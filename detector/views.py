import os
import tempfile
from datetime import datetime
from io import BytesIO

import numpy as np
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from PIL import Image

from accounts.models import Verification
from .predict import predict_currency

try:
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


def _clamp_score(value):
    return max(0.0, min(100.0, float(value)))


def _score_level(score):
    if score < 40:
        return "Low"
    if score < 70:
        return "Medium"
    return "High"


def _compute_note_factors(image_bytes):
    try:
        image = Image.open(BytesIO(image_bytes)).convert("L")
        gray = np.asarray(image, dtype=np.float32) / 255.0
    except Exception:
        fallback = [
            ("Texture/Print Clarity", 50.0),
            ("Alignment & Geometry", 50.0),
            ("Security Feature Visibility", 50.0),
            ("Image Capture Quality", 50.0),
        ]
        return [
            {"label": label, "score": score, "level": _score_level(score)}
            for label, score in fallback
        ]

    if gray.ndim != 2 or gray.size == 0:
        gray = np.zeros((224, 224), dtype=np.float32)

    height, width = gray.shape
    grad_y, grad_x = np.gradient(gray)
    grad_mag = np.hypot(grad_x, grad_y)

    contrast_std = float(np.std(gray))
    sharpness_raw = float(np.mean(np.abs(np.diff(gray, axis=0))) + np.mean(np.abs(np.diff(gray, axis=1))))
    clipped_ratio = float(np.mean((gray < 0.03) | (gray > 0.97)))

    contrast_score = _clamp_score(contrast_std * 280)
    sharpness_score = _clamp_score(sharpness_raw * 380)
    exposure_score = _clamp_score(100 - (clipped_ratio * 420))

    texture_score = _clamp_score((0.62 * sharpness_score) + (0.38 * contrast_score))
    capture_score = _clamp_score(
        (0.45 * sharpness_score) + (0.35 * exposure_score) + (0.20 * contrast_score)
    )

    threshold = np.percentile(grad_mag, 75)
    edge_mask = grad_mag > threshold
    edge_points = np.argwhere(edge_mask)
    if edge_points.size == 0:
        alignment_score = 45.0
    else:
        y_min, x_min = edge_points.min(axis=0)
        y_max, x_max = edge_points.max(axis=0)
        bbox_area = float((y_max - y_min + 1) * (x_max - x_min + 1))
        bbox_ratio = bbox_area / float(height * width)
        bbox_center_x = (x_min + x_max) / 2.0
        bbox_center_y = (y_min + y_max) / 2.0
        center_dx = (bbox_center_x - (width / 2.0)) / max(width, 1)
        center_dy = (bbox_center_y - (height / 2.0)) / max(height, 1)
        center_distance = (center_dx ** 2 + center_dy ** 2) ** 0.5

        center_score = _clamp_score(100 - (center_distance * 250))
        size_score = _clamp_score(100 - (abs(bbox_ratio - 0.55) * 180))
        alignment_score = _clamp_score((0.6 * center_score) + (0.4 * size_score))

    y1 = int(height * 0.2)
    y2 = int(height * 0.8)
    left_x1, left_x2 = int(width * 0.08), int(width * 0.28)
    right_x1, right_x2 = int(width * 0.62), int(width * 0.82)

    left_region = gray[y1:y2, left_x1:left_x2] if y2 > y1 and left_x2 > left_x1 else gray
    right_region = gray[y1:y2, right_x1:right_x2] if y2 > y1 and right_x2 > right_x1 else gray
    left_std = float(np.std(left_region))
    right_std = float(np.std(right_region))
    local_feature_score = _clamp_score(((left_std + right_std) / 2.0) * 320)
    security_score = _clamp_score((0.7 * local_feature_score) + (0.3 * sharpness_score))

    factors = [
        ("Texture/Print Clarity", texture_score),
        ("Alignment & Geometry", alignment_score),
        ("Security Feature Visibility", security_score),
        ("Image Capture Quality", capture_score),
    ]
    return [
        {"label": label, "score": round(score, 1), "level": _score_level(score)}
        for label, score in factors
    ]


def _pdf_escape(text):
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(lines):
    stream_lines = ["BT", "/F1 18 Tf", "50 790 Td", "(Currency Detection Report) Tj", "0 -30 Td", "/F1 12 Tf"]

    for line in lines:
        stream_lines.append(f"({_pdf_escape(line)}) Tj")
        stream_lines.append("0 -20 Td")

    stream_lines.append("ET")
    stream = "\n".join(stream_lines)
    stream_bytes = stream.encode("latin-1", errors="replace")

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream_bytes)} >>\nstream\n{stream}\nendstream",
    ]

    pdf = b"%PDF-1.4\n"
    offsets = [0]

    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{index} 0 obj\n{obj}\nendobj\n".encode("latin-1", errors="replace")

    xref_start = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode("latin-1")

    pdf += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF"
    ).encode("latin-1")

    return pdf


@csrf_exempt
def upload_image(request):
    return detect_currency(request)


@csrf_exempt
def detect_currency(request):
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Invalid request method"},
            status=405,
        )

    uploaded_file = request.FILES.get("file") or request.FILES.get("image")
    if not uploaded_file:
        return JsonResponse(
            {"status": "error", "message": "No file uploaded"},
            status=400,
        )

    uploaded_name = os.path.basename(uploaded_file.name or "uploaded_note.jpg")
    uploaded_bytes = uploaded_file.read()
    if not uploaded_bytes:
        return JsonResponse(
            {"status": "error", "message": "Uploaded file is empty"},
            status=400,
        )

    suffix = os.path.splitext(uploaded_name)[1] or ".jpg"
    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(uploaded_bytes)
            temp_file_path = temp_file.name

        predicted_label, confidence, class_scores = predict_currency(temp_file_path)
    except Exception as exc:
        return JsonResponse(
            {"status": "error", "message": f"Prediction failed: {str(exc)}"},
            status=500,
        )
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass

    normalized_result = str(predicted_label or "UNKNOWN").upper()
    confidence_percent = 0.0
    try:
        confidence_percent = float(confidence)
        if confidence_percent <= 1:
            confidence_percent *= 100
    except (TypeError, ValueError):
        confidence_percent = 0.0

    fake_score = float(class_scores.get("fake", 0.0)) if isinstance(class_scores, dict) else 0.0
    real_score = float(class_scores.get("real", 0.0)) if isinstance(class_scores, dict) else 0.0
    fake_score = max(0.0, min(1.0, fake_score))
    real_score = max(0.0, min(1.0, real_score))

    if request.user.is_authenticated and normalized_result in {"REAL", "FAKE"}:
        verification = Verification.objects.create(
            user=request.user,
            result=normalized_result,
            confidence=round(confidence_percent, 2),
        )
        verification.image.save(uploaded_name, ContentFile(uploaded_bytes), save=True)

    factors = _compute_note_factors(uploaded_bytes)
    return JsonResponse(
        {
            "status": "success",
            "result": normalized_result,
            "confidence": confidence_percent / 100 if confidence_percent else 0.0,
            "file": uploaded_name,
            "factors": factors,
            "class_scores": {
                "fake": fake_score,
                "real": real_score,
            },
        },
        status=200,
    )

def download_report(request):
    if request.method != "GET":
        return JsonResponse(
            {"status": "error", "message": "Invalid request method"},
            status=405,
        )

    result = (request.GET.get("result") or "UNKNOWN").upper()
    confidence_raw = request.GET.get("confidence")
    file_name = request.GET.get("file") or "N/A"

    confidence_text = "N/A"
    if confidence_raw not in (None, ""):
        try:
            confidence_value = float(confidence_raw)
            if confidence_value <= 1:
                confidence_value *= 100
            confidence_text = f"{confidence_value:.2f}%"
        except (TypeError, ValueError):
            confidence_text = str(confidence_raw)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_filename = f"currency_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    if not HAS_REPORTLAB:
        report_lines = [
            f"Generated At: {generated_at}",
            f"Image File: {file_name}",
            f"Result: {result}",
            f"Confidence: {confidence_text}",
            "Status: Analysis completed.",
        ]
        pdf_bytes = _build_simple_pdf(report_lines)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{report_filename}"'
        return response

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("<b>Fake Currency Detection Report</b>", styles["Title"]))
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(Paragraph(f"Generated on: {generated_at}", styles["Normal"]))
    elements.append(Spacer(1, 0.3 * inch))

    data = [
        ["User", "Guest"],
        ["Result", result],
        ["Confidence", confidence_text],
        ["Model Used", "Deep Learning CNN Model"],
        ["Image File", file_name],
    ]
    table = Table(data, colWidths=[150, 250])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 1), (-1, 1), colors.red if result == "FAKE" else colors.green),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.white),
        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(
        Paragraph(
            "This report was generated using AI-powered currency authentication system.",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(
        Paragraph(
            "(c) 2026 Fake Currency Detection System | Final Year Project",
            styles["Normal"],
        )
    )

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{report_filename}"'
    return response

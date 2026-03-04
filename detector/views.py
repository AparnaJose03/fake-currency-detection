import os
import tempfile
from datetime import datetime
from io import BytesIO

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

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

    suffix = os.path.splitext(uploaded_file.name)[1] or ".jpg"
    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        predicted_label, confidence = predict_currency(temp_file_path)
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

    return JsonResponse(
        {
            "status": "success",
            "result": predicted_label,
            "confidence": confidence,
            "file": uploaded_file.name,
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

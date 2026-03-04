import json
import re
from datetime import datetime
from io import BytesIO

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import HelpTicket

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
    stream_lines = [
        "BT",
        "/F1 18 Tf",
        "50 790 Td",
        "(Fake Currency Detection Report) Tj",
        "0 -30 Td",
        "/F1 12 Tf",
    ]

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


ALLOWED_RESULTS = {"REAL", "FAKE", "UNKNOWN"}
MAX_FIELD_LEN = 100
REPORT_RATE_LIMIT = 20
REPORT_RATE_WINDOW_SEC = 60


def _sanitize_text(value, max_len=MAX_FIELD_LEN):
    text = (value or "").strip()
    text = re.sub(r"[^\x20-\x7E]", "", text)
    return text[:max_len]


def _parse_confidence(raw_confidence):
    raw = _sanitize_text(raw_confidence, 16).replace("%", "")
    if raw == "":
        return "0.00%"
    try:
        value = float(raw)
        if value <= 1:
            value *= 100
        value = max(0.0, min(100.0, value))
        return f"{value:.2f}%"
    except ValueError:
        return "0.00%"


def _is_rate_limited(request):
    user_part = f"user-{request.user.id}" if request.user.is_authenticated else f"ip-{request.META.get('REMOTE_ADDR', 'unknown')}"
    key = f"download-report:{user_part}"

    current = cache.get(key, 0)
    if current >= REPORT_RATE_LIMIT:
        return True

    if current == 0:
        cache.set(key, 1, timeout=REPORT_RATE_WINDOW_SEC)
    else:
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, current + 1, timeout=REPORT_RATE_WINDOW_SEC)

    return False


# ================= REGISTER =================
@csrf_exempt
@require_POST
def register_view(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not (name and email and password):
        return JsonResponse({"error": "All fields required"}, status=400)

    if User.objects.filter(username=email).exists():
        return JsonResponse({"error": "User already exists"}, status=400)

    User.objects.create_user(
        username=email,
        email=email,
        password=password,
        first_name=name,
    )

    return JsonResponse({"message": "Registration successful"}, status=201)


# ================= LOGIN =================
@csrf_exempt
@require_POST
def login_view(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    user = authenticate(request, username=email, password=password)

    if user is None:
        return JsonResponse({"error": "Invalid email or password"}, status=401)

    login(request, user)

    return JsonResponse(
        {
            "message": "Login successful",
            "user": {
                "username": user.username,
                "date_joined": user.date_joined,
                "last_login": user.last_login,
            },
        },
        status=200,
    )


# ================= PROFILE =================
@require_GET
def me_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    u = request.user

    return JsonResponse({
        "id": u.id,
        "full_name": (u.first_name + " " + u.last_name).strip() or u.username,
        "username": u.username,
        "email": u.email,
        "is_staff": u.is_staff,
        "date_joined": u.date_joined,
        "last_login": u.last_login,
    })


# ================= LOGOUT =================
@csrf_exempt
def logout_view(request):
    logout(request)
    return JsonResponse({"message": "Logged out"})


# ================= HELP =================
@csrf_exempt
@require_POST
def help_create(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    topic = (data.get("topic") or "").strip()
    message = (data.get("message") or "").strip()

    if not (name and email and topic and message):
        return JsonResponse({"error": "All fields required"}, status=400)

    ticket = HelpTicket.objects.create(
        name=name,
        email=email,
        topic=topic,
        message=message,
        user=request.user if request.user.is_authenticated else None,
    )

    return JsonResponse({"ok": True, "ticket_id": ticket.id}, status=201)


# ================= DETECT (TEMPORARY DEMO) =================
@csrf_exempt
@require_POST
def detect(request):

    if "image" not in request.FILES:
        return JsonResponse({"status": "error", "message": "No image uploaded"}, status=400)

    # TEMPORARY RESULT (replace with real model later)
    return JsonResponse({
        "status": "success",
        "result": "FAKE",
        "confidence": 0.94
    })


# ================= BEAUTIFUL PDF REPORT =================
@csrf_exempt
@require_POST
def download_report(request):
    if _is_rate_limited(request):
        return JsonResponse(
            {"error": "Too many report requests. Please retry after a minute."},
            status=429,
        )

    result = _sanitize_text(request.POST.get("result", "UNKNOWN"), 20).upper()
    if result not in ALLOWED_RESULTS:
        result = "UNKNOWN"

    confidence = _parse_confidence(request.POST.get("confidence", "0%"))
    username = _sanitize_text(request.user.username, 60) if request.user.is_authenticated else "Guest"
    if not username:
        username = "Guest"

    if not HAS_REPORTLAB:
        lines = [
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"User: {username}",
            f"Result: {result}",
            f"Confidence: {confidence}",
            "Model Used: Deep Learning CNN Model",
        ]
        pdf_bytes = _build_simple_pdf(lines)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="currency_report.pdf"'
        return response

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer)
    elements = []

    styles = getSampleStyleSheet()

    # ===== TITLE =====
    elements.append(Paragraph("<b>Fake Currency Detection Report</b>", styles["Title"]))
    elements.append(Spacer(1, 0.5 * inch))

    # ===== DATE =====
    elements.append(Paragraph(
        f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        styles["Normal"]
    ))
    elements.append(Spacer(1, 0.3 * inch))

    # ===== USER =====
    # ===== TABLE DATA =====
    data = [
        ["User", username],
        ["Result", result],
        ["Confidence", confidence],
        ["Model Used", "Deep Learning CNN Model"],
    ]

    table = Table(data, colWidths=[150, 250])

    # ===== STYLE TABLE =====
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 1), (-1, 1),
         colors.red if result == "FAKE" else colors.green),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 0.5 * inch))

    # ===== FOOTER =====
    elements.append(Paragraph(
        "This report was generated using AI-powered currency authentication system.",
        styles["Normal"]
    ))
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(
        "© 2026 Fake Currency Detection System | Final Year Project",
        styles["Normal"]
    ))

    doc.build(elements)
    buffer.seek(0)

    return FileResponse(buffer, as_attachment=True, filename="currency_report.pdf")

from django.db import models
from django.contrib.auth.models import User


class Verification(models.Model):
    RESULT_CHOICES = [
        ("REAL", "REAL"),
        ("FAKE", "FAKE"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="verifications")
    image = models.ImageField(upload_to="uploads/")
    result = models.CharField(max_length=10, choices=RESULT_CHOICES)
    confidence = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.result} ({self.confidence}%)"


class Report(models.Model):
    verification = models.OneToOneField(Verification, on_delete=models.CASCADE, related_name="report")
    pdf_file = models.FileField(upload_to="reports/")
  
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report for Verification #{self.verification.id}"

class HelpTicket(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=120)
    email = models.EmailField()
    topic = models.CharField(max_length=120)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.topic} - {self.email}"


class FakeNoteReport(HelpTicket):
    class Meta:
        proxy = True
        verbose_name = "Fake Note Report"
        verbose_name_plural = "Fake Note Reports"


class GeneratedReport(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="generated_reports")
    result = models.CharField(max_length=10)
    confidence = models.CharField(max_length=20)
    source_file = models.CharField(max_length=120, blank=True)
    pdf_file = models.FileField(upload_to="reports/generated/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        owner = self.user.username if self.user else "Guest"
        return f"{owner} - {self.result} - {self.created_at:%Y-%m-%d %H:%M:%S}"

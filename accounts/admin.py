from django.contrib import admin
from .models import Verification, Report, HelpTicket, FakeNoteReport


@admin.register(Verification)
class VerificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "result", "confidence", "created_at")
    list_filter = ("result", "created_at")
    search_fields = ("user__username",)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "verification", "created_at")
    search_fields = ("verification__id",)


@admin.register(HelpTicket)
class HelpTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket_type", "name", "email", "user", "created_at")
    list_filter = ("topic", "created_at")
    search_fields = ("name", "email", "topic", "message", "user__username")
    ordering = ("-created_at",)
    list_per_page = 25

    @admin.display(description="Type")
    def ticket_type(self, obj):
        if (obj.topic or "").strip().lower() == "fake note report":
            return "Fake Note Report"
        return "Support"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.exclude(topic__iexact="Fake Note Report")


@admin.register(FakeNoteReport)
class FakeNoteReportAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "email", "user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "email", "message", "user__username")
    ordering = ("-created_at",)
    list_per_page = 25

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(topic__iexact="Fake Note Report")

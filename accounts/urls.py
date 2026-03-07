from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register_view),
    path("login/", views.login_view),
    path("logout/", views.logout_view),
    path("me/", views.me_view),
    path("help/", views.help_create),
    path("history/", views.history_view),
    path("history/clear/", views.history_clear),
    path("history/<int:item_id>/", views.history_delete_item),
    path("download-report/", views.download_report),  # IMPORTANT
    path("report-history/", views.report_history),
    path("report-history/clear/", views.report_history_clear),
    path("report-history/<int:item_id>/", views.report_history_delete_item),
]

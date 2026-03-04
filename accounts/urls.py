from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register_view),
    path("login/", views.login_view),
    path("logout/", views.logout_view),
    path("me/", views.me_view),
    path("help/", views.help_create),
    path("download-report/", views.download_report),  # IMPORTANT
]

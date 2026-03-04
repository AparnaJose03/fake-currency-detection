from django.urls import path
from . import views

urlpatterns = [
    path("detect/", views.detect_currency, name="detect_currency"),
    path('upload/', views.upload_image, name='upload_image'),
    path("report/", views.download_report, name="download_report"),
]

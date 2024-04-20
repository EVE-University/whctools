"""Routes."""

from django.urls import path

from . import views

app_name = "whctools"

urlpatterns = [
    path("", views.index, name="index"),
]

"""Routes."""

from django.urls import path

from . import views

app_name = "whctools"

urlpatterns = [
    path("", views.index, name="index"),
    path("staff", views.staff, name="staff"),
    path("apply/<char_id>", views.apply, name="apply"),
    path("withdraw/<char_id>", views.withdraw, name="withdraw"),
    # Staff actions
    path("staff/action/<char_id>/accept/<acl_name>", views.accept, name="staff_accept"),
    path(
        "staff/action/<char_id>/reject/<reason>/<days>",
        views.reject,
        name="staff_reject",
    ),
    path(
        "staff/action/<char_id>/reject/<reason>/<days>",
        views.reject,
        name="staff_reject",
    ),
    path("staff/action/<char_id>/reset", views.reset, name="staff_reset"),
    path("staff/action/<acl_pk>/view", views.list_acl_members, name="view_acl_members"),
    path("staff/action/<acl_pk>/view/<char_id>/reject/<reason>/<days>", views.reject, name="acl_staff_reject")
]

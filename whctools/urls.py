"""Routes."""

from django.urls import path

from . import views

app_name = "whctools"

urlpatterns = [
    path("", views.index, name="index"),
    path("apply/<char_id>", views.apply, name="apply"),
    path("withdraw/<char_id>", views.withdraw, name="withdraw"),
    # Staff actions
    path("staff/action/<char_id>/accept/<acl_name>", views.accept, name="staff_accept"),
    path(
        "staff/action/<char_id>/reject/<reason>/<days>/<source>",
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
    path("staff/open", views.open_applications, name="staff_view_open_apps"),
    path(
        "staff/rejected", views.rejected_applications, name="staff_view_rejected_apps"
    ),
    # path("staff/list_acls", views.list_acls, name="staff_view_acl_lists"),
    path("staff/getSkills/<char_id>", views.get_skills, name="get_skills"),
    path(
        "staff/<acl_pk>/sync_groups_with_acl",
        views.sync_groups_with_acl,
        name="sync_groups_with_acl",
    ),
    path(
        "staff/<acl_pk>/sync_wanderer_with_acl",
        views.sync_wanderer_with_acl,
        name="sync_wanderer_with_acl",
    ),
    path("staff/getMail", views.get_mail, name="get_mail"),
    path("staff/updateMail", views.update_mail, name="update_mail"),
]

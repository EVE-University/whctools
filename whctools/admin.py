"""Admin site."""

from django.contrib import admin

from . import models

admin.site.register(models.Applications)
admin.site.register(models.ApplicationHistory)
admin.site.register(models.Acl)
admin.site.register(models.WelcomeMail)

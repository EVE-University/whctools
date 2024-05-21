from django.apps import AppConfig

from whctools import __version__


class WhctoolsConfig(AppConfig):
    name = "whctools"
    label = "whctools"
    verbose_name = "WHC tools V" + __version__

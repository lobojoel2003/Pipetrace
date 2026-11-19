from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ExportConfig(AppConfig):
    name = "pipetrace.export"
    label = "export"
    verbose_name = _("Static export")

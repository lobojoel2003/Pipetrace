from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ResidentsConfig(AppConfig):
    name = "pipetrace.residents"
    label = "residents"
    verbose_name = _("Resident submissions")

"""
Appconfig for Django Clear To Build
"""

from django.apps import AppConfig


class DjangoCtbConfig(AppConfig):
    """
    Appconfig for Django Clear To Build
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "django_ctb"
    verbose_name = "Clear To Build"

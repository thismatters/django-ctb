"""
Config for Django Clear To Build
"""

from appconf import AppConf
from django.conf import settings  # noqa: F401


class DjangoCTBAppConf(AppConf):
    """
    Config for Django Clear To Build
    """

    MOUSER_API_KEY = ""

    class Meta:
        prefix = "ctb"

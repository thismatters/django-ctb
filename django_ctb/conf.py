from appconf import AppConf
from django.conf import settings  # noqa: F401


class DjangoCTBAppConf(AppConf):
    MOUSER_API_KEY = ""

    class Meta:
        prefix = "ctb"

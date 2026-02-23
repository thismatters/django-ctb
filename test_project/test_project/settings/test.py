from .base import *  # noqa: F403

INSTALLED_APPS.remove("django_extensions")  # noqa: F405


DRAMATIQ_BROKER = {
    "BROKER": "dramatiq.brokers.stub.StubBroker",
    "OPTIONS": {},
    "MIDDLEWARE": [
        # "dramatiq.middleware.Prometheus",
        "dramatiq.middleware.AgeLimit",
        "dramatiq.middleware.TimeLimit",
        "dramatiq.middleware.Callbacks",
        "dramatiq.middleware.Retries",
        "django_dramatiq.middleware.DbConnectionsMiddleware",
        # "django_dramatiq.middleware.AdminMiddleware",
    ],
}

CTB_MOUSER_API_KEY = "FAKE"

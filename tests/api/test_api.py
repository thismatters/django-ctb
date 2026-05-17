from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


class TestAutogenDocs:
    def test_autogen_schema_available(self):
        api_client = APIClient()
        # the URL is defined by the ``test_project``
        response = api_client.get(reverse("schema"))
        assert response.status_code == status.HTTP_200_OK

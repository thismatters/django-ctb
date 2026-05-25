import pytest

from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_authed_api_client(user, api_client):
    api_client.login(username="username", password="password")
    return api_client


@pytest.fixture
def other_user_authed_api_client(user_factory, api_client):
    user_factory("other", email="other@test.test", password="otherpass")
    api_client.login(username="other", password="otherpass")
    return api_client

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model
from django_ctb import models as m


@pytest.fixture
def user(db):
    user = get_user_model().objects.create_user(
        "username", email="test@test.test", password="password"
    )
    yield user
    user.delete()


@pytest.fixture
def user_authed_api_client(user):
    api_client = APIClient()
    api_client.login(username="username", password="password")
    return api_client


class TestProjectCRUD:
    basename = "project"
    model = m.Project

    # @pytest.fixture(
    #     autouse=True,
    #     scope="class",
    #     params=[
    #         pytest.param(
    #             "project",  # basename
    #             "project",  # fixture name
    #             m.Project,  # model
    #             fac.ProjectFactory,  # factory
    #         )
    #     ],
    # )
    # def klass_loader(self, request):
    #     pass

    def test_project__create(self, db, user_authed_api_client):
        response = user_authed_api_client.post(
            reverse(f"django-ctb-api:{self.basename}-list"),
            {
                "name": "test project",
                "git_server": 1,
                "git_user": "test_user",
                "git_repo": "test_repo",
            },
            format="json",
        )
        assert (
            response.status_code == status.HTTP_201_CREATED
        ), f"Bad response ({response.status_code}, expected 201)"
        created = m.Project.objects.get(id=response.json()["id"])
        assert created.name == "test project"
        assert created.git_url == "https://github.com/test_user/test_repo"
        created.delete()
        m.Owner.objects.all().delete()

    def test_project__detail(self, user_authed_api_client, project: m.Project):
        response = user_authed_api_client.get(
            reverse(
                f"django-ctb-api:{self.basename}-detail",
                kwargs={"pk": project.id},
            )
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == project.name

    def test_project__list(self, user_authed_api_client, project: m.Project):
        response = user_authed_api_client.get(
            reverse(f"django-ctb-api:{self.basename}-list")
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()[0]["name"] == project.name

    def test_project__update(self, user_authed_api_client, project: m.Project):
        response = user_authed_api_client.patch(
            reverse(
                f"django-ctb-api:{self.basename}-detail", kwargs={"pk": project.id}
            ),
            {"name": "other test project"},
        )
        project.refresh_from_db()
        assert project.name == "other test project"

    def test_project__delete(self, user_authed_api_client, project: m.Project):
        response = user_authed_api_client.delete(
            reverse(
                f"django-ctb-api:{self.basename}-detail", kwargs={"pk": project.id}
            ),
            {"name": "other test project"},
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        with pytest.raises(m.Project.DoesNotExist):
            project.refresh_from_db()

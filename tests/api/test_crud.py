from datetime import datetime
from typing import Any, cast
from django.db import models
import pytest
from django.urls import reverse
from rest_framework import serializers, status
from rest_framework.test import APIClient
from factory.django import DjangoModelFactory

from django.contrib.auth import get_user_model
from django_ctb import models as m
from django_ctb.api import serializers as s
from tests import factories as fac


@pytest.fixture
def user_authed_api_client(user):
    api_client = APIClient()
    api_client.login(username="username", password="password")
    return api_client


def deep_print(instance: models.Model):
    for field in instance._meta.fields:
        try:
            print(f"{field.name}: {getattr(instance, field.name)}")
        except Exception as e:
            print(f"{field.name}: exception {e}")


class TestCRUD:
    # I want to use this single class to do all basic API CRUD testing to ensure
    # that everything is as standard as possible in the schema definitions and
    # endpoint patterns. If anything here becomes too brittle it is an indicator
    # that the API has become to snowflakey.
    basename: str
    resource: Any
    model: type[models.Model]
    serializer_klass: type[serializers.Serializer]
    factory: type[DjangoModelFactory]

    @pytest.fixture(
        autouse=True,
        params=[
            pytest.param(
                (
                    "vendor-order",  # basename
                    "vendor_order",  # fixture name
                    m.VendorOrder,  # model
                    s.VendorOrderSerializer,  # serializer
                    fac.VendorOrderFactory,  # factory
                ),
                id="vendor-order",
            ),
            pytest.param(
                (
                    "inventory",  # basename
                    "inventory",  # fixture name
                    m.Inventory,  # model
                    s.InventorySerializer,  # serializer
                    fac.InventoryFactory,  # factory
                ),
                id="inventory",
            ),
            pytest.param(
                (
                    "project",  # basename
                    "project",  # fixture name
                    m.Project,  # model
                    s.ProjectSerializer,  # serializer
                    fac.ProjectFactory,  # factory
                ),
                id="project",
            ),
        ],
    )
    def klass_loader(self, request):
        basename, fixture_name, model, serializer_klass, factory = request.param
        request.cls.basename = basename
        request.cls.resource = request.getfixturevalue(fixture_name)
        request.cls.model = model
        request.cls.serializer_klass = serializer_klass
        request.cls.factory = factory

    def test_project__create(self, db, user_authed_api_client):
        # build data for posting from actual instance
        instance = self.factory.build()
        deep_print(instance)
        serialized = cast(dict, self.serializer_klass(instance).data)
        print(serialized)
        serialized.pop("id", None)
        # post data to API
        response = user_authed_api_client.post(
            reverse(f"django-ctb-api:{self.basename}-list"), serialized, format="json"
        )
        # check response
        assert (
            response.status_code == status.HTTP_201_CREATED
        ), f"Bad response ({response.status_code}, expected 201) {response.text}"
        # check instance created
        print(response.json())
        created = self.model.objects.get(id=response.json()["id"])
        try:
            # check attributes
            for field in instance._meta.concrete_fields:
                if field.name in ("id", "owner"):
                    continue
                if not hasattr(created, field.name):
                    continue
                assert getattr(created, field.name) == getattr(instance, field.name)
        finally:
            # clean up
            created.delete()

    def test_project__detail(self, user_authed_api_client):
        response = user_authed_api_client.get(
            reverse(
                f"django-ctb-api:{self.basename}-detail",
                kwargs={"pk": self.resource.id},
            )
        )
        assert response.status_code == status.HTTP_200_OK
        response_data = response.json()
        assert response_data["id"] == self.resource.id
        assertion_count: int = 0
        for field in self.resource._meta.concrete_fields:
            resource_val = getattr(self.resource, field.name)
            response_field = field.name
            if isinstance(resource_val, models.Model):
                if f"{field.name}_id" not in response_data:
                    # not every related resource is actually serialized
                    continue
                # by convention related resources are referenced by `_id` within
                #   serializers
                resource_val = resource_val.id  # type: ignore
                response_field = f"{field.name}_id"

            if isinstance(resource_val, datetime):
                # format datetimes
                resource_val = resource_val.isoformat().replace("+00:00", "Z")
            if response_field not in response_data:
                # skip anything which isn't in response
                continue
            assert resource_val == response_data[response_field]
            assertion_count += 1
        assert assertion_count > 0, "No fields were compared!"

    def test_project__update(self, user_authed_api_client):
        instance = self.factory.build()
        serialized = cast(dict, self.serializer_klass(instance).data)
        serialized.pop("id", None)
        response = user_authed_api_client.put(
            reverse(
                f"django-ctb-api:{self.basename}-detail",
                kwargs={"pk": self.resource.id},
            ),
            serialized,
            format="json",
        )
        assert (
            response.status_code == status.HTTP_200_OK
        ), f"Bad response ({response.status_code}, expected 200) {response.text}"
        self.resource.refresh_from_db()
        # TODO: expanded validation here
        for field in instance._meta.concrete_fields:
            if field.name in ("id", "owner"):
                continue
            assert getattr(self.resource, field.name) == getattr(instance, field.name)

    def test_project__list(self, user_authed_api_client):
        response = user_authed_api_client.get(
            reverse(f"django-ctb-api:{self.basename}-list")
        )
        assert (
            response.status_code == status.HTTP_200_OK
        ), f"Bad response ({response.status_code}, expected 200) {response.text}"

        assert response.json()[0]["id"] == self.resource.id

    def test_project__delete(self, user_authed_api_client):
        response = user_authed_api_client.delete(
            reverse(
                f"django-ctb-api:{self.basename}-detail",
                kwargs={"pk": self.resource.id},
            ),
            {"name": "other test project"},
        )
        assert (
            response.status_code == status.HTTP_204_NO_CONTENT
        ), f"Bad response ({response.status_code}, expected 204) {response.text}"
        with pytest.raises(self.model.DoesNotExist):
            self.resource.refresh_from_db()

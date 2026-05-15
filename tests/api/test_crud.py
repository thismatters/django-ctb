from datetime import datetime
from typing import Any, NamedTuple, cast
from unittest.mock import Mock

import pytest
from django.db import models
from django.db.models.fields.generated import GeneratedField
from django.urls import reverse
from factory.django import DjangoModelFactory
from rest_framework import serializers, status
from rest_framework.test import APIClient

from django_ctb import models as m
from django_ctb import services
from django_ctb.api import serializers as s
from django_ctb.mouser.services import MouserService
from tests import factories as fac


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


def deep_print(instance: models.Model):
    """Print all attributes for the class"""
    print(f"model: {type(instance)}")
    for field in instance._meta.fields:
        try:
            print(f">> {field.name}: {getattr(instance, field.name)}")
        except Exception as e:
            print(f"!! {field.name}: exception {e}")


class APITestParam(NamedTuple):
    basename: str
    fixture_name: str
    model: type[models.Model]
    serializer_klass: type[serializers.Serializer]
    factory: type[DjangoModelFactory]
    is_owned_resource: bool = True


test_params = [
    APITestParam(
        basename="footprint",
        fixture_name="footprint",
        model=m.Footprint,
        serializer_klass=s.FootprintSerializer,
        factory=fac.FootprintFactory,
        is_owned_resource=False,
    ),
    APITestParam(  # has M2M relationship
        basename="package",
        fixture_name="package",
        model=m.Package,
        serializer_klass=s.PackageSerializer,
        factory=fac.PackageFactory,
        is_owned_resource=False,
    ),
    APITestParam(
        basename="vendor",
        fixture_name="vendor",
        model=m.Vendor,
        serializer_klass=s.VendorSerializer,
        factory=fac.VendorFactory,
        is_owned_resource=False,
    ),
    APITestParam(
        basename="part",
        fixture_name="part",
        model=m.Part,
        serializer_klass=s.PartSerializer,
        factory=fac.PartFactory,
        is_owned_resource=False,
    ),
    APITestParam(
        basename="vendor-part",
        fixture_name="vendor_part",
        model=m.VendorPart,
        serializer_klass=s.VendorPartSerializer,
        factory=fac.VendorPartFactory,
        is_owned_resource=False,
    ),
    APITestParam(  # has direct relation to ``owner``
        basename="implicit-project-part",
        fixture_name="implicit_project_part",
        model=m.ImplicitProjectPart,
        serializer_klass=s.ImplicitProjectPartSerializer,
        factory=fac.ImplicitProjectPartFactory,
    ),
    APITestParam(  # has direct relation to ``owner``
        basename="vendor-order",
        fixture_name="vendor_order",
        model=m.VendorOrder,
        serializer_klass=s.VendorOrderSerializer,
        factory=fac.VendorOrderFactory,
    ),
    APITestParam(  # has direct relation to ``owner``
        basename="inventory",
        fixture_name="inventory",
        model=m.Inventory,
        serializer_klass=s.InventorySerializer,
        factory=fac.InventoryFactory,
    ),
    APITestParam(
        basename="inventory-line",
        fixture_name="inventory_line",
        model=m.InventoryLine,
        serializer_klass=s.InventoryLineSerializer,
        factory=fac.InventoryLineFactory,
    ),
    APITestParam(  # has direct relation to ``owner``
        basename="vendor-order-line",
        fixture_name="vendor_order_line",
        model=m.VendorOrderLine,
        serializer_klass=s.VendorOrderLineSerializer,
        factory=fac.VendorOrderLineFactory,
    ),
    APITestParam(
        basename="inventory-action",
        fixture_name="inventory_action",
        model=m.InventoryAction,
        serializer_klass=s.InventoryActionSerializer,
        factory=fac.InventoryActionFactory,
    ),
    APITestParam(
        basename="project",
        fixture_name="project",
        model=m.Project,
        serializer_klass=s.ProjectSerializer,
        factory=fac.ProjectFactory,
    ),
    APITestParam(
        basename="project-version",
        fixture_name="project_version",
        model=m.ProjectVersion,
        serializer_klass=s.ProjectVersionSerializer,
        factory=fac.ProjectVersionFactory,
    ),
    APITestParam(
        basename="project-part",
        fixture_name="project_part",
        model=m.ProjectPart,
        serializer_klass=s.ProjectPartSerializer,
        factory=fac.ProjectPartFactory,
    ),
    APITestParam(
        basename="project-part-footprint-ref",
        fixture_name="project_part_footprint_ref",
        model=m.ProjectPartFootprintRef,
        serializer_klass=s.ProjectPartFootprintRefSerializer,
        factory=fac.ProjectPartFootprintRefFactory,
    ),
    APITestParam(
        basename="project-build",
        fixture_name="project_build",
        model=m.ProjectBuild,
        serializer_klass=s.ProjectBuildSerializer,
        factory=fac.ProjectBuildFactory,
    ),
    APITestParam(
        basename="project-build-part-shortage",
        fixture_name="project_build_part_shortage",
        model=m.ProjectBuildPartShortage,
        serializer_klass=s.ProjectBuildPartShortageSerializer,
        factory=fac.ProjectBuildPartShortageFactory,
    ),
    APITestParam(
        basename="project-build-part-reservation",
        fixture_name="project_build_part_reservation",
        model=m.ProjectBuildPartReservation,
        serializer_klass=s.ProjectBuildPartReservationSerializer,
        factory=fac.ProjectBuildPartReservationFactory,
    ),
]


# I want to use this single class to do all basic API CRUD testing to ensure
# that everything is as standard as possible in the schema definitions and
# endpoint patterns. If anything here becomes too brittle it is an indicator
# that the API has become to snowflakey.
class TestCRUD:
    basename: str
    resource: Any
    model: type[models.Model]
    serializer_klass: type[serializers.Serializer]
    factory: type[DjangoModelFactory]
    is_owned_resource: bool

    @pytest.fixture(
        autouse=True,
        params=[pytest.param(tup, id=tup.basename) for tup in test_params],
    )
    def klass_loader(self, request):
        """Load all the parameterized data from the fixture into the test class"""
        request.cls.basename = request.param.basename
        request.cls.resource = request.getfixturevalue(request.param.fixture_name)
        request.cls.model = request.param.model
        request.cls.serializer_klass = request.param.serializer_klass
        request.cls.factory = request.param.factory
        request.cls.is_owned_resource = request.param.is_owned_resource

    def test_create(self, db, user_authed_api_client):
        # build data for posting from actual instance
        instance = self.factory.build()
        # instances with many-to-many relationships will not serialize without an id
        instance.id = 0
        deep_print(instance)
        serialized = cast(dict, self.serializer_klass(instance).data)
        print(serialized)
        serialized.pop("id", None)
        # post data to API
        response = user_authed_api_client.post(
            reverse(f"django-ctb-api:{self.basename}-list"), serialized, format="json"
        )
        # check response
        assert response.status_code == status.HTTP_201_CREATED, (
            f"Bad response ({response.status_code}, expected 201) {response.text}"
        )
        # check instance created
        print(response.json())
        created = self.model.objects.get(id=response.json()["id"])
        try:
            # check attributes
            for field in instance._meta.concrete_fields:
                if field.name in ("id", "owner", "created", "updated"):
                    continue
                if not hasattr(created, field.name):
                    continue
                if isinstance(field, GeneratedField):
                    # don't compare this... it isn't real
                    continue
                _created_value = getattr(created, field.name)
                _instance_value = getattr(instance, field.name)
                assert _created_value == _instance_value
        finally:
            # clean up
            created.delete()

    def test_detail(self, user_authed_api_client):
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

    def test_detail_inaccessible_to_other_user(
        self, other_user_authed_api_client, request
    ):
        if not self.is_owned_resource:
            pytest.skip("not owned resource, test meaningless")

        response = other_user_authed_api_client.get(
            reverse(
                f"django-ctb-api:{self.basename}-detail",
                kwargs={"pk": self.resource.id},
            )
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND, (
            f"Bad response ({response.status_code}, expected 404) {response.text}"
        )

    def test_update(self, user_authed_api_client):
        instance = self.factory.build()
        # instances with many-to-many relationships will not serialize without an id
        instance.id = 0
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
        assert response.status_code == status.HTTP_200_OK, (
            f"Bad response ({response.status_code}, expected 200) {response.text}"
        )
        self.resource.refresh_from_db()
        # TODO: expanded validation here
        for field in instance._meta.concrete_fields:
            if field.name in ("id", "owner", "updated"):
                continue
            if isinstance(field, GeneratedField):
                # don't compare this... it isn't real
                continue
            print(f"checking field {field.name}")
            assert getattr(self.resource, field.name) == getattr(instance, field.name)

    def test_list(self, user_authed_api_client):
        response = user_authed_api_client.get(
            reverse(f"django-ctb-api:{self.basename}-list")
        )
        assert response.status_code == status.HTTP_200_OK, (
            f"Bad response ({response.status_code}, expected 200) {response.text}"
        )

        assert response.json()["results"][0]["id"] == self.resource.id

    def test_list_shortened_for_other_user(self, other_user_authed_api_client):
        if not self.is_owned_resource:
            pytest.skip("not owned resource, test meaningless")

        response = other_user_authed_api_client.get(
            reverse(f"django-ctb-api:{self.basename}-list")
        )
        assert response.status_code == status.HTTP_200_OK, (
            f"Bad response ({response.status_code}, expected 200) {response.text}"
        )
        assert len(response.json()["results"]) == 0

    def test_list_403_for_non_auth(self, api_client):
        response = api_client.get(reverse(f"django-ctb-api:{self.basename}-list"))
        assert response.status_code == status.HTTP_403_FORBIDDEN, (
            f"Bad response ({response.status_code}, expected 403) {response.text}"
        )

    def test_delete(self, user_authed_api_client):
        response = user_authed_api_client.delete(
            reverse(
                f"django-ctb-api:{self.basename}-detail",
                kwargs={"pk": self.resource.id},
            ),
            {"name": "other test project"},
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"Bad response ({response.status_code}, expected 204) {response.text}"
        )
        with pytest.raises(self.model.DoesNotExist):
            self.resource.refresh_from_db()


class TestPackageManyToMany:
    def test_create_accepts_footprints(self, user_authed_api_client, db):
        footprint_names = []
        for _ in range(5):
            footprint_build = fac.FootprintFactory.build()
            print(footprint_build)
            footprint_names.append(footprint_build.name)
        response = user_authed_api_client.post(
            reverse("django-ctb-api:package-list"),
            {
                "technology": 1,
                "name": "test package",
                "footprints": [{"name": fp} for fp in footprint_names],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, (
            f"Bad response ({response.status_code}, expected 201) {response.text}"
        )
        data = response.json()
        created = m.Package.objects.get(id=data["id"])
        print("These footprints are related to the created package:")
        for fp in created.footprints.all():
            deep_print(fp)
        assert {fp.name for fp in created.footprints.all()} == set(footprint_names)

    def test_update_accepts_footprints(self, user_authed_api_client, package):
        footprint_instances = []
        for _ in range(5):
            footprint = fac.FootprintFactory()
            deep_print(footprint)
            footprint_instances.append(footprint)
        update_footprint = fac.FootprintFactory()
        response = user_authed_api_client.patch(
            reverse("django-ctb-api:package-detail", kwargs={"pk": package.id}),
            {
                "footprints": [{"id": fp.id} for fp in footprint_instances]
                + [{"id": update_footprint.id, "name": "some other name"}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, (
            f"Bad response ({response.status_code}, expected 200) {response.text}"
        )
        data = response.json()
        created = m.Package.objects.get(id=data["id"])
        assert set(created.footprints.all()) == set(footprint_instances) | {
            update_footprint  # type: ignore
        }
        assert m.Footprint.objects.get(id=update_footprint.id).name == "some other name"

    def test_update_rejects_unknown_footprints(self, user_authed_api_client, package):
        response = user_authed_api_client.patch(
            reverse("django-ctb-api:package-detail", kwargs={"pk": package.id}),
            {
                "footprints": [{"id": 4000}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Bad response ({response.status_code}, expected 400) {response.text}"
        )


class TestProjectBuildManyToMany:
    def test_create_accepts_excluded_project_parts(
        self, user_authed_api_client, project_version
    ):
        excluded_parts = []
        for _ in range(5):
            project_part = fac.ProjectPartFactory()
            deep_print(project_part)
            excluded_parts.append(project_part)
        response = user_authed_api_client.post(
            reverse("django-ctb-api:project-build-list"),
            {
                "project_version_id": project_version.id,
                "quantity": 1,
                "excluded_project_parts": [{"id": ep.id} for ep in excluded_parts],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, (
            f"Bad response ({response.status_code}, expected 201) {response.text}"
        )
        data = response.json()
        created = m.ProjectBuild.objects.get(id=data["id"])
        print("These excluded_project_parts are related to the created project build:")
        for ep in created.excluded_project_parts.all():
            deep_print(ep)
        assert {ep.id for ep in created.excluded_project_parts.all()} == set(
            [ep.id for ep in excluded_parts]
        )
        created.delete()
        [ep.delete() for ep in excluded_parts]

    def test_update_accepts_excluded_project_parts(
        self, user_authed_api_client, project_build
    ):
        excluded_parts = []
        for _ in range(5):
            excluded_part = fac.ProjectPartFactory()
            deep_print(excluded_part)
            excluded_parts.append(excluded_part)
        update_excluded_part = fac.ProjectPartFactory()
        response = user_authed_api_client.patch(
            reverse(
                "django-ctb-api:project-build-detail", kwargs={"pk": project_build.id}
            ),
            {
                "excluded_project_parts": [{"id": fp.id} for fp in excluded_parts]
                + [{"id": update_excluded_part.id}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, (
            f"Bad response ({response.status_code}, expected 200) {response.text}"
        )
        data = response.json()
        created = m.ProjectBuild.objects.get(id=data["id"])
        assert set(created.excluded_project_parts.all()) == set(excluded_parts) | {
            update_excluded_part  # type: ignore
        }
        [ep.delete() for ep in excluded_parts + [update_excluded_part]]

    def test_update_rejects_unknown_excluded_project_parts(
        self, user_authed_api_client, project_build
    ):
        response = user_authed_api_client.patch(
            reverse(
                "django-ctb-api:project-build-detail", kwargs={"pk": project_build.id}
            ),
            {
                "excluded_project_parts": [{"id": 4000}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Bad response ({response.status_code}, expected 400) {response.text}"
        )


class TestProjectBuildPartReservationManyToMany:
    def test_create_accepts_project_parts(
        self, user_authed_api_client, project_build, part
    ):
        _project_parts = []
        for _ in range(5):
            project_part = fac.ProjectPartFactory(part=part)
            deep_print(project_part)
            _project_parts.append(project_part)
        response = user_authed_api_client.post(
            reverse("django-ctb-api:project-build-part-reservation-list"),
            {
                "project_build_id": project_build.id,
                "part_id": part.id,
                "project_parts": [{"id": ep.id} for ep in _project_parts],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, (
            f"Bad response ({response.status_code}, expected 201) {response.text}"
        )
        data = response.json()
        created = m.ProjectBuildPartReservation.objects.get(id=data["id"])
        print("These project_parts are related to the created project build:")
        for ep in created.project_parts.all():
            deep_print(ep)
        assert {ep.id for ep in created.project_parts.all()} == set(
            [ep.id for ep in _project_parts]
        )
        created.delete()
        [ep.delete() for ep in _project_parts]

    def test_update_accepts_project_parts(
        self, user_authed_api_client, project_build_part_reservation
    ):
        _project_parts = []
        for _ in range(5):
            project_part_part = fac.ProjectPartFactory()
            deep_print(project_part_part)
            _project_parts.append(project_part_part)
        update_project_part = fac.ProjectPartFactory()
        response = user_authed_api_client.patch(
            reverse(
                "django-ctb-api:project-build-part-reservation-detail",
                kwargs={"pk": project_build_part_reservation.id},
            ),
            {
                "project_parts": [{"id": fp.id} for fp in _project_parts]
                + [{"id": update_project_part.id}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, (
            f"Bad response ({response.status_code}, expected 200) {response.text}"
        )
        data = response.json()
        created = m.ProjectBuildPartReservation.objects.get(id=data["id"])
        assert set(created.project_parts.all()) == set(_project_parts) | {
            update_project_part  # type: ignore
        }
        [ep.delete() for ep in _project_parts + [update_project_part]]

    def test_update_rejects_unknown_project_parts(
        self, user_authed_api_client, project_build_part_reservation
    ):
        response = user_authed_api_client.patch(
            reverse(
                "django-ctb-api:project-build-part-reservation-detail",
                kwargs={"pk": project_build_part_reservation.id},
            ),
            {
                "project_parts": [{"id": 4000}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Bad response ({response.status_code}, expected 400) {response.text}"
        )


class ActionTestParam(NamedTuple):
    action_name: str
    service_klass: Any
    action_method_name: str


action_params = [
    ActionTestParam(
        action_name="vendor-part-populate-mouser",
        service_klass=MouserService,
        action_method_name="populate",
    ),
    ActionTestParam(
        action_name="vendor-order-fulfill",
        service_klass=services.VendorOrderService,
        action_method_name="complete_order",
    ),
    ActionTestParam(
        action_name="project-version-sync",
        service_klass=services.ProjectVersionBomService,
        action_method_name="sync",
    ),
    ActionTestParam(
        action_name="project-build-clear-to-build",
        service_klass=services.ProjectBuildService,
        action_method_name="clear_to_build",
    ),
    ActionTestParam(
        action_name="project-build-complete",
        service_klass=services.ProjectBuildService,
        action_method_name="complete_build",
    ),
    ActionTestParam(
        action_name="project-build-cancel",
        service_klass=services.ProjectBuildService,
        action_method_name="cancel_build",
    ),
    ActionTestParam(
        action_name="project-build-generate-vendor-orders",
        service_klass=services.VendorOrderService,
        action_method_name="generate_vendor_orders",
    ),
]


class TestAPIActions:
    action_name: str
    service_klass: Any
    action_method_name: str

    @pytest.fixture(
        autouse=True,
        params=[pytest.param(tup, id=tup.action_name) for tup in action_params],
    )
    def klass_loader(self, request):
        """Load all the parameterized data from the fixture into the test class"""
        request.cls.action_name = request.param.action_name
        request.cls.service_klass = request.param.service_klass
        request.cls.action_method_name = request.param.action_method_name

    def test_action(self, broker, worker, monkeypatch, user_authed_api_client):
        _mock = Mock()
        monkeypatch.setattr(self.service_klass, self.action_method_name, _mock)

        response = user_authed_api_client.post(
            reverse(
                f"django-ctb-api:{self.action_name}",
                kwargs={"pk": 12345},
            ),
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, (
            f"Bad response ({response.status_code}, expected 200) {response.text}"
        )

        broker.join("default")
        worker.join()
        _mock.assert_called_once_with(12345)

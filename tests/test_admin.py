import pytest
from unittest.mock import patch, Mock
from django.http import Http404
from django.contrib import admin as admin_site
from django.shortcuts import reverse
from pytest_django.asserts import assertTemplateUsed

from django_ctb import admin
from django_ctb.mouser.services import MouserService
from django_ctb import models as m
from django_ctb.services import (
    ProjectBuildService,
    VendorOrderService,
    ProjectVersionBomService,
)


@pytest.fixture
def inner_mock():
    return Mock()


@pytest.fixture
def vendor_order_admin(inner_mock):
    return admin.VendorOrderAdmin(
        m.VendorOrder, Mock(admin_view=Mock(return_value=inner_mock))
    )


@pytest.fixture
def vendor_part_admin(inner_mock):
    return admin.VendorPartAdmin(
        m.VendorPart, Mock(admin_view=Mock(return_value=inner_mock))
    )


@pytest.fixture
def project_version_admin(inner_mock):
    return admin.ProjectVersionAdmin(
        m.ProjectVersion, Mock(admin_view=Mock(return_value=inner_mock))
    )


@pytest.fixture
def project_build_admin(inner_mock):
    return admin.ProjectBuildAdmin(
        m.ProjectBuild, Mock(admin_view=Mock(return_value=inner_mock))
    )


class TestExtendibleModelAdminMixin:
    # mixin is too abstract, have to test concrete class
    @patch.object(admin.ProjectVersionAdmin, "get_queryset")
    def test_get_object_missing(self, p_get_queryset):
        p_get_queryset.side_effect = m.ProjectVersion.DoesNotExist
        with pytest.raises(Http404):
            admin.ProjectVersionAdmin(m.ProjectVersion, admin_site)._getobj(None, None)

    @patch.object(admin.ProjectVersionAdmin, "get_queryset")
    def test_get_object_present(self, p_get_queryset):
        p_get_queryset.return_value = Mock(get=Mock(return_value="something"))
        assert (
            admin.ProjectVersionAdmin(m.ProjectVersion, admin_site)._getobj(None, "25")
            == "something"
        )

    def test_view_name(self):
        assert (
            admin.ProjectVersionAdmin(m.ProjectVersion, admin_site)._view_name("snut")
            == "django_ctb_projectversion_snut"
        )

    def test_wrap(self, project_version_admin, inner_mock):
        _callable = project_version_admin._wrap(project_version_admin.bom_view)
        _callable("wild")
        inner_mock.assert_called_once_with("wild")


class TestVendorOrderAdmin:
    def test__compete_order(
        self, vendor_order, broker, worker, monkeypatch, vendor_order_admin
    ):
        call_count = 0

        def patched_complete(*args):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(VendorOrderService, "complete_order", patched_complete)
        vendor_order_admin._complete_order(Mock(), m.VendorOrder.objects.all())

        broker.join("default")
        worker.join()
        assert call_count == 1


class TestVendorPartAdmin:
    def test__populate(
        self, vendor_part, broker, worker, monkeypatch, vendor_part_admin
    ):
        call_count = 0

        def patched_populate(*args):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(MouserService, "populate", patched_populate)
        vendor_part_admin._populate(Mock(), m.VendorPart.objects.all())

        broker.join("default")
        worker.join()
        assert call_count == 1


class TestProjectVersionAdmin:
    def test_bom_view(self, admin_client, project_version):
        response = admin_client.get(
            reverse(
                "admin:django_ctb_projectversion_bom",
                kwargs={"object_id": project_version.pk},
            )
        )
        assertTemplateUsed(response, "admin/django_ctb/project_version_bom.html")

    def test_sync_bom(
        self, project_version, project_version_admin, broker, worker, monkeypatch
    ):
        call_count = 0

        def patched_sync_bom(*args):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(ProjectVersionBomService, "sync", patched_sync_bom)
        project_version_admin.sync_bom(Mock(), m.ProjectVersion.objects.all())

        broker.join("default")
        worker.join()
        assert call_count == 1


class TestProjectBuildAdmin:
    def test_bom_view(self, admin_client, project_build):
        response = admin_client.get(
            reverse(
                "admin:django_ctb_projectbuild_bom",
                kwargs={"object_id": project_build.pk},
            )
        )
        assertTemplateUsed(response, "admin/django_ctb/project_build_bom.html")

    def test__clear_to_build(
        self, project_build, project_build_admin, broker, worker, monkeypatch
    ):
        call_count = 0

        def patched_clear_to_build(*args):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(
            ProjectBuildService, "clear_to_build", patched_clear_to_build
        )
        project_build_admin._clear_to_build(Mock(), m.ProjectBuild.objects.all())

        broker.join("default")
        worker.join()
        assert call_count == 1

    def test__complete_build(
        self, project_build, project_build_admin, broker, worker, monkeypatch
    ):
        call_count = 0

        def patched_complete_build(*args):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(
            ProjectBuildService, "complete_build", patched_complete_build
        )
        project_build_admin._complete_build(Mock(), m.ProjectBuild.objects.all())

        broker.join("default")
        worker.join()
        assert call_count == 1

    def test__cancel_build(
        self, project_build, project_build_admin, broker, worker, monkeypatch
    ):
        call_count = 0

        def patched_cancel_build(*args):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(ProjectBuildService, "cancel_build", patched_cancel_build)
        project_build_admin._cancel_build(Mock(), m.ProjectBuild.objects.all())

        broker.join("default")
        worker.join()
        assert call_count == 1

    def test__generate_vendor_orders(
        self, project_build, project_build_admin, broker, worker, monkeypatch
    ):
        call_count = 0

        def patched_generate_vendor_orders(*args):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(
            VendorOrderService, "generate_vendor_orders", patched_generate_vendor_orders
        )
        project_build_admin._generate_vendor_orders(
            Mock(), m.ProjectBuild.objects.all()
        )

        broker.join("default")
        worker.join()
        assert call_count == 1

import dramatiq

from django_ctb import models
from django_ctb.mouser.services import (
    populate_mouser_vendor_part,
)
from django_ctb.services import (
    ProjectVersionBomService,
    ProjectBuildService,
    VendorOrderService,
)


@dramatiq.actor
def sync_project_version(project_version_pk):
    ProjectVersionBomService().sync(project_version_pk)


@dramatiq.actor
def clear_to_build(project_build_pk):
    ProjectBuildService().clear_to_build(project_build_pk)


@dramatiq.actor
def complete_build(project_build_pk):
    ProjectBuildService().complete_build(project_build_pk)


@dramatiq.actor
def complete_order(vendor_order_pk):
    VendorOrderService().complete_order(vendor_order_pk)


@dramatiq.actor
def cancel_build(project_build_pk):
    ProjectBuildService().cancel_build(project_build_pk)

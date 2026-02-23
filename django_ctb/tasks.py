"""
Dramatiq tasks for performing long-running actions in the background
"""

import dramatiq

from django_ctb.mouser.services import (
    populate_mouser_vendor_part,  # noqa: F401
)
from django_ctb.services import (
    ProjectBuildService,
    ProjectVersionBomService,
    VendorOrderService,
)


@dramatiq.actor
def sync_project_version(project_version_pk):
    """
    Background task to sync the Bill Of Materials (BOM) for a given project
    version. Syncing the BOM will create project parts for each BOM row which
    are linked to a part which matches the attributes of the row. When a
    suitable part cannot be found, a description of the part is included in the
    project part. Implicit project parts will be generated when a known
    footprint is called for (e.g. an LED footprint may create an implicit
    project part for the LED bezel).
    """
    ProjectVersionBomService().sync(project_version_pk)


@dramatiq.actor
def clear_to_build(project_build_pk):
    """
    Background task to reserve parts to cover a project build. Part
    reservations will remove stock from the inventory lines and create
    inventory actions to track. If there is insufficient stock to cover the
    project, a shortage will be associated with the build.
    """
    ProjectBuildService().clear_to_build(project_build_pk)


@dramatiq.actor
def complete_build(project_build_pk):
    """
    Background task to complete a cleared project build. All part reservations
    will be marked as utilized when the project build is completed.
    """
    ProjectBuildService().complete_build(project_build_pk)


@dramatiq.actor
def cancel_build(project_build_pk):
    """
    Background task to cancel a project build. All part reservations will be
    deleted, associated inventory lines credited, and inventory actions
    deleted.
    """
    ProjectBuildService().cancel_build(project_build_pk)


@dramatiq.actor
def generate_vendor_orders(project_build_pks):
    """
    Background task to create vendor orders from project build shortages.
    Prefers to add to existing (unplaced) orders rather than create a new one.
    """
    for project_build_pk in project_build_pks:
        VendorOrderService().generate_vendor_orders(project_build_pk)


@dramatiq.actor
def complete_order(vendor_order_pk):
    """
    Background task to complete a vendor order. All order lines will credit
    the appropriate inventory lines and inventory actions will be created to
    track.
    """
    VendorOrderService().complete_order(vendor_order_pk)

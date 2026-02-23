"""
Services associated with placing and receiving orders from vendors.
"""

import logging
from dataclasses import dataclass

from django.utils import timezone

from django_ctb import models
from django_ctb.exceptions import MissingVendorPart

logger = logging.getLogger(__name__)


@dataclass
class _PartCount:
    part: models.Part
    count: int


class VendorOrderService:
    """
    Service for creating vendor orders, and seeing their fulfillment through
    to altering inventory stock. Provides traceability through inventory
    actions.
    """

    def _complete_order_line(self, order_line):
        # resolve part/inventory line
        inventory_line, _ = models.InventoryLine.objects.get_or_create(
            part=order_line.vendor_part.part, inventory=order_line.for_inventory
        )
        # create inventory action
        models.InventoryAction.objects.create(
            inventory_line=inventory_line,
            delta=order_line.quantity,
            order_line=order_line,
        )
        # update inventory line
        inventory_line.quantity += order_line.quantity
        inventory_line.save()

    def _complete_order(self, order):
        for order_line in order.lines.all():
            self._complete_order_line(order_line)
        order.fulfilled = timezone.now()
        order.save()

    def complete_order(self, order_pk):
        """
        Looks up a vendor order by PK then updates inventory lines for each
        part in the order, creates inventory action with change details.
        Marks vendor order as fulfilled.

        Ignores any vendor order marked fulfilled.
        """
        try:
            order = (
                models.VendorOrder.objects.filter(fulfilled__isnull=True)
                .prefetch_related("lines")
                .get(pk=order_pk)
            )
        except models.VendorOrder.DoesNotExist:
            raise
        self._complete_order(order)

    def _accumulate_shortfalls(self, build: models.ProjectBuild) -> list[_PartCount]:
        _shortfalls = {}
        for shortfall in build.shortfalls.all():
            part = shortfall.part
            _shortfalls.setdefault(part.pk, _PartCount(part=part, count=0))
            _shortfalls[part.pk].count += shortfall.quantity
        return list(_shortfalls.values())

    def _select_vendor_part(self, part: models.Part) -> models.VendorPart:
        logger.info(f">> Need more {part}, searching for best vendor")
        # TODO: should this incorporate the order volume somehow?
        vendor_part = (
            models.VendorPart.objects.filter(part=part).order_by("cost").first()
        )
        if vendor_part is None:
            logger.info(
                f"!! Part {part} does not have a vendor associated, "
                "cannot generate order!"
            )
            raise MissingVendorPart
        return vendor_part

    def _populate_vendor_order(
        self,
        *,
        vendor_part: models.VendorPart,
        quantity: int,
        inventory: models.Inventory,
    ):
        # get (or create) open vendor order for necessary vendor
        vendor_order, _ = models.VendorOrder.objects.get_or_create(
            vendor=vendor_part.vendor,
            placed__isnull=True,
        )
        # create order lines for shortfall
        order_line, _ = models.VendorOrderLine.objects.get_or_create(
            vendor_order=vendor_order,
            vendor_part=vendor_part,
            cost=vendor_part.cost,
            for_inventory=inventory,
            defaults={"quantity": 0},
        )
        order_line.quantity += quantity
        order_line.save()

    def generate_vendor_orders(self, build_pk):
        """
        Looks up a project build by PK then creates or updates vendor
        orders and order lines to cover shortfalls for the given project build.
        Searches for appropriate vendors for each part. Will silently ignore
        parts that don't have vendors.

        Ignores any project build which is completed.
        """
        # get shortfalls
        try:
            build = (
                models.ProjectBuild.objects.filter(completed__isnull=True)
                .prefetch_related("shortfalls")
                .get(pk=build_pk)
            )
        except models.ProjectBuild.DoesNotExist:
            return
        inventory = models.Inventory.objects.first()
        if inventory is None:
            return
        # analyze shortfalls for vendors and item numbers
        _shortfalls = self._accumulate_shortfalls(build)
        for _shortfall in _shortfalls:
            try:
                selected_vendor_part = self._select_vendor_part(_shortfall.part)
            except MissingVendorPart:
                # nothing to do for this part
                continue
            self._populate_vendor_order(
                vendor_part=selected_vendor_part,
                quantity=_shortfall.count,
                inventory=inventory,
            )

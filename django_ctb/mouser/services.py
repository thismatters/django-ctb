"""
Services for interacting with the Mouser Search API
"""

import logging

import dramatiq

from django_ctb import models
from django_ctb.mouser.client import MouserClient, MouserPricebreak

logger = logging.getLogger(__name__)


class MouserService:
    """Get data from the Mouser API to create parts"""

    def _get_price_break(
        self, price_breaks: list[MouserPricebreak]
    ) -> tuple[int, float]:
        volume = 0
        cost = 0.0
        for price_break in price_breaks:
            if volume and volume >= 10:
                break
            volume = price_break.volume
            cost = price_break.cost
        return volume, cost

    def _populate(self, vendor_part: models.VendorPart):
        mouser_part = MouserClient().get_part(vendor_part.item_number)
        vendor_part.url_path = mouser_part.url_path
        # find good price
        volume, cost = self._get_price_break(mouser_part.price_breaks)
        vendor_part.cost = cost
        vendor_part.volume = volume
        vendor_part.save()
        vendor_part.part.name = mouser_part.name
        vendor_part.part.value = mouser_part.name
        vendor_part.part.description = mouser_part.description
        vendor_part.part.save()

    class MissingPart(Exception):
        """The part cannot be located in the Mouser Search API"""

    def _create(self, item_number: str) -> models.VendorPart:
        try:
            mouser_part = MouserClient().get_part(item_number)
        except MouserClient.EmptyResponse:
            raise self.MissingPart
        part, _ = models.Part.objects.get_or_create(
            name=mouser_part.name,
            value=mouser_part.name,
            description=mouser_part.description,
        )
        mouser = models.Vendor.objects.get(name="Mouser")
        volume, cost = self._get_price_break(mouser_part.price_breaks)
        vendor_part, _ = models.VendorPart.objects.update_or_create(
            vendor=mouser,
            part=part,
            item_number=item_number,
            volume=volume,
            cost=cost,
            url_path=mouser_part.url_path,
        )
        return vendor_part

    def populate(self, vendor_part_pk: int):
        """Populate given vendor part with data from Mouser Search API"""
        try:
            vendor_part = models.VendorPart.objects.get(pk=vendor_part_pk)
        except models.VendorPart.DoesNotExist:
            logger.info(f"No vendor part like {vendor_part_pk} found")
            return
        self._populate(vendor_part)


@dramatiq.actor
def populate_mouser_vendor_part(vendor_part_pk: int):
    """Populate given vendor part with data from Mouser Search API"""
    MouserService().populate(vendor_part_pk)


class MouserPartService:
    """
    Service for interacting with local instances of Mouser Part data
    """

    def _get_footprint(self, row: models.BillOfMaterialsRow) -> models.Footprint:
        footprint, _ = models.Footprint.objects.get_or_create(name=row.footprint_name)
        return footprint

    def _get_package(self, row: models.BillOfMaterialsRow) -> models.Package:
        footprint = self._get_footprint(row)
        try:
            package = models.Package.objects.get(footprints=footprint)
        except models.Package.DoesNotExist:
            _, package_name = row.footprint_name.split(":", maxsplit=1)
            package = models.Package.objects.create(
                technology=models.Package.Technology.UNKNOWN,
                name=package_name,
            )
            package.footprints.add(footprint)
        return package

    def _get_part(self, row: models.BillOfMaterialsRow) -> models.Part:
        # I'm waffling about this cascade setup where each method calls
        #   another to get is prereqs. The prereqs could be passed in as
        #   an alternative, but that means that each method must take in a
        #   snowflake parameter (part, package, footprint)
        package = self._get_package(row)
        assert len(row.symbols) == 1
        symbol = list(row.symbols)[0]
        try:
            part = models.Part.objects.get(
                value=row.value, package=package, symbol=symbol
            )
        except models.Part.DoesNotExist:
            part = models.Part.objects.create(
                name="placeholder",
                value=row.value,
                package=package,
                symbol=symbol,
            )
        return part

    def _get_vendor(self) -> models.Vendor:
        return models.Vendor.objects.get(name="Mouser")

    def create_vendor_part(self, row: models.BillOfMaterialsRow) -> models.VendorPart:
        """
        Creates new vendor part for a BOM row, initiates job to populate part
        data from Mouser API
        """
        part = self._get_part(row)
        # create placeholder vendor part
        vendor_part = models.VendorPart.objects.create(
            vendor=self._get_vendor(),
            part=part,
            item_number=row.item_number,
            cost=0.01,
            volume=1,
            url_path="placeholder",
        )
        # send task for worker to populate part/vendor part with API data
        populate_mouser_vendor_part.send(vendor_part.pk)
        # return placeholder vendor part
        return vendor_part

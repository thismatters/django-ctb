import logging
import csv

from django.core.management.base import BaseCommand
from pydantic import BaseModel, Field
from django_ctb import models, services
from django_ctb.mouser.services import MouserService


logger = logging.getLogger(__name__)


class InventoryRow(BaseModel):
    symbol: str = Field(alias="Symbol")
    value: str = Field(alias="Value")
    quantity: int = Field(alias="QTY")
    item_number: str = Field(alias="Part number")
    unit: str = Field(alias="Unit")
    package_name: str = Field(alias="Package")
    vendor_name: str = Field(alias="Vendor")


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("filename")

    def _handle_row(self, *, row: InventoryRow, inventory):
        # look for part
        try:
            vendor_part = models.VendorPart.objects.get(
                vendor__name=row.vendor_name, item_number=row.item_number
            )
        except models.VendorPart.DoesNotExist:
            logger.info(
                f"Couldn't find {row.vendor_name} item number {row.item_number}"
            )
            part = models.Part.objects.filter(
                value=row.value,
                package__name=row.package_name,
                symbol=row.symbol,
            ).first()
        else:
            part = vendor_part.part
        if part is None:
            logger.warning(f"Couldn't find suitable part for row {row}")
            if row.vendor_name == "Mouser":
                try:
                    vendor_part = MouserService()._create(row.item_number)
                except MouserService.MissingPart:
                    logger.warning(f"Couldn't find mouser part {row}")
                    return
                part = vendor_part.part
            else:
                return
        _line, _ = models.InventoryLine.objects.update_or_create(
            inventory=inventory, part=part, defaults={"quantity": row.quantity}
        )
        return _line

    def handle(self, filename, **kwargs):
        inventory = models.Inventory.objects.get(pk=1)
        with open(filename) as inventory_file:
            reader = csv.DictReader(inventory_file)
            for _row in reader:
                row = InventoryRow(**_row)
                if row.quantity == 0:
                    continue
                self._handle_row(row=row, inventory=inventory)

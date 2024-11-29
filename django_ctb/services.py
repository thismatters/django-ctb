import csv
import re
import io
import logging
import zipfile
from contextlib import closing

from django.db.models import Sum
from django.utils import timezone
from pydantic import BaseModel, Field, field_validator, AliasChoices
import requests

from django_ctb import models
from django_ctb.mouser.services import MouserPartService

logger = logging.getLogger(__name__)


class VendorOrderService:
    def _complete_order_line(self, order_line):
        # resolve part/inventory line
        inventory_line, _ = models.InventoryLine.objects.get_or_create(
            part=order_line.vendor_part.part, inventory=order_line.for_inventory
        )
        # create inventory action
        inventory_action = models.InventoryAction.objects.create(
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
        try:
            order = (
                models.VendorOrder.objects.filter(fulfilled__isnull=True)
                .prefetch_related("lines")
                .get(pk=order_pk)
            )
        except models.VendorOrder.DoesNotExist:
            raise
        self._complete_order(order)


class InventoryLineFulfillment:
    def __init__(self, *, inventory_line, depletion):
        self.inventory_line = inventory_line
        self.depletion = depletion

    def execute_fulfillment(self):
        self.inventory_line.quantity -= self.depletion
        self.inventory_line.save()


class PartSatisfaction:
    def __init__(self, *, part, needed):
        self.part = part
        self.needed = needed
        self.unfulfilled = needed
        self.fulfillments = self.calculate_fulfillment()

    def calculate_fulfillment(self) -> list[InventoryLineFulfillment]:
        inventory_lines = models.InventoryLine.objects.filter(
            part=self.part, is_deprioritized=False
        ).order_by("quantity")
        needed_lines = []
        for inventory_line in inventory_lines:
            depletion = min(self.unfulfilled, inventory_line.quantity)
            needed_lines.append(
                InventoryLineFulfillment(
                    inventory_line=inventory_line, depletion=depletion
                )
            )
            self.unfulfilled -= depletion
            if self.unfulfilled == 0:
                break
        return needed_lines


class ProjectBuildPartReservationService:
    def create_reservations(
        self, satisfaction: PartSatisfaction, build: models.ProjectBuild
    ) -> list[models.ProjectBuildPartReservation]:
        reservations = []
        for fulfillment in satisfaction.fulfillments:
            # Do inventory action
            inventory_action = models.InventoryAction.objects.create(
                inventory_line=fulfillment.inventory_line,
                delta=fulfillment.depletion * -1,
                build=build,
            )
            fulfillment.execute_fulfillment()

            # create reservations
            reservations.append(
                models.ProjectBuildPartReservation.objects.create(
                    inventory_action=inventory_action,
                    project_build=build,
                )
            )
        return reservations

    def delete_reservations(self, reservations):
        for reservation in reservations:
            # undo inventory action
            inventory_action = reservation.inventory_action
            if inventory_action is not None:
                reservation.inventory_action = None
                reservation.save()
                inventory_action.inventory_line.quantity -= inventory_action.delta
                inventory_action.inventory_line.save()
                inventory_action.delete()
            reservation.delete()


class ProjectBuildService:
    class InsufficientInventory(Exception):
        def __init__(self, *args, lacking, **kwargs):
            self.lacking = lacking
            super().__init__(*args, **kwargs)

    def _clear_to_build(self, build) -> list[models.ProjectBuildPartReservation]:
        if build.cleared is not None:
            print(f"!! Build already cleared at {build.cleared}")
            return list(
                models.ProjectBuildPartReservation.objects.filter(
                    project_build=build, utilized__isnull=True
                )
            )
        consolodated_project_parts: dict[int, int] = {}
        for project_part in build.project_version.project_parts.all():
            _pk = project_part.part.pk
            consolodated_project_parts.setdefault(
                _pk, {"part": project_part.part, "quantity": 0}
            )
            consolodated_project_parts[_pk]["quantity"] += (
                project_part.quantity * build.quantity
            )

        satisfied = []
        unsatisfied_demand = []
        for _part in consolodated_project_parts.values():
            part = _part["part"]
            quantity_needed = _part["quantity"]
            satisfaction = PartSatisfaction(part=part, needed=quantity_needed)
            if satisfaction.unfulfilled > 0:
                unsatisfied_demand.append(satisfaction)
                models.ProjectBuildPartShortage.objects.create(
                    project_build=build,
                    part=part,
                    quantity=satisfaction.unfulfilled,
                )
            else:
                satisfied.append(satisfaction)

        if unsatisfied_demand:
            print("!! Not clear to build !!")
            print("!! Lacking: ")
            for unsatisfied in unsatisfied_demand:
                _vendor_part = (
                    unsatisfied.part.part_vendors.all().order_by("cost").first()
                )
                print(unsatisfied.part, unsatisfied.unfulfilled)
                if _vendor_part:
                    print(f">> {_vendor_part.vendor.name} {_vendor_part.item_number}")
            raise self.InsufficientInventory(lacking=unsatisfied_demand)

        reservations = []
        for satisfaction in satisfied:
            # create reservation for part
            reservations.extend(
                ProjectBuildPartReservationService().create_reservations(
                    satisfaction=satisfaction, build=build
                )
            )
        build.cleared = timezone.now()
        build.save()
        return reservations

    def _complete_build(self, build):
        if build.completed is not None:
            print(f"!! Build already completed at {build.completed}")
            return
        reservations = self._clear_to_build(build)

        for reservation in reservations:
            reservation.utilized = timezone.now()
            reservation.save()

        build.completed = timezone.now()
        build.save()
        return

    def complete_build(self, build_pk):
        try:
            build = (
                models.ProjectBuild.objects.filter(completed__isnull=True)
                .exclude(cleared__isnull=True)
                .select_related("project_version")
                .prefetch_related("project_version__parts")
                .get(pk=build_pk)
            )
        except models.ProjectBuild.DoesNotExist:
            raise
        return self._complete_build(build)

    def clear_to_build(self, build_pk):
        try:
            build = (
                models.ProjectBuild.objects.filter(completed__isnull=True)
                .select_related("project_version")
                .prefetch_related("project_version__parts")
                .get(pk=build_pk)
            )
        except models.ProjectBuild.DoesNotExist:
            raise
        try:
            return self._clear_to_build(build)
        except self.InsufficientInventory:
            return []

    def _cancel_build(self, build):
        if build.completed is not None:
            print(f"!! Build already completed, cannot cancel")
            return
        ProjectBuildPartReservationService().delete_reservations(
            build.part_reservations.all()
        )
        build.cleared = None
        build.save()

    def cancel_build(self, build_pk):
        try:
            build = (
                models.ProjectBuild.objects.filter(completed__isnull=True)
                # .select_related("part_reservations")
                .prefetch_related("part_reservations").get(pk=build_pk)
            )
        except models.ProjectBuild.DoesNotExist:
            raise
        try:
            return self._cancel_build(build)
        except:
            return


class BillOfMaterialsRow(BaseModel):
    line_number: int | None = Field(validation_alias=AliasChoices("#", "line"))
    references: list[str] = Field(validation_alias=AliasChoices("Reference", "Ref"))
    quantity: int = Field(validation_alias=AliasChoices("Qty", "Qnty"))
    value: str = Field(alias="Value")
    footprint_name: str = Field(alias="Footprint")
    vendor_name: str | None = Field(alias="Vendor", default=None)
    item_number: str | None = Field(alias="PartNum", default=None)

    @property
    def symbols(self):
        return {r.strip("0123456789") for r in self.references}

    @field_validator("value", mode="before")
    @classmethod
    def normalize_value(cls, value: str):
        """3M3 -> 3.3M"""
        matches = re.match(r"(?P<whole>\d+)(?P<prefix>[mMkKuUpPn])(?P<frac>\d+)", value)
        if matches is not None:
            _prefix = matches.group("prefix")
            if _prefix in "UP":
                _prefix = _prefix.lower()
            value = f"{matches.group('whole')}.{matches.group('frac')}" f"{_prefix}"
        return value

    @field_validator("references", mode="before")
    @classmethod
    def split_and_strip(cls, value: str) -> list[str]:
        return [v.strip() for v in value.split(",") if v.strip()]


class ProjectVersionBomService:
    """Downloads BOM from repo at specified commit and creates project
    parts for each line."""

    def _get_vendor_part(self, *, row):
        try:
            vendor_part = models.VendorPart.objects.get(
                vendor__name=row.vendor_name, item_number=row.item_number
            )
        except models.VendorPart.DoesNotExist:
            # such a vendor part will need to exist before this project
            #  bom can be validated
            logger.error(
                f"Project BOM includes vendor specified part which is not "
                f"in parts library: {row.vendor_name}: {row.item_number}"
            )
            # If the vendor is Mouser then the part can be looked up via API
            if row.vendor_name == "Mouser":
                vendor_part = MouserPartService().create_vendor_part(
                    row=row,
                )
            else:
                return None
        return vendor_part

    def _get_matching_parts(self, *, row):
        return (
            models.Part.objects.filter(
                value=row.value,
                package__footprints__name=row.footprint_name,
                symbol__in=row.symbols,
            )
            .exclude(inventory_lines__is_deprioritized=True)
            .annotate(qty_in_inventory=Sum("inventory_lines__quantity"))
            .order_by("-qty_in_inventory")
        )

    def _get_part(self, *, row):
        if row.item_number and row.vendor_name:
            return self._get_vendor_part(row=row).part

        # Consider cases where there is more than one part that satisfies,
        #  e.g. an LED (parts may include a white LED and a green LED).
        #  * Don't choose the part which is deprioritized
        #  * Choose the part which has inventory!

        _part = self._get_matching_parts(row=row).first()
        return _part

    def _sync_footprints(serf, footprint_refs, *, project_part):
        # get rid of any outdated/altered refs
        models.ProjectPartFootprintRef.objects.filter(
            project_part=project_part
        ).exclude(footprint_ref__in=footprint_refs).delete()
        # create any missing refs
        for footprint_ref in footprint_refs:
            models.ProjectPartFootprintRef.objects.get_or_create(
                footprint_ref=footprint_ref, project_part=project_part
            )

    def _sync_implicit_parts(self, *, project_part):
        if project_part.part is None:
            print(
                "Cannot create implicit parts for project_part lacking a "
                f"part {project_part}"
            )
            return
        implicit_project_parts = models.ImplicitProjectPart.objects.filter(
            for_package=project_part.part.package
        )
        project_part_pks = []
        for implicit_project_part in implicit_project_parts:
            print(implicit_project_part)
            quantity = implicit_project_part.quantity * project_part.quantity
            _implicit_project_part, _ = models.ProjectPart.objects.update_or_create(
                project_version=project_part.project_version,
                line_number=project_part.line_number,
                is_implicit=True,
                part=implicit_project_part.part,
                defaults={
                    "quantity": quantity,
                },
            )
            print(f"created implicit project part {_implicit_project_part.pk}")
            project_part_pks.append(_implicit_project_part.pk)
        # clean up any vestiges
        models.ProjectPart.objects.exclude(pk__in=project_part_pks).filter(
            line_number=project_part.line_number, is_implicit=True
        ).delete()

    def _sync_row(self, *, row, project_version):
        _part = self._get_part(row=row)
        defaults = {"part": _part, "quantity": row.quantity}
        if _part is None:
            defaults.update({"missing_part_description": f"{row}"})
        project_part, _ = models.ProjectPart.objects.update_or_create(
            project_version=project_version,
            line_number=row.line_number,
            is_implicit=False,
            defaults=defaults,
        )
        self._sync_footprints(row.references, project_part=project_part)
        self._sync_implicit_parts(project_part=project_part)
        return project_part

    def _build_bom_url(self, project_version):
        # build file url
        # e.g. https://github.com/thismatters/EurorackLfo/raw/main/lfo.csv
        _bom_path = project_version.bom_path
        if not _bom_path.startswith("/"):
            _bom_path = "/" + _bom_path
        _bom_file = (
            project_version.project.git_url
            + "/raw/"
            + project_version.commit_ref
            + _bom_path
        )
        return _bom_file

    def _sync(self, project_version):
        row_errors = {}
        project_part_pks = []
        _bom_url = self._build_bom_url(project_version=project_version)
        print(_bom_url)
        file_response = requests.get(_bom_url)
        with closing(file_response), io.StringIO(
            file_response.content.decode("utf-8")
        ) as bom:
            reader = csv.DictReader(bom)
            print("Parsing csv")
            for line_number, _row in enumerate(reader, start=1):
                if "#" not in _row:
                    _row["#"] = line_number
                row = BillOfMaterialsRow(**_row)
                project_part = self._sync_row(row=row, project_version=project_version)
                if project_part.part is None:
                    logger.warning(f"Part missing for row {row}")
                    logger.warning(row.symbols)
                    row_errors.setdefault("part_missing", []).append(row.line_number)
                project_part_pks.append(project_part.pk)
        print(f"created these project parts {project_part_pks}")
        # remove any outdated lines
        print(
            models.ProjectPart.objects.filter(
                project_version=project_version, is_implicit=False
            )
            .exclude(pk__in=project_part_pks)
            .delete()
        )
        project_version.synced = timezone.now()
        project_version.save()
        return row_errors

    def sync(self, project_version_pk):
        project_version = models.ProjectVersion.objects.get(pk=project_version_pk)
        return self._sync(project_version)

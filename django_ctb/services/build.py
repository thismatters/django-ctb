"""
Services associated with Project Builds; clearing, and completing
"""

import logging

from django.db.models import QuerySet
from django.utils import timezone

from django_ctb import models
from django_ctb.exceptions import InsufficientInventory

logger = logging.getLogger(__name__)


class ProjectBuildPartReservationService:
    """
    Handles deletion of Project Build Part Reservations and restocking of
    inventory lines
    """

    def delete_reservation(self, reservation: models.ProjectBuildPartReservation):
        """
        Deletes reservation after crediting inventory lines and deleting
        inventory actions. Will not act on a utilized reservation.
        """
        if reservation.utilized is not None:
            return

        # undo inventory action
        for inventory_action in reservation.inventory_actions.all():
            inventory_action.inventory_line.quantity -= inventory_action.delta
            inventory_action.inventory_line.save()
            inventory_action.delete()

        reservation.delete()

    def delete_reservations(
        self,
        reservations: list[models.ProjectBuildPartReservation]
        | QuerySet[models.ProjectBuildPartReservation],
    ):
        """
        Deletes reservations after crediting inventory lines and deleting
        inventory actions. Will not act on a utilized reservation.
        """
        for reservation in reservations:
            self.delete_reservation(reservation)


class PartSatisfactionManager:
    """
    Manages satisfaction of combined demand for parts in a project build.
    This is a receptical in which to accumulate project parts which use a
    common part, then to assess the stock of said part (or it's equivalents),
    finally creating reservations or shortages.

    Use ``add_project_part`` to accumulate project parts, then
    use ``ensure_reservation`` to create a reservation (and inventory actions).
    """

    def __init__(
        self,
        *,
        part: models.Part,
        project_build: models.ProjectBuild,
    ):
        """
        Provide a part and a project build. Then use ``add_project_part`` to
        add any project parts which call for the same part. Once all project
        parts are tabulated, call ``ensure_reservation`` to create the actual
        reservation.
        """
        self.part = part
        self.project_build = project_build

        self.fulfilled: int = 0

        # These will be updated post initialization
        self.project_parts: list[models.ProjectPart] = []
        self.needed: int = 0

    @property
    def unfulfilled(self) -> int:
        """Number of parts required for the build which are not yet covered
        by reserved stock."""
        return self.needed - self.fulfilled

    def add_project_part(self, *, project_part: models.ProjectPart):
        """
        Add a project part for consideration in this manager. Increases the
        number of ``needed`` parts, and tracks the project part itself for
        association to the reservation (should it come to pass).
        """
        logger.info(
            "Adding project part: "
            f"{project_part.quantity} * {self.project_build.quantity}"
        )
        self.needed += project_part.quantity * self.project_build.quantity
        self.project_parts.append(project_part)

    def _ensure_inventory_action(
        self,
        *,
        inventory_line: models.InventoryLine,
        depletion: int,
        reservation: models.ProjectBuildPartReservation,
    ) -> models.InventoryAction:
        """
        Idempotent creation of inventory action and update of inventory line
        """
        inventory_action, _ = models.InventoryAction.objects.get_or_create(
            inventory_line=inventory_line,
            reservation=reservation,
            defaults={"delta": 0},
        )
        inventory_action.delta -= depletion
        inventory_action.save()
        inventory_line.quantity -= depletion
        inventory_line.save()
        return inventory_action

    @staticmethod
    def find_equivalent_parts(
        *,
        part: models.Part,
        depth: int = 0,
        maxdepth: int = 5,
    ) -> set[models.Part]:
        """
        Recursively searches for equivalent parts.
        """
        _equivalents = set()
        _equivalents.add(part)
        if depth >= maxdepth:
            return _equivalents
        if part.equivalent_to is not None:
            _equivalents.update(
                PartSatisfactionManager.find_equivalent_parts(
                    part=part.equivalent_to, depth=depth + 1, maxdepth=maxdepth
                )
            )
        others = part.equivalents.all()
        for other in others:
            _equivalents.update(
                PartSatisfactionManager.find_equivalent_parts(
                    part=other, depth=depth + 1, maxdepth=maxdepth
                )
            )
        return _equivalents

    def _get_inventory_lines_queryset(self):
        # determine equivalent parts
        _equivalents = PartSatisfactionManager.find_equivalent_parts(
            part=self.part,
        )

        # get inventory lines for all equivalent parts
        inventory_lines = models.InventoryLine.objects.filter(
            part__in=_equivalents, is_deprioritized=False
        ).order_by("quantity")
        return inventory_lines

    def _debit_inventory_for_reservation(
        self, reservation: models.ProjectBuildPartReservation
    ):
        """
        Handles situations where reservation quantities need to be increased.
        Will create/update inventory actions to cover the full reservation
        quantity.

        Takes stock such that there will be the fewest number of inventory
        lines with stock as possible.
        """
        logger.info(">> Debiting inventory")
        # deduct from inventory lines until need is fulfilled
        for inventory_line in self._get_inventory_lines_queryset():
            depletion = min(self.unfulfilled, inventory_line.quantity)
            self._ensure_inventory_action(
                inventory_line=inventory_line,
                depletion=depletion,
                reservation=reservation,
            )
            self.fulfilled += depletion
            logger.info(
                f">>>> Debiting inventory line {inventory_line} {depletion} parts"
            )
            if self.unfulfilled == 0:
                logger.info(">>>> Reservation satisfied")
                return

    def _credit_inventory_for_reservation(
        self,
        reservation: models.ProjectBuildPartReservation,
    ):
        """
        Return extra parts to stock from reservations such that there will be
        the fewest number of inventory lines with stock. Do not return stock
        to lines with zero stock (unless it is last resort)
        """
        logger.info(">> Crediting inventory")
        actions = reservation.inventory_actions.all().order_by(
            "-inventory_line__quantity", "delta"
        )
        for action in actions:
            # These should both be negative quantities
            credit = max(self.unfulfilled, action.delta) * -1
            action.delta += credit
            action.save()
            action.inventory_line.quantity += credit
            action.inventory_line.save()
            logger.info(
                f">>>> Crediting inventory line {action.inventory_line} {credit} parts"
            )
            if action.delta == 0:
                logger.info(">>>> Inventory action is depleted, deleting")
                action.delete()
            self.fulfilled -= credit
            if self.unfulfilled == 0:
                logger.info(">>>> Reservation satisfied")
                return

    def _check_stock(self):
        """
        Confirms that enough stock is on hand to cover the needed amount of
        parts. Raises ``InsufficientInventory`` otherwise.
        """
        logger.info(f">> Checking stock for {self.part}")
        inventory_lines = self._get_inventory_lines_queryset()
        total_stock = sum(inventory_lines.values_list("quantity", flat=True))
        if self.needed > total_stock:
            logger.info("!!!! Insufficient stock")
            self.fulfilled += total_stock
            shortage, _ = models.ProjectBuildPartShortage.objects.update_or_create(
                part=self.part,
                project_build=self.project_build,
                defaults={"quantity": self.unfulfilled},
            )
            raise InsufficientInventory(shortages=[shortage])

    def ensure_reservation(self) -> models.ProjectBuildPartReservation:
        """
        Idempotent creation of reservations for an individual part to satisfy
        build. Creates inventory actions to trace the reservation, and alters
        inventory line quantities to suit.
        """
        logger.info(f"Ensuring Reservation for {self.project_build} {self.part}")
        reservation = None
        try:
            reservation = models.ProjectBuildPartReservation.objects.get(
                project_build=self.project_build,
                part=self.part,
            )
            # add existing reservation quantity to fulfillment
            logger.info(
                f">> Reservation already exists with quantity {reservation.quantity}"
            )
            self.fulfilled += reservation.quantity
        except models.ProjectBuildPartReservation.DoesNotExist:
            pass

        self._check_stock()
        if reservation is None:
            logger.info(">> Creating Reservation")
            reservation = models.ProjectBuildPartReservation.objects.create(
                project_build=self.project_build,
                part=self.part,
            )
        reservation.project_parts.set(self.project_parts)

        if self.unfulfilled > 0:
            self._debit_inventory_for_reservation(reservation)
        elif self.unfulfilled < 0:
            self._credit_inventory_for_reservation(reservation)
        return reservation


class ProjectBuildService:
    """
    Service for clearing and completing project builds.
    """

    def _consolidate_project_parts(
        self, build: models.ProjectBuild
    ) -> list[PartSatisfactionManager]:
        """
        Consolidate project parts by the actual part (or substitute part)
        called for. Excludes excluded project parts.
        """
        # Get only parts which are actually included in the build
        excluded_project_part_pks = build.excluded_project_parts.all().values_list(
            "pk", flat=True
        )

        # Gather project parts by part (parts may be used on more than one row)
        # Accumulate total quantity required for all rows
        consolidated_project_parts: dict[int, PartSatisfactionManager] = {}
        for project_part in build.project_version.project_parts.all():
            if project_part.pk in excluded_project_part_pks:
                # Do not count this project part, it has been excluded from the build
                continue
            part = project_part.substitute_part or project_part.part
            consolidated_project_parts.setdefault(
                part.pk, PartSatisfactionManager(part=part, project_build=build)
            ).add_project_part(project_part=project_part)
        return list(consolidated_project_parts.values())

    def _clear_to_build(self, build) -> list[models.ProjectBuildPartReservation]:
        """
        Reserves sufficient stock of parts to complete a project, or---barring
        availability---reserves stock of parts which are pletiful enough to
        complete the project build and creates shortages for those unfortunate
        parts which have low stocks (then raises an ``InsufficientInventory``
        exception).
        """
        part_satisfactions = self._consolidate_project_parts(build)

        reservations: list[models.ProjectBuildPartReservation] = []
        shortages: list[models.ProjectBuildPartShortage] = []
        for part_satisfaction in part_satisfactions:
            try:
                reservations.append(part_satisfaction.ensure_reservation())
            except InsufficientInventory as exc:
                shortages.extend(exc.shortages)

        # clean up any resources left over from prior runs
        ProjectBuildPartReservationService().delete_reservations(
            models.ProjectBuildPartReservation.objects.exclude(
                id__in=[res.pk for res in reservations],
            ).filter(project_build=build)
        )
        models.ProjectBuildPartShortage.objects.exclude(
            id__in=[short.pk for short in shortages]
        ).filter(project_build=build).delete()

        # Display shortages for unavailable parts, and bail early
        if shortages:
            logger.info("!! Not clear to build !!")
            logger.info("!! Lacking: ")
            for shortage in shortages:
                _vendor_part = shortage.part.part_vendors.all().order_by("cost").first()
                logger.info(shortage.part, shortage.quantity)
                if _vendor_part:
                    logger.info(
                        f">> {_vendor_part.vendor.name} {_vendor_part.item_number}"
                    )
            raise InsufficientInventory(shortages=shortages)

        # Housekeeping
        build.cleared = timezone.now()
        build.save()
        return reservations

    def _complete_build(self, build):
        logger.info(f"Completing build {build}")
        if build.completed is not None:
            logger.info(f"!! Build already completed at {build.completed}")
            return
        reservations = self._clear_to_build(build)

        for reservation in reservations:
            reservation.utilized = timezone.now()
            reservation.save()

        build.completed = timezone.now()
        build.save()
        return

    def complete_build(self, build_pk):
        """
        Finds a project build by PK then marks it complete. This will mark any
        reservation associated with the project as utilized. Will only find
        project builds which are not complete and have been cleared.
        """
        try:
            build = (
                models.ProjectBuild.objects.filter(completed__isnull=True)
                .exclude(cleared__isnull=True)
                .select_related("project_version")
                .prefetch_related("project_version__project_parts")
                .get(pk=build_pk)
            )
        except models.ProjectBuild.DoesNotExist:
            raise
        return self._complete_build(build)

    def clear_to_build(self, build_pk):
        """
        Finds a project build by PK then reserves sufficient stock of parts to
        complete a project, or---barring availability---reserves stock of parts
        which are pletiful enough to complete the project build and creates
        shortages for those unfortunate parts which have low stocks.

        Ignores any project build which is completed.
        """
        try:
            build = (
                models.ProjectBuild.objects.filter(completed__isnull=True)
                .select_related("project_version")
                .prefetch_related("project_version__project_parts")
                .get(pk=build_pk)
            )
        except models.ProjectBuild.DoesNotExist:
            raise
        try:
            return self._clear_to_build(build)
        except InsufficientInventory:
            return []

    def _cancel_build(self, build):
        logger.info(f"Canceling build {build}")
        if build.completed is not None:
            logger.info("!! Build already completed, cannot cancel")
            return
        ProjectBuildPartReservationService().delete_reservations(
            build.part_reservations.all()
        )
        build.shortfalls.all().delete()
        build.cleared = None
        build.save()

    def cancel_build(self, build_pk):
        """
        Finds a project build by PK then removes any reservations or shortages
        associated with the project. Removes cleared status.

        Ignores any project build which is marked completed.
        """
        build = (
            models.ProjectBuild.objects.filter(completed__isnull=True)
            .prefetch_related("part_reservations")
            .get(pk=build_pk)
        )
        return self._cancel_build(build)

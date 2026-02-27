# ruff: noqa: D100, D101, D102, D107

import logging

from django.utils import timezone

from django_ctb import models

logger = logging.getLogger(__name__)


class PartUsage:
    horizon_days = 90
    horizon_lookback = 3

    def __init__(self, part: models.Part):
        self.part = part
        self.total_used: int = 0
        self.action_count: int = 0
        self.amortized_usage: float = 0
        self.rolling_horizon_usage: float = 0
        self.in_stock: int = 0
        self._tabulate_usage()

    def _tabulate_usage(self):
        # reset just in case this is somehow run a second time...
        self.total_used = 0
        self.action_count = 0
        self.amortized_usage = 0
        self.in_stock = 0
        self.rolling_horizon_usage = 0
        _now = timezone.now()
        horizon_bins = {}
        for inventory_line in self.part.inventory_lines.filter(is_deprioritized=False):
            self.in_stock += inventory_line.quantity
            print("in_stock: ", self.in_stock)
            for action in inventory_line.inventory_actions.all():
                print(action.delta)
                if action.delta > 0:
                    print("should continue")
                    continue
                qty = -1 * action.delta
                self.total_used += qty

                self.action_count += 1
                ### Simple amortization
                days_since = (_now - action.created).total_seconds() / (3600 * 24)
                self.amortized_usage += qty / days_since
                ### Bin usage by distance from planning horizon
                horizon_bin = days_since // self.horizon_days
                horizon_bins.setdefault(horizon_bin, 0)
                horizon_bins[horizon_bin] += qty
        # process rolling horizon
        _buff = 0
        for _bin in range(self.horizon_lookback):
            _buff += horizon_bins.get(_bin, 0)
            self.rolling_horizon_usage += _buff / ((_bin + 1) * self.horizon_lookback)

    @property
    def order_priority(self):
        # return self.amortized_usage / max(0.1, self.in_stock)
        return self.rolling_horizon_usage / max(0.1, self.in_stock)

    @property
    def sort_key(self):
        return (self.order_priority, self.total_used, self.action_count)


class PartAnalyticsService:
    def find_low_stock_parts(self):
        part_usages: list[PartUsage] = []
        for part in models.Part.objects.all():
            # collect rate of usage
            part_usages.append(PartUsage(part=part))
        for usage in sorted(part_usages, key=lambda x: x.sort_key, reverse=True)[:10]:
            if usage.action_count == 0:
                continue
            print(
                usage.part.pk,
                usage.order_priority,
                usage.part.name,
                usage.part.value,
                usage.in_stock,
                usage.part.part_vendors.all().values_list("item_number", flat=True),
                usage.action_count,
                usage.total_used,
            )

    def reconcile_reservations_with_inventory(self):
        reservations = models.ProjectBuildPartReservation.objects.filter(
            utilized__isnull=True
        ).select_related("inventory_action")
        # Gather part quantities
        line_reservations = {}
        for reservation in reservations:
            line_pk = reservation.inventory_action.inventory_line.pk
            line_reservations.setdefault(line_pk, 0)
            line_reservations[line_pk] += reservation.inventory_action.delta * -1
        print(line_reservations)
        # check for potential shortcomings (due to inventory errors)
        for line_pk, total_delta in line_reservations.items():
            line = models.InventoryLine.objects.get(pk=line_pk)
            if total_delta * 0.1 > line.quantity:
                print(f"!! Inventory alert for {line}")

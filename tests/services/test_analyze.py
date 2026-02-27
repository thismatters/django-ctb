import pytest

from django_ctb.services import analyze as sa


class TestPartUsage:
    def test__tabulate_usage__base(self, part, inventory_line_factory):
        inventory_line_factory(part=part, quantity=100)
        part_usage = sa.PartUsage(part=part)
        assert part_usage.part == part
        assert part_usage.action_count == 0
        assert part_usage.total_used == 0
        assert part_usage.amortized_usage == 0
        assert part_usage.rolling_horizon_usage == 0
        assert part_usage.in_stock == 100

    def test__tabulate_usage__regular_usage(
        self, part_factory, inventory_line_factory, inventory_action_factory
    ):
        part = part_factory(name="asdf", symbol="asdf")
        inventory_line = inventory_line_factory(part=part, quantity=100)
        inventory_action_factory(inventory_line=inventory_line, delta=-20, days_ago=45)
        inventory_action_factory(
            inventory_line=inventory_line, delta=-20, days_ago=45 + 90
        )
        inventory_action_factory(
            inventory_line=inventory_line, delta=-20, days_ago=45 + 180
        )
        part_usage = sa.PartUsage(part=part)
        print(
            part_usage.rolling_horizon_usage,
            part_usage.amortized_usage,
            part_usage.in_stock,
            part_usage.order_priority,
        )
        assert part_usage.part == part
        assert part_usage.action_count == 3
        assert part_usage.total_used == 60
        assert part_usage.rolling_horizon_usage == 20
        assert part_usage.amortized_usage == pytest.approx(0.68148148)
        assert part_usage.order_priority == 0.2
        # factory just creates the resource... doesn't do the side effects
        assert part_usage.in_stock == 100

    def test__tabulate_usage__declining_usage(
        self, part_factory, inventory_line_factory, inventory_action_factory
    ):
        part = part_factory(name="asdf", symbol="asdf")
        inventory_line = inventory_line_factory(part=part, quantity=100)
        inventory_action_factory(inventory_line=inventory_line, delta=-10, days_ago=45)
        inventory_action_factory(
            inventory_line=inventory_line, delta=-20, days_ago=45 + 90
        )
        inventory_action_factory(
            inventory_line=inventory_line, delta=-30, days_ago=45 + 180
        )
        part_usage = sa.PartUsage(part=part)
        print(
            part_usage.rolling_horizon_usage,
            part_usage.amortized_usage,
            part_usage.in_stock,
            part_usage.order_priority,
        )
        assert part_usage.part == part
        assert part_usage.action_count == 3
        assert part_usage.total_used == 60
        assert part_usage.rolling_horizon_usage == pytest.approx(15)
        assert part_usage.amortized_usage == pytest.approx(0.5037037)
        assert part_usage.order_priority == pytest.approx(0.15)

    def test__tabulate_usage__increasing_usage(
        self, part_factory, inventory_line_factory, inventory_action_factory
    ):
        part = part_factory(name="asdf", symbol="asdf")
        inventory_line = inventory_line_factory(part=part, quantity=100)
        inventory_action_factory(inventory_line=inventory_line, delta=-30, days_ago=45)
        inventory_action_factory(
            inventory_line=inventory_line, delta=-20, days_ago=45 + 90
        )
        inventory_action_factory(
            inventory_line=inventory_line, delta=-10, days_ago=45 + 180
        )
        part_usage = sa.PartUsage(part=part)
        print(
            part_usage.rolling_horizon_usage,
            part_usage.amortized_usage,
            part_usage.in_stock,
            part_usage.order_priority,
        )
        assert part_usage.part == part
        assert part_usage.action_count == 3
        assert part_usage.total_used == 60
        assert part_usage.rolling_horizon_usage == pytest.approx(25)
        assert part_usage.amortized_usage == pytest.approx(0.8592592)
        assert part_usage.order_priority == pytest.approx(0.25)

    def test__tabulate_usage__positive_action(
        self, part_factory, inventory_line_factory, inventory_action_factory
    ):
        part = part_factory(name="asdf", symbol="asdf")
        inventory_line = inventory_line_factory(part=part, quantity=100)
        inventory_action_factory(inventory_line=inventory_line, delta=20, days_ago=45)
        part_usage = sa.PartUsage(part=part)
        print(
            part_usage.rolling_horizon_usage,
            part_usage.amortized_usage,
            part_usage.in_stock,
            part_usage.order_priority,
        )
        assert part_usage.part == part
        assert part_usage.action_count == 0
        assert part_usage.total_used == 0
        assert part_usage.rolling_horizon_usage == 0
        assert part_usage.amortized_usage == 0
        # factory just creates the resource... doesn't do the side effects
        assert part_usage.in_stock == 100

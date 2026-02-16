import datetime
from decimal import Decimal
from django.utils import timezone

import pytest


class TestPartModel:
    def test_unit_cost_no_vendor(self, part):
        assert part.unit_cost == 0

    def test_unit_cost(self, vendor_part):
        assert vendor_part.part.unit_cost == Decimal("0.0100")


class TestProjectPartModel:
    def test_line_cost__no_part(self, project_part_factory, project_version):
        _project_part = project_part_factory(
            part=None, project_version=project_version, quantity=10
        )
        assert _project_part.line_cost == 0

    def test_line_cost__no_unit_cost(
        self, project_part_factory, project_version, part, vendor_part
    ):
        vendor_part.cost = None
        vendor_part.save()
        _project_part = project_part_factory(
            part=part, project_version=project_version, quantity=10
        )
        assert _project_part.line_cost == 0

    def test_footprints(
        self, project_part, project_part_footprint_ref_factory, project_part_factory
    ):
        """
        :scenario: Footprint Refs are reproduced from BOM Row to Project Part

        | GIVEN an project part represents a BOM row with at least one footprint
        reference
        | WHEN the footprints are gotten from the project part
        | THEN all footprint refs from the BOM row will be represented
        | AND other footprint refs will not be represented
        """
        project_part_footprint_ref_factory(footprint_ref="T1")
        project_part_footprint_ref_factory(footprint_ref="T2")
        project_part_footprint_ref_factory(footprint_ref="T3")
        other_project_part = project_part_factory(
            part=project_part.part, project_version=project_part.project_version
        )
        project_part_footprint_ref_factory(
            project_part=other_project_part, footprint_ref="T4"
        )
        footprints = project_part.footprints
        assert "T1" in footprints
        assert "T2" in footprints
        assert "T3" in footprints
        assert "T4" not in footprints


class TestProjectVersionModel:
    def test_pcb_unit_cost_no_cost(self, project_version):
        project_version.pcb_cost = None
        project_version.save()
        assert project_version.pcb_unit_cost == 0

    def test_pcb_unit_cost(self, project_version):
        assert project_version.pcb_unit_cost == pytest.approx(14.23)

    def test_total_cost(self, project_version, project_part_factory, vendor_part):
        project_part_factory(
            part=vendor_part.part, project_version=project_version, quantity=102
        )
        print(project_version.project_parts.all()[0].quantity)
        print(project_version.project_parts.all()[0].part.unit_cost)
        project_version.refresh_from_db()
        assert float(project_version.total_cost) == pytest.approx(15.25)


class TestInventoryLineModel:
    """
    :feature: Inventory Lines accurately represent stock and facilitate reorder
    """

    def test_item_numbers(
        self, vendor_part_factory, part, inventory_line_factory, part_factory
    ):
        """
        :scenario: Inventory Lines will prominently display Vendor Part item
                   numbers with which they share a Part

        | GIVEN an inventory line represents a part with at least one vendor part
        | WHEN the item numbers are gotten from the inventory line
        | THEN all vendor part item numbers will be represented
        | AND other vendor part item numbers will not be represented
        """
        vendor_part_factory(part=part, item_number="item-1")
        vendor_part_factory(part=part, item_number="item-2")
        vendor_part_factory(part=part, item_number="item-3")
        other_part = part_factory(name="other", symbol="O")
        vendor_part_factory(item_number="item-4", part=other_part)
        inventory_line = inventory_line_factory(part=part, quantity=200)
        item_numbers = inventory_line.item_numbers
        assert "item-1" in item_numbers
        assert "item-2" in item_numbers
        assert "item-3" in item_numbers
        assert "item-4" not in item_numbers

    def test_on_hand(
        self,
        part,
        inventory_line_factory,
        project_build_factory,
        inventory_action_factory,
        vendor_part,
        vendor_order_line_factory,
    ):
        """
        :scenario: The stock of Parts on-hand, including quantities from
                   unutilized Reservations will be visible

        | GIVEN an inventory line with positive quantity
        | AND some number of "order" inventory actions associated to the given
          inventory line
        | AND some number of "build" inventory actions associated to the given
          inventory line for which the build is not cleared
        | AND some number of "build" inventory actions associated to the given
          inventory line for which the build is cleared
        | AND some number of "build" inventory actions associated to the given
          inventory line for which the build is completed
        | WHEN the on hand count is gotten from the given inventory line
        | THEN the number will be the positive quanity on the inventory line less
            the quanitiy indicated by all build actions which are not completed
        """
        inventory_line = inventory_line_factory(part=part, quantity=300)
        inventory_action_factory(
            inventory_line=inventory_line,
            delta=500,
            order_line=vendor_order_line_factory(vendor_part=vendor_part),
        )
        inventory_action_factory(
            inventory_line=inventory_line, delta=-11, build=project_build_factory()
        )
        inventory_action_factory(
            inventory_line=inventory_line, delta=-13, build=project_build_factory()
        )
        inventory_action_factory(
            inventory_line=inventory_line,
            delta=-17,
            build=project_build_factory(cleared=timezone.now()),
        )
        inventory_action_factory(
            inventory_line=inventory_line,
            delta=-19,
            build=project_build_factory(cleared=timezone.now()),
        )
        inventory_action_factory(
            inventory_line=inventory_line,
            delta=-23,
            build=project_build_factory(
                cleared=timezone.now(), completed=timezone.now()
            ),
        )
        inventory_action_factory(
            inventory_line=inventory_line,
            delta=-27,
            build=project_build_factory(
                cleared=timezone.now(), completed=timezone.now()
            ),
        )
        assert inventory_line.quantity_on_hand == 300 + 11 + 13 + 17 + 19


class TestProjectBuildModel:
    def test_is_complete__yes(self, project_build):
        project_build.completed = datetime.datetime.now(datetime.UTC)
        project_build.save()
        assert project_build.is_complete

    def test_is_complete__no(self, project_build):
        project_build.completed = None
        project_build.save()
        assert not project_build.is_complete

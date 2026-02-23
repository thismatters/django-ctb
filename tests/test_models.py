import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from django_ctb.models import BillOfMaterialsRow


class TestPartModel:
    def test_unit_cost_no_vendor(self, part):
        assert part.unit_cost == 0

    def test_unit_cost(self, vendor_part):
        assert vendor_part.part.unit_cost == Decimal("0.0100")


class TestProjectPartModel:
    """
    :feature: Project Parts represent data from a Bill of Materials
    """

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
            part=project_part.part,
            project_version=project_part.project_version,
            is_optional=True,
        )
        project_part_footprint_ref_factory(
            project_part=other_project_part, footprint_ref="T4"
        )
        project_part_footprint_ref_factory(
            project_part=other_project_part, footprint_ref="T5"
        )
        footprints = project_part.footprints
        assert "T1" in footprints
        assert "T2" in footprints
        assert "T3" in footprints
        assert "T4" not in footprints
        assert "T4*, T5*" == other_project_part.footprints


class TestProjectVersionModel:
    """
    :feature: Project Versions map to a git respository and commit
    """

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

    def test_bom_url(self, project_version):
        """
        :scenario: Project Version Bills of Material will be found from Project
                   and Project Version attributes

        | GIVEN a project and project version exist
        | AND these are correctly configured
        | WHEN bom_url is called for that project version
        | THEN a valid URL is returned
        """
        ret = project_version.bom_url
        assert ret == "https://github.com/fake/fake/raw/v0/nested/deep/test.csv"
        assert (
            project_version.bom_url_for_commit("asdfasdf")
            == "https://github.com/fake/fake/raw/asdfasdf/nested/deep/test.csv"
        )


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
        project_build_part_reservation_factory,
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
            inventory_line=inventory_line,
            delta=-11,
            reservation=project_build_part_reservation_factory(),
        )
        inventory_action_factory(
            inventory_line=inventory_line,
            delta=-13,
            reservation=project_build_part_reservation_factory(),
        )
        inventory_action_factory(
            inventory_line=inventory_line,
            delta=-17,
            reservation=project_build_part_reservation_factory(),
        )
        inventory_action_factory(
            inventory_line=inventory_line,
            delta=-19,
            reservation=project_build_part_reservation_factory(),
        )
        inventory_action_factory(
            inventory_line=inventory_line,
            delta=-23,
            reservation=project_build_part_reservation_factory(utilized=timezone.now()),
        )
        inventory_action_factory(
            inventory_line=inventory_line,
            delta=-27,
            reservation=project_build_part_reservation_factory(utilized=timezone.now()),
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


class TestProjectBuildPartReservationModel:
    """
    :feature: Project Build Part Reservations may encapsulate several Inventory
              Actions and Project Parts
    """

    def test_instance_shows_sum_of_action_quantities(
        self,
        project_build_part_reservation,
        inventory_action_factory,
        inventory_line,
    ):
        """
        :scenario: Reservations show full quantity of parts reserved

        | GIVEN a reservation represents more than one inventory action
        | WHEN the reservation quantity is retrieved
        | THEN all inventory action deltas will be represented in the return
        """
        inventory_action_factory(delta=-6, reservation=project_build_part_reservation)
        inventory_action_factory(delta=-9, reservation=project_build_part_reservation)
        assert project_build_part_reservation.quantity == 15
        inventory_action_factory(delta=-420, reservation=project_build_part_reservation)
        assert project_build_part_reservation.quantity == 435

    def test_footprints(
        self,
        project_part,
        project_part_footprint_ref_factory,
        project_part_factory,
        project_build_part_reservation,
    ):
        """
        :scenario: Footprint Refs are reproduced from BOM Row to Project Build
                   Part Reservations via Project Part

        | GIVEN an project part represents a BOM row with at least one footprint
          reference
        | AND another project part with matching part has some other footprint
        | AND the second project part is optional
        | AND both project parts are associated to a build reservation
        | WHEN the footprints are gotten from the build reservation
        | THEN all footprint refs from the BOM row will be represented
        | AND all footprint refs from the second BOM row will be represented
        | AND the second BOM row footprint refs will be marked with asterices (*)
        """
        project_part_footprint_ref_factory(footprint_ref="T1")
        project_part_footprint_ref_factory(footprint_ref="T2")
        project_part_footprint_ref_factory(footprint_ref="T3")
        other_project_part = project_part_factory(
            part=project_part.part,
            project_version=project_part.project_version,
            is_optional=True,
        )
        project_part_footprint_ref_factory(
            project_part=other_project_part, footprint_ref="T4"
        )
        project_part_footprint_ref_factory(
            project_part=other_project_part, footprint_ref="T5"
        )
        project_build_part_reservation.project_parts.set(
            (project_part, other_project_part)
        )

        assert "T1, T2, T3, T4*, T5*" == project_build_part_reservation.footprints

    def test_line_numbers(
        self,
        project_part,
        project_part_footprint_ref_factory,
        project_part_factory,
        project_build_part_reservation,
    ):
        """
        :scenario: Footprint Refs are reproduced from BOM Rows to Part
                   Reservation

        | GIVEN an project part represents a BOM row
        | AND another project part with identical part represents another
          BOM row
        | AND both project parts are associated to a build reservation
        | WHEN the line numbers are gotten from the build reservation
        | THEN line numbers for both BOM rows will be represented
        | AND other line numbers will not be represented
        """
        other_project_part = project_part_factory(
            part=project_part.part,
            project_version=project_part.project_version,
            line_number=2,
        )
        project_part_factory(
            part=project_part.part,
            project_version=project_part.project_version,
            line_number=3,
        )
        project_build_part_reservation.project_parts.set(
            (project_part, other_project_part)
        )

        assert "1, 2" == project_build_part_reservation.line_numbers


class TestBillOfMaterialsRow:
    """
    :feature: Bills of Material will be parsed into a format consistent with
              inventory conventions
    """

    def test_normalize_value(self):
        """
        :scenario: Component values will be converted to decimal notation and SI
                   prefixes greater than 1 will be capitalized

        | GIVEN a component value in a project version BOM is in the format 2K2
        | AND the SI prefix is greater than 1
        | WHEN the BOM is synced
        | THEN the component value will be normalized to 2.2K
        | AND the SI prefix will be capitalized
        """
        row = BillOfMaterialsRow.model_validate(
            {
                "#": 1,
                "Reference": "T1, T2",
                "Qty": 2,
                "PartNum": "ASDF-1234",
                "Vendor": "Mouser",
                "Value": "3M3",
                "Footprint": "Test Footprint",
            }
        )
        assert row.value == "3.3M"

    def test_normalize_value_diode(self):
        """
        :scenario: Component values for diodes will not be altered

        | GIVEN a component value in a project version BOM is in the format 1N4148
        | WHEN the BOM is synced
        | THEN the component value will not be altered
        """
        row = BillOfMaterialsRow.model_validate(
            {
                "#": 1,
                "Reference": "T1, T2",
                "Qty": 2,
                "PartNum": "ASDF-1234",
                "Vendor": "Mouser",
                "Value": "1N4148",
                "Footprint": "Test Footprint",
            }
        )
        assert row.value == "1N4148"

    def test_lower_case_si_prefix(self):
        """
        :scenario: Component values will be converted to decimal notation and SI
                   prefixes less than 1 will be lower-cased

        | GIVEN a component value in a project version BOM is in the format 2U2
        | AND the SI prefix is less than 1
        | WHEN the BOM is synced
        | THEN the component value will be normalized to 2.2u
        | AND the SI prefix will be lower case
        """
        row = BillOfMaterialsRow.model_validate(
            {
                "#": 1,
                "Reference": "T1, T2",
                "Qty": 2,
                "PartNum": "ASDF-1234",
                "Vendor": "Mouser",
                "Value": "3U3",
                "Footprint": "Test Footprint",
            }
        )
        assert row.value == "3.3u"

    def test_silently_ignores_extra_columns(self):
        """
        :scenario: Extra columns in BOM will be silently ignored

        | GIVEN there are unknown columns in the BOM
        | WHEN the BOM is synced
        | THEN the unknown columns are silently ignored
        """
        row = BillOfMaterialsRow.model_validate(
            {
                "#": 1,
                "Reference": "T1, T2",
                "Qty": 2,
                "PartNum": "ASDF-1234",
                "Vendor": "Mouser",
                "Value": "3U3",
                "Footprint": "Test Footprint",
                "asdfsadf": "asdf",
            }
        )
        assert row.value == "3.3u"
        assert not hasattr(row, "asdfsadf")

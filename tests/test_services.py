import requests
import pytest
from django.utils import timezone

from django_ctb import models as m

from django_ctb import services as s
from django_ctb.mouser.services import MouserService


class TestVendorOrderService:
    def test__complete_order_line(
        self, vendor_order_line_factory, vendor_part, inventory
    ):
        """
        GIVEN a vendor order has an order line associated to an inventory
        AND no inventory line exists for the order line part
        WHEN _complete_order_line is run
        THEN an inventory line will be created in the given inventory for the
          order line part
        AND the quantity of parts in the inventory line will be increased by
          the quantity in the inventory line
        AND an inventory line action will be created showing the inventory
          line, the change in quantity, and the vendor order which generated
          the action
        """
        assert len(m.InventoryLine.objects.all()) == 0
        order_line = vendor_order_line_factory(vendor_part=vendor_part, quantity=11)
        s.VendorOrderService()._complete_order_line(order_line)
        assert len(m.InventoryLine.objects.all()) == 1
        assert len(m.InventoryAction.objects.all()) == 1
        inventory_line = m.InventoryLine.objects.all()[0]
        assert inventory_line.quantity == order_line.quantity
        assert inventory_line.part == order_line.vendor_part.part
        assert inventory_line.inventory == inventory
        action = m.InventoryAction.objects.all()[0]
        assert action.inventory_line == inventory_line
        assert action.delta == 11
        assert action.order_line == order_line
        assert action.build is None
        action.delete()
        inventory_line.delete()

    def test__complete_order_line__existing_inventory(
        self, vendor_order_line_factory, vendor_part, inventory_line_factory
    ):
        """
        GIVEN a vendor order has an order line associated to an inventory
        AND an inventory line exists for the order line part
        WHEN _complete_order_line is run
        AND the quantity of parts in the inventory line will be increased by
          the quantity in the inventory line
        AND an inventory line action will be created showing the inventory
          line, the change in quantity, and the vendor order which generated
          the action
        """
        inventory_line = inventory_line_factory(part=vendor_part.part, quantity=3)
        order_line = vendor_order_line_factory(vendor_part=vendor_part, quantity=11)
        s.VendorOrderService()._complete_order_line(order_line)
        inventory_line.refresh_from_db()
        assert inventory_line.quantity == 14
        assert len(m.InventoryAction.objects.all()) == 1
        action = m.InventoryAction.objects.all()[0]
        assert action.inventory_line == inventory_line
        assert action.delta == 11
        assert action.order_line == order_line
        assert action.build is None
        action.delete()

    def test__complete_order(
        self,
        vendor_order_line_factory,
        monkeypatch,
        vendor_part_factory,
        vendor_order,
        part_factory,
    ):
        """
        GIVEN a vendor order exists with several order lines
        WHEN _complete_order is called on the vendor order
        THEN _complete_order_line will be called for each order line
        AND the vendor order will be marked "fulfilled"
        """
        call_args = []

        def fake_complete_order_line(self, order_line):
            call_args.append(order_line)

        order_lines = []
        for idx in range(5):
            part = part_factory(name=f"part{idx}", symbol="R")
            vendor_part = vendor_part_factory(part=part, item_number=f"test-item-{idx}")
            order_lines.append(
                vendor_order_line_factory(vendor_part=vendor_part, quantity=100)
            )

        monkeypatch.setattr(
            s.VendorOrderService, "_complete_order_line", fake_complete_order_line
        )
        s.VendorOrderService()._complete_order(vendor_order)
        vendor_order.refresh_from_db()
        assert vendor_order.fulfilled is not None
        assert call_args == order_lines

    def test_complete_order(self, monkeypatch, vendor_order):
        """
        GIVEN a vendor order exists
        WHEN complete_order is called for the vendor order
        THEN _complete_order is called for the vendor order
        """
        call_count = 0

        def fake_complete_order(self, order):
            assert order == vendor_order
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(
            s.VendorOrderService, "_complete_order", fake_complete_order
        )
        s.VendorOrderService().complete_order(vendor_order.pk)
        assert call_count == 1

    def test_complete_order_bad(self, db):
        """
        WHEN complete_order is called for a non-extant vendor order
        THEN an exception is raised
        """
        with pytest.raises(m.VendorOrder.DoesNotExist):
            s.VendorOrderService().complete_order(1234)

    def test_complete_order_fulfilled(self, vendor_order):
        """
        GIVEN a vendor order exists which has already been fulfilled
        WHEN complete_order is called for the vendor order
        THEN an exception is raised
        """
        vendor_order.fulfilled = timezone.now()
        vendor_order.save()
        with pytest.raises(m.VendorOrder.DoesNotExist):
            s.VendorOrderService().complete_order(vendor_order.pk)

    def test__accumulate_shortfalls(
        self, project_build, part, part_factory, project_build_part_shortage_factory
    ):
        """
        GIVEN a project build exists
        AND the project build has several shortfalls
        WHEN _accumulate_shortfalls is called for the project build
        THEN any shortfalls which share a common part will be gathered into a
          single entry with the sum total of component count
        AND all shortfalls from the build will be represented in the return
        """
        other_part = part_factory(name="other", symbol="O")
        project_build_part_shortage_factory(
            part=part, quantity=6, project_build=project_build
        )
        project_build_part_shortage_factory(
            part=part, quantity=12, project_build=project_build
        )
        project_build_part_shortage_factory(
            part=other_part, quantity=3, project_build=project_build
        )
        shortfalls = list(s.VendorOrderService()._accumulate_shortfalls(project_build))
        assert len(shortfalls) == 2
        if shortfalls[0].part == part:
            assert shortfalls[0].count == 18
            assert shortfalls[1].part == other_part
            assert shortfalls[1].count == 3
        elif shortfalls[1].part == part:
            assert shortfalls[1].count == 18
            assert shortfalls[0].part == other_part
            assert shortfalls[0].count == 3
        else:
            raise Exception("bad shortfalls")

    def test__select_vendor_part(self, part, vendor_part_factory, vendor):
        """
        GIVEN a part exists with more than one vendor part
        WHEN _select_vendor_part is run for the part
        THEN the vendor part with the lowest cost will be returned
        """
        cheapest = vendor_part_factory(cost=0.01, part=part)
        vendor_part_factory(cost=0.02, part=part)
        vendor_part_factory(cost=0.03, part=part)
        selected = s.VendorOrderService()._select_vendor_part(part)
        assert selected == cheapest

    def test__select_vendor_part__none(self, part):
        """
        GIVEN a part exists with no vendor part
        WHEN _select_vendor_part is run for the part
        THEN a MissingVendorPart exception is raised
        """
        with pytest.raises(s.MissingVendorPart):
            s.VendorOrderService()._select_vendor_part(part)

    def test__populate_vendor_order(
        self, vendor_part, vendor, vendor_order, vendor_order_line, inventory
    ):
        """
        GIVEN a vendor part exists for a vendor
        AND a vendor order exists for the given vendor
        AND a vendor order line exists for the part
        WHEN _populate_vendor_order is called for the vendor part providing a
          quantity
        THEN the provided quantity will be added to the existing order line
        """

        assert vendor_order.lines.count() == 1
        s.VendorOrderService()._populate_vendor_order(
            vendor_part=vendor_part, quantity=22, inventory=inventory
        )
        vendor_order_line.refresh_from_db()
        assert vendor_order.lines.count() == 1
        assert vendor_order_line.quantity == 32

    def test__populate_vendor_order__new_line(
        self, vendor_part, vendor_order, inventory
    ):
        """
        GIVEN a vendor part exists for a vendor
        AND a vendor order exists for the given vendor
        AND no vendor order line exists for the part
        WHEN _populate_vendor_order is called for the vendor part providing a quantity
        THEN a vendor order will be created with the given vendor
        AND a vendor order line will be created for the vendor part
        AND the provided quantity will be represented in the order line
        """
        assert vendor_order.lines.count() == 0
        s.VendorOrderService()._populate_vendor_order(
            vendor_part=vendor_part, quantity=22, inventory=inventory
        )
        assert vendor_order.lines.count() == 1
        assert vendor_order.lines.all()[0].quantity == 22
        assert vendor_order.lines.all()[0].vendor_part == vendor_part
        vendor_order.lines.all()[0].delete()

    def test__populate_vendor_order__new_order(self, vendor_part, inventory):
        """
        GIVEN a vendor part exists for a vendor
        AND no vendor order exists for the given vendor
        WHEN _populate_vendor_order is called for the vendor part providing a quantity
        THEN a vendor order will be created with the given vendor
        AND a vendor order line will be created for the vendor part
        AND the provided quantity will be represented in the order line
        """
        assert m.VendorOrder.objects.count() == 0
        s.VendorOrderService()._populate_vendor_order(
            vendor_part=vendor_part, quantity=22, inventory=inventory
        )
        assert m.VendorOrder.objects.count() == 1
        vendor_order = m.VendorOrder.objects.all()[0]
        assert vendor_order.vendor == vendor_part.vendor
        assert vendor_order.lines.count() == 1
        assert vendor_order.lines.all()[0].vendor_part == vendor_part
        assert vendor_order.lines.all()[0].quantity == 22
        vendor_order.lines.all()[0].delete()
        vendor_order.delete()

    def test_generate_vendor_orders(
        self,
        project_build,
        part,
        part_factory,
        project_build_part_shortage_factory,
        vendor_part,
        vendor_mouser,
        vendor_part_factory,
        vendor,
        inventory,
    ):
        """
        GIVEN a project build exists
        AND the project build has several shortfalls to several vendors
        AND the project build has shortfalls for parts with no vendor
        WHEN generate_vendor_orders is called for the project build
        THEN vendor orders will be made to the several vendors
        AND each vendor order will have lines for the parts from that vendor
        AND shortfalls without a vendor will be ignored
        """
        project_build_part_shortage_factory(
            part=part, quantity=6, project_build=project_build
        )
        project_build_part_shortage_factory(
            part=part, quantity=12, project_build=project_build
        )
        other_part = part_factory(name="other", symbol="O")
        vendor_part_factory(part=other_part, vendor=vendor_mouser)
        project_build_part_shortage_factory(
            part=other_part, quantity=3, project_build=project_build
        )
        third_part = part_factory(name="third", symbol="T")
        project_build_part_shortage_factory(
            part=third_part, quantity=21, project_build=project_build
        )

        s.VendorOrderService().generate_vendor_orders(project_build.pk)
        assert m.VendorOrder.objects.count() == 2
        m.VendorOrder.objects.all().delete()
        assert m.VendorOrder.objects.count() == 0

    def test_generate_vendor_orders__no_build(self, db):
        """
        WHEN generate_vendor_orders is called for a non-extant project build
        THEN no vendor orders are generated
        """
        assert m.VendorOrder.objects.count() == 0
        s.VendorOrderService().generate_vendor_orders(1234)
        assert m.VendorOrder.objects.count() == 0

    def test_generate_vendor_orders__no_inventory(self, db, project_build):
        """
        GIVEN a project build exists
        AND no inventory exists
        WHEN generate_vendor_orders is called for the project build
        THEN no vendor orders are generated
        """

        assert m.Inventory.objects.count() == 0
        assert m.VendorOrder.objects.count() == 0
        s.VendorOrderService().generate_vendor_orders(project_build.pk)
        assert m.VendorOrder.objects.count() == 0


class TestProjectBuildService:
    def test_part_satisfaction_no_inventory(self, part, project_part):
        """
        GIVEN a part is used in a project
        AND there is no inventory line for the part
        WHEN the part satisfaction process is run
        THEN no inventory line will be used in fulfillment
        AND there will be unfilfilled need
        """
        satisfaction = s.PartSatisfaction(
            part=part, needed=2, project_part=project_part
        )
        assert satisfaction.needed == 2
        assert satisfaction.unfulfilled == 2
        assert satisfaction.fulfillments == []

    def test_part_satisfaction_insufficient_inventory(
        self, part, inventory_line_factory, project_part
    ):
        """
        GIVEN a part is used in a project
        AND the given part has an inventory line with insufficient stock
        WHEN the part satisfaction process is run
        THEN the inventory line is used for fulfillment
        AND there will be unfilfilled need
        """
        _line = inventory_line_factory(part=part, quantity=1)
        satisfaction = s.PartSatisfaction(
            part=part, needed=2, project_part=project_part
        )
        assert satisfaction.needed == 2
        assert satisfaction.unfulfilled == 1
        assert satisfaction.fulfillments[0].inventory_line == _line
        assert satisfaction.fulfillments[0].depletion == 1

    def test_part_satisfaction_sufficient_inventory(
        self, part, inventory_line_factory, project_part
    ):
        """
        GIVEN a part is used in a project
        AND the given part has two inventory lines with stock
        WHEN the part satisfaction process is run
        THEN the inventory line with the least stock is used for fulfillment
        """
        _other_line = inventory_line_factory(part=part, quantity=5)
        _line = inventory_line_factory(part=part, quantity=3)
        satisfaction = s.PartSatisfaction(
            part=part, needed=2, project_part=project_part
        )
        assert satisfaction.needed == 2
        assert satisfaction.unfulfilled == 0
        assert satisfaction.fulfillments[0].inventory_line == _line
        assert satisfaction.fulfillments[0].depletion == 2

    def test_part_satisfaction_sufficient_inventory_split(
        self, part, inventory_line_factory, project_part
    ):
        """
        GIVEN a part is used in a project
        AND the given part has two inventory lines with stock
        AND one of the inventory lines does not have enough stock for the project
        WHEN the part satisfaction process is run
        THEN the inventory line with the least stock is used for fulfillment first
        AND the inventory line with the most stock is used for the remainder
        """
        _other_line = inventory_line_factory(part=part, quantity=5)
        _line = inventory_line_factory(part=part, quantity=3)
        satisfaction = s.PartSatisfaction(
            part=part, needed=4, project_part=project_part
        )
        assert satisfaction.needed == 4
        assert satisfaction.unfulfilled == 0
        assert satisfaction.fulfillments[0].inventory_line == _line
        assert satisfaction.fulfillments[0].depletion == 3
        assert satisfaction.fulfillments[1].inventory_line == _other_line
        assert satisfaction.fulfillments[1].depletion == 1

    def test_part_satisfaction_sufficient_inventory_deprioritized(
        self, part, inventory_line_factory, project_part
    ):
        """
        GIVEN a part is used in a project
        AND the given part has a deprioritized inventory line with stock
        AND the given part has an inventory line with stock
        WHEN the part satisfaction process is run
        THEN the non deprioritized inventory line will be used
        """
        _line = inventory_line_factory(part=part, quantity=2, is_deprioritized=True)
        _other_line = inventory_line_factory(part=part, quantity=5)
        _third_line = inventory_line_factory(
            part=part, quantity=3, is_deprioritized=True
        )
        satisfaction = s.PartSatisfaction(
            part=part, needed=2, project_part=project_part
        )
        assert satisfaction.needed == 2
        assert satisfaction.unfulfilled == 0
        assert satisfaction.fulfillments[0].inventory_line == _other_line
        assert satisfaction.fulfillments[0].depletion == 2

    def test_clear_to_build_calls__clear_to_build(self, project_build, monkeypatch):
        call_count = 0

        def fake_clear_to_build(self, _build):
            assert _build == project_build
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(
            s.ProjectBuildService, "_clear_to_build", fake_clear_to_build
        )
        s.ProjectBuildService().clear_to_build(project_build.pk)
        assert call_count == 1

    def test_clear_to_build__no_build(self, project_build):
        project_build.completed = timezone.now()
        project_build.save()

        with pytest.raises(m.ProjectBuild.DoesNotExist):
            s.ProjectBuildService().clear_to_build(project_build.pk)

    def test_clear_to_build__insufficient_inventory(self, project_build, monkeypatch):
        def fake_clear_to_build(self, _build):
            raise s.ProjectBuildService.InsufficientInventory(lacking=[])

        monkeypatch.setattr(
            s.ProjectBuildService, "_clear_to_build", fake_clear_to_build
        )
        assert s.ProjectBuildService().clear_to_build(project_build.pk) == []

    def test__clear_to_build(self, project_part, project_build, inventory_line_factory):
        """
        GIVEN a part is used in a project
        AND there is enough stock of the given part to complete the project
        WHEN the project clear to build process is run
        THEN the project will be marked as cleared
        AND a reservation will be made for all the quantity of parts needed
        AND the quantity of the parts will be deducted from the inventory for the part
        """
        _line = inventory_line_factory(part=project_part.part, quantity=10)
        s.ProjectBuildService()._clear_to_build(project_build)
        assert project_build.part_reservations.count() == 1
        assert len(m.InventoryAction.objects.all()) == 1
        action = m.InventoryAction.objects.all()[0]
        assert action.inventory_line == _line
        assert action.delta == -6
        assert action.order_line is None
        assert action.build == project_build
        _line.refresh_from_db()
        assert _line.quantity == 4
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )
        _line.refresh_from_db()
        assert _line.quantity == 10
        assert project_build.cleared is not None

    def test__clear_to_build__not(
        self, project_part, vendor_part, project_build, inventory_line_factory
    ):
        """
        GIVEN a part is used in a project
        AND there is not enough stock of the given part to complete the project
        WHEN the project clear to build process is run
        THEN the project will not be marked clear to build
        AND the part and quantity of shortfall will be persisted
        """
        _line = inventory_line_factory(part=project_part.part, quantity=1)

        with pytest.raises(s.ProjectBuildService.InsufficientInventory):
            s.ProjectBuildService()._clear_to_build(project_build)
        assert project_build.shortfalls.all().count() == 1
        assert project_build.shortfalls.all()[0].quantity == 5
        assert project_build.shortfalls.all()[0].part == project_part.part
        project_build.refresh_from_db
        assert project_build.cleared is None

    def test__clear_to_build__accumulates_by_part(
        self, project_build, project_part_factory, inventory_line_factory, part
    ):
        """
        GIVEN a the same part is used as two separate project parts
        WHEN the project clear to build process is run
        THEN only one reservation for the part will be created
        AND the full quantity of parts will be reserved
        """
        _line = inventory_line_factory(part=part, quantity=10)
        project_part_factory(
            project_version=project_build.project_version,
            part=part,
            quantity=1,
            line_number=2,
        )
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 1
        assert reservations[0].inventory_action.delta == -9
        _line.refresh_from_db()
        assert _line.quantity == 1
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )
        _line.refresh_from_db()
        assert _line.quantity == 10

    def test__clear_to_build__excluded_part(
        self,
        project_part,
        project_build,
        project_part_factory,
        part,
        part_factory,
        inventory_line_factory,
    ):
        """
        GIVEN a project build marks a given part as exluded
        WHEN the project clear to build process is run
        THEN no reservation is made for the excluded part
        """
        _line = inventory_line_factory(part=project_part.part, quantity=10)
        excluded_part = part_factory(name="omitted", symbol="O")
        excluded_project_part = project_part_factory(
            part=excluded_part,
            project_version=project_build.project_version,
            line_number=2,
            quantity=1,
            is_optional=False,
        )
        project_build.excluded_project_parts.add(excluded_project_part)
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 1
        assert reservations[0].inventory_action.inventory_line.part == part
        project_build.excluded_project_parts.clear()
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )

    def test__clear_to_build__equivalent_part(
        self,
        project_part,
        project_build,
        part,
        part_factory,
        inventory_line_factory,
    ):
        """
        GIVEN a project uses a part which is not stocked
        AND the given part is `equivalent_to` another part which is stocked
        WHEN the project clear to build process is run
        THEN the other part will be reserved
        """
        equivalent_part = part_factory(
            name="equivalent", symbol="E", equivalent_to=part
        )
        _line = inventory_line_factory(part=equivalent_part, quantity=10)
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 1
        assert reservations[0].inventory_action.inventory_line.part == equivalent_part
        project_build.excluded_project_parts.clear()
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )

    def test__clear_to_build__equivalent_part_original_part_stocked(
        self,
        project_part,
        project_build,
        part,
        part_factory,
        inventory_line_factory,
    ):
        """
        GIVEN a project uses a part which is stocked
        AND the given part is `equivalent_to` another part which is stocked
        WHEN the project clear to build process is run
        THEN the original part will be reserved
        """
        inventory_line_factory(part=part, quantity=10)
        equivalent_part = part_factory(
            name="equivalent", symbol="E", equivalent_to=part
        )
        _line = inventory_line_factory(part=equivalent_part, quantity=10)
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 1
        assert reservations[0].inventory_action.inventory_line.part == part
        project_build.excluded_project_parts.clear()
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )

    def test__clear_to_build__substitute_part(
        self, project_part, project_build, part, part_factory, inventory_line_factory
    ):
        """
        GIVEN a project uses a part which is stocked
        AND the project part includes a `substitute_part` which is stocked
        WHEN the project clear to build process is run
        THEN the other part will be reserved
        """
        inventory_line_factory(part=part, quantity=10)
        substitute_part = part_factory(name="sub", symbol="S")
        project_part.substitute_part = substitute_part
        project_part.save()
        _line = inventory_line_factory(part=substitute_part, quantity=10)
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 1
        assert reservations[0].inventory_action.inventory_line.part == substitute_part
        project_build.excluded_project_parts.clear()
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )

    def test__clear_to_build__equivalent_substitute_part(
        self, project_part, project_build, part, part_factory, inventory_line_factory
    ):
        """
        GIVEN a project uses a part which is stocked
        AND the project part includes a `substitute_part` which is stocked
        AND the substitute part is `equivalent_to` another part which is stocked
        WHEN the project clear to build process is run
        THEN the equivalent part will be reserved
        """
        inventory_line_factory(part=part, quantity=10)
        substitute_part = part_factory(name="sub", symbol="S")
        equivalent_part = part_factory(
            name="equivalent", symbol="E", equivalent_to=substitute_part
        )
        project_part.substitute_part = substitute_part
        project_part.save()
        _line = inventory_line_factory(part=equivalent_part, quantity=10)
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 1
        assert reservations[0].inventory_action.inventory_line.part == equivalent_part
        project_build.excluded_project_parts.clear()
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )

    def test__complete_build(self, project_part, project_build, inventory_line_factory):
        """
        GIVEN a project build has been cleared
        AND part reservations made
        WHEN the complete build action is run for the project build
        THEN the project build is marked completed
        AND the part reservations are marked utilized
        """
        _line = inventory_line_factory(part=project_part.part, quantity=10)
        project_build.cleared = timezone.now()
        project_build.save()
        reservation = m.ProjectBuildPartReservation.objects.create(
            inventory_action=None,
            project_build=project_build,
        )
        s.ProjectBuildService()._complete_build(project_build)
        reservation.refresh_from_db()
        project_build.refresh_from_db()
        assert reservation.utilized is not None
        assert project_build.completed is not None
        reservation.delete()

    def test__complete_build__no_build(
        self, project_part, project_build, inventory_line_factory, monkeypatch
    ):
        """
        GIVEN a project build has not been cleared
        AND there is not sufficient inventory to build the project
        WHEN the complete build action is run for the project build
        THEN the clear to build action is run for the project build
        AND the project is not marked completed
        """
        _line = inventory_line_factory(part=project_part.part, quantity=2)

        call_count = 0

        def fake_clear_to_build(self, _build):
            assert _build == project_build
            nonlocal call_count
            call_count += 1
            raise s.ProjectBuildService.InsufficientInventory(lacking=[])

        monkeypatch.setattr(
            s.ProjectBuildService, "_clear_to_build", fake_clear_to_build
        )
        with pytest.raises(s.ProjectBuildService.InsufficientInventory):
            s.ProjectBuildService()._complete_build(project_build)
        project_build.refresh_from_db()
        assert project_build.completed is None
        assert call_count == 1

    def test__complete_build__already_completed(self, project_build, monkeypatch):
        """
        GIVEN a project build is marked completed
        WHEN the complete build action is run for the project build
        THEN no operation is run on the project build
        """
        project_build.completed = timezone.now()
        project_build.save()

        call_count = 0

        def fake_clear_to_build(self, _build):
            assert _build == project_build
            nonlocal call_count
            call_count += 1
            raise s.ProjectBuildService.InsufficientInventory(lacking=[])

        monkeypatch.setattr(
            s.ProjectBuildService, "_clear_to_build", fake_clear_to_build
        )

        s.ProjectBuildService()._complete_build(project_build)
        assert call_count == 0

    def test_complete_build_calls__complete_build(self, project_build, monkeypatch):
        call_count = 0
        print(project_build)
        project_build.cleared = timezone.now()
        project_build.save()

        def fake_complete_build(self, _build):
            assert _build == project_build
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(
            s.ProjectBuildService, "_complete_build", fake_complete_build
        )
        s.ProjectBuildService().complete_build(project_build.pk)
        assert call_count == 1

    def test_complete_build__bad(self, project_build, monkeypatch):
        """
        WHEN the complete build action is called for a non existent project build
        THEN an exception is raised
        """
        with pytest.raises(m.ProjectBuild.DoesNotExist):
            s.ProjectBuildService().complete_build(1234)

    def test_cancel_build_calls__cancel_build(self, project_build, monkeypatch):
        call_count = 0

        def fake__cancel_build(self, _build):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(s.ProjectBuildService, "_cancel_build", fake__cancel_build)
        s.ProjectBuildService().cancel_build(project_build.pk)
        assert call_count == 1

    def test__cancel_build(self, project_build, inventory_line_factory, part):
        """
        GIVEN part reservations exist for a project build
        WHEN the cancel build action is run for the project build
        THEN the part reservations are deleted
        AND the inventory lines are credited with the reservation quantities
        AND the project build clear status is cleared
        """
        _line = inventory_line_factory(part=part, quantity=10)
        s.ProjectBuildService()._clear_to_build(project_build)
        project_build.refresh_from_db()
        assert project_build.cleared is not None
        _line.refresh_from_db()
        assert _line.quantity == 4
        s.ProjectBuildService()._cancel_build(project_build)
        _line.refresh_from_db()
        assert _line.quantity == 10
        project_build.refresh_from_db()
        assert project_build.cleared is None

    def test__cancel_build__completed(self, project_build, monkeypatch):
        """
        GIVEN a project build has been completed
        WHEN the cancel build action is run for the project build
        THEN the project build completed status will be unchanged
        """

        def fake_delete_reservations(self, _build):
            assert False

        monkeypatch.setattr(
            s.ProjectBuildPartReservationService,
            "delete_reservations",
            fake_delete_reservations,
        )
        project_build.completed = timezone.now()
        project_build.save()
        s.ProjectBuildService()._cancel_build(project_build)
        project_build.refresh_from_db()
        assert project_build.completed is not None


class TestBillOfMaterialsRow:
    def test_normalize_value(self):
        """
        GIVEN a component value in a project version BOM is in the format 2K2
        AND the SI prefix is greater than 1
        WHEN the BOM is synced
        THEN the component value will be normalized to 2.2K
        AND the SI prefix will be capitalized
        """
        row = s.BillOfMaterialsRow(
            **{
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
        GIVEN a component value in a project version BOM is in the format 1N4148
        WHEN the BOM is synced
        THEN the component value will not be altered
        """
        row = s.BillOfMaterialsRow(
            **{
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
        GIVEN a component value in a project version BOM is in the format 2U2
        AND the SI prefix is less than 1
        WHEN the BOM is synced
        THEN the component value will be normalized to 2.2u
        AND the SI prefix will be lower case
        """
        row = s.BillOfMaterialsRow(
            **{
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


class TestMouserPartService:
    @pytest.fixture
    def bom_row(self):
        row = s.BillOfMaterialsRow(
            **{
                "#": 1,
                "Reference": "T1, T2",
                "Qty": 2,
                "PartNum": "ASDF-1234",
                "Vendor": "Mouser",
                "Value": "great",
                "Footprint": "Test Footprint",
            }
        )
        return row

    def test__get_footprint(self, footprint, bom_row):
        """
        GIVEN a project version BOM row represents a known footprint
        AND the same row shows the vendor as "Mouser"
        WHEN _get_footprint is run for the BOM row
        THEN the known footprint is returned
        """
        _footprint = s.MouserPartService()._get_footprint(bom_row)
        assert footprint == _footprint

    def test__get_footprint_new(self, footprint, bom_row):
        """
        GIVEN a project version BOM row represents an unknown footprint
        AND the same row shows the vendor as "Mouser"
        WHEN _get_footprint is run for the BOM row
        THEN a new footprint matching the unknown footprint is created and returned
        """
        bom_row.footprint_name = "Other Footprint"
        _footprint = s.MouserPartService()._get_footprint(bom_row)
        assert _footprint.name == "Other Footprint"
        assert _footprint != footprint

    def test__get_package(self, package, bom_row):
        """
        GIVEN a project version BOM row represents a known footprint
        AND the same row shows the vendor as "Mouser"
        AND the known footprint has an associated package
        WHEN _get_package is run for the BOM row
        THEN the package for the known footprint is returned
        """
        _package = s.MouserPartService()._get_package(bom_row)
        assert _package == package

    def test__get_package_new(self, package, bom_row):
        """
        GIVEN a project version BOM row represents an unknown footprint
        AND the same row shows the vendor as "Mouser"
        WHEN _get_package is run for the BOM row
        THEN a package (with unknown technology) is created and returned returned
        """
        bom_row.footprint_name = "ASDF:Other Footprint"
        _package = s.MouserPartService()._get_package(bom_row)
        assert _package != package
        assert _package.technology == m.CircuitTechnologyEnum.UNKNOWN
        assert _package.name == "Other Footprint"

    def test__get_part(self, part_factory, bom_row):
        """
        GIVEN a project version BOM row represents a known part
        AND the same row shows the vendor as "Mouser"
        WHEN _get_part is run for the BOM row
        THEN the known part is returned
        """
        part = part_factory(name="Test Part", value="great", symbol="T")
        _part = s.MouserPartService()._get_part(bom_row)
        assert _part == part

    def test__get_part_new(self, part_factory, bom_row, package):
        """
        GIVEN a project version BOM row represents an unknown part
        AND the same row shows the vendor as "Mouser"
        AND the BOM row component package (gleaned from the BOM footprint) is known
        WHEN _get_part is run for the BOM row
        THEN a placeholder part is created which matches the BOM row
        AND the created part references the appropriate component package
        """
        part = part_factory(name="Test Part", value="awful", symbol="T")
        _part = s.MouserPartService()._get_part(bom_row)
        assert _part != part
        assert _part.name == "placeholder"
        assert _part.value == "great"
        assert _part.package == package
        assert _part.symbol == "T"
        _part.delete()

    def test__get_vendor(self, vendor_mouser):
        _mouser = s.MouserPartService()._get_vendor()
        assert _mouser == vendor_mouser

    def test__get_vendor_missing(self, db):
        with pytest.raises(m.Vendor.DoesNotExist):
            s.MouserPartService()._get_vendor()

    def test_create_vendor_part(
        self, bom_row, part_factory, vendor_mouser, broker, worker, monkeypatch
    ):
        """
        GIVEN a project version BOM row represents an unknown part
        AND the same row shows the vendor as "Mouser"
        AND the BOM row component package (gleaned from the BOM footprint) is known
        WHEN create_vendor_part is run for the BOM row
        THEN a placeholder part is created which matches the BOM row
        AND the created part references the appropriate component package
        AND a vendor part is created which references the "PartNum" of the BOM row
        AND a task to populate the vendor part with actual data will be started
        """
        call_count = 0

        def fake_populate(*args, **kwargs):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(MouserService, "populate", fake_populate)
        # This method should _only_ be hit after a part has been found to not
        #   exist, but it should work fine either way.
        _vendor_part = s.MouserPartService().create_vendor_part(bom_row)
        assert _vendor_part.part.name == "placeholder"
        assert _vendor_part.item_number == "ASDF-1234"
        assert _vendor_part.url_path == "placeholder"

        broker.join("default")
        worker.join()
        assert call_count == 1
        _vendor_part.part.delete()
        _vendor_part.delete()


class TestProjectVersionBomService:
    def test__get_vendor_part(self, vendor_part):
        """
        GIVEN a BOM row references a known vendor part by matching the columns
          for "Vendor" and "PartNum"
        WHEN _get_vendor_part is run for that BOM rown
        THEN the known vendor part will be returned
        """
        _vendor_part = s.ProjectVersionBomService()._get_vendor_part(
            row=s.BillOfMaterialsRow(
                **{
                    "#": 1,
                    "Reference": "D1, D2",
                    "Qty": 2,
                    "PartNum": vendor_part.item_number,
                    "Vendor": vendor_part.vendor.name,
                    "Value": "LED",
                    "Footprint": "asdf6789",
                }
            ),
        )
        assert _vendor_part == vendor_part

    def test__get_vendor_part__missing(self, vendor_part):
        """
        GIVEN a BOM row references an unknown vendor part
        AND the "Vendor" for the BOM row is not "Mouser"
        WHEN _get_vendor_part is run for that BOM rown
        THEN a `MissingVendorPart` exception is raised
        """
        with pytest.raises(s.MissingVendorPart):
            _vendor_part = s.ProjectVersionBomService()._get_vendor_part(
                row=s.BillOfMaterialsRow(
                    **{
                        "#": 1,
                        "Reference": "D1, D2",
                        "Qty": 2,
                        "PartNum": vendor_part.item_number,
                        "Vendor": "nothing",
                        "Value": "LED",
                        "Footprint": "asdf6789",
                    }
                ),
            )

    def test__get_vendor_part__missing_mouser(self, vendor_part_mouser, monkeypatch):
        """
        GIVEN a BOM row references an unknown vendor part
        AND the "Vendor" for the BOM row is "Mouser"
        WHEN _get_vendor_part is run for that BOM rown
        THEN the process to create a placeholder vendor part and populate it
          with real data is initiated
        AND the placeholder part is returned
        """

        def fake_create_vendor_part(self, row):
            # SEE: TestMouserPartService.test_create_vendor_part
            return vendor_part_mouser

        monkeypatch.setattr(
            s.MouserPartService, "create_vendor_part", fake_create_vendor_part
        )
        _vendor_part = s.ProjectVersionBomService()._get_vendor_part(
            row=s.BillOfMaterialsRow(
                **{
                    "#": 1,
                    "Reference": "D1, D2",
                    "Qty": 2,
                    "PartNum": "asdf1234",
                    "Vendor": "Mouser",
                    "Value": "LED",
                    "Footprint": "asdf6789",
                }
            ),
        )
        assert _vendor_part == vendor_part_mouser

    def test__get_matching_parts(self, part_factory, footprint):
        """
        GIVEN a BOM row references a value and symbol which describes more than
          one part in the catalog
        WHEN _get_matching_parts is called for the given BOM row
        THEN all catalog parts which match the value and symbol will be returned
        """
        green_led = part_factory(name="LED Green", value="LED", symbol="D")
        white_led = part_factory(name="LED White", value="LED", symbol="D")
        parts = s.ProjectVersionBomService()._get_matching_parts(
            row=s.BillOfMaterialsRow(
                **{
                    "#": 1,
                    "Reference": "D1, D2",
                    "Qty": 2,
                    "PartNum": "asdf1234",
                    "Vendor": "vendor",
                    "Value": "LED",
                    "Footprint": footprint.name,
                }
            ),
        )
        assert green_led in parts
        assert white_led in parts

    def test__get_matching_parts__discriminating(self, part_factory, footprint):
        """
        GIVEN a BOM row references a symbol which describes more than one part
          in the catalog
        AND the BOM row references a value which describes more than one part
          in the catalog
        WHEN _get_matching_parts is called for the given BOM row
        THEN all catalog parts which match the value and symbol will be returned
        AND any catalog partch which do not match the value or symbol will not
          be returned
        """

        log_pot = part_factory(name="Spinny Boi Pot", value="A100K", symbol="RV")
        lin_pot = part_factory(name="Spinny Boi Pot", value="B100K", symbol="RV")
        idk_my_bff_jill = part_factory(
            name="Spinny Boi Pot", value="B100K", symbol="VR"
        )
        parts = s.ProjectVersionBomService()._get_matching_parts(
            row=s.BillOfMaterialsRow(
                **{
                    "#": 1,
                    "Reference": "RV1, RV2",
                    "Qty": 2,
                    "PartNum": "asdf1234",
                    "Vendor": "vendor",
                    "Value": "B100K",
                    "Footprint": footprint.name,
                }
            ),
        )
        assert lin_pot in parts
        assert log_pot not in parts
        assert idk_my_bff_jill not in parts

    def test__get_matching_parts__quantity_sorting(
        self, part_factory, footprint, inventory_line_factory
    ):
        """
        GIVEN a BOM row references a value and symbol which describes more than
          one part in the catalog
        AND the parts are in stock
        WHEN _get_matching_parts is called for the given BOM row
        THEN all catalog parts which match the value and symbol will be returned
        AND the parts will be returned sorted descending by the quantity in stock
        """
        green_led = part_factory(name="LED Green", value="LED", symbol="D")
        purple_led = part_factory(name="LED purple", value="LED", symbol="D")
        white_led = part_factory(name="LED White", value="LED", symbol="D")
        inventory_line_factory(part=green_led, quantity=53)
        inventory_line_factory(part=white_led, quantity=47)
        inventory_line_factory(part=purple_led, quantity=22)
        parts = s.ProjectVersionBomService()._get_matching_parts(
            row=s.BillOfMaterialsRow(
                **{
                    "#": 1,
                    "Reference": "D1, D2",
                    "Qty": 2,
                    "PartNum": "asdf1234",
                    "Vendor": "vendor",
                    "Value": "LED",
                    "Footprint": footprint.name,
                }
            ),
        )
        assert green_led == parts[0]
        assert white_led == parts[1]
        assert purple_led == parts[2]
        assert len(parts) == 3
        for part in parts:
            if part == green_led:
                assert part.qty_in_inventory == 53
            elif part == white_led:
                assert part.qty_in_inventory == 47
            elif part == purple_led:
                assert part.qty_in_inventory == 22

    def test__get_matching_parts__deprioritized(
        self, part_factory, footprint, inventory_line_factory
    ):
        """
        GIVEN a BOM row references a value and symbol which describes more than
          one part in the catalog
        AND any of the parts are marked `is_deprioritized`
        WHEN _get_matching_parts is called for the given BOM row
        THEN no parts marked `is_deprioritized` will be returned
        AND all other catalog parts which match the value and symbol will be
          returned
        """
        green_led = part_factory(name="LED Green", value="LED", symbol="D")
        white_led = part_factory(name="LED white", value="LED", symbol="D")
        inventory_line_factory(part=green_led, quantity=53)
        inventory_line_factory(part=white_led, quantity=22, is_deprioritized=True)
        parts = s.ProjectVersionBomService()._get_matching_parts(
            row=s.BillOfMaterialsRow(
                **{
                    "#": 1,
                    "Reference": "D1, D2",
                    "Qty": 2,
                    "PartNum": "asdf1234",
                    "Vendor": "vendor",
                    "Value": "LED",
                    "Footprint": footprint.name,
                }
            ),
        )
        assert white_led not in parts

    def test__get_part_calls__get_vendor_part(self, monkeypatch, vendor_part):
        """
        GIVEN a BOM row does reference a vendor and part number
        WHEN _get_part is run for that BOM row
        THEN _get_vendor_part is run for that BOM row
        AND the first result is returned
        """
        call_count = 0

        def fake_get_vendor_part(self, *, row):
            assert row.vendor_name == "vendor"
            assert row.item_number == "asdf1234"
            nonlocal call_count
            call_count += 1
            return vendor_part

        monkeypatch.setattr(
            s.ProjectVersionBomService, "_get_vendor_part", fake_get_vendor_part
        )
        part = s.ProjectVersionBomService()._get_part(
            row=s.BillOfMaterialsRow(
                **{
                    "#": 1,
                    "Reference": "F1, F2",
                    "Qty": 2,
                    "PartNum": "asdf1234",
                    "Vendor": "vendor",
                    "Value": "asdf6789",
                    "Footprint": "asdf1234",
                }
            ),
        )
        assert call_count == 1
        assert part == vendor_part.part

    def test__get_part_calls__get_matching_parts(
        self, monkeypatch, part_queryset, part
    ):
        """
        GIVEN a BOM row does not reference either a vendor or a part number
        AND the BOM row references a value and symbol which describes at least
          one part in the catalog
        WHEN _get_part is run for that BOM row
        THEN _get_matching_parts is run for that BOM row
        AND the first result is returned
        """
        call_count = 0

        def fake_get_matching_part(self, *, row):
            assert row.value == "asdf6789"
            assert row.footprint_name == "asdf1234"
            assert row.symbols == {"F"}
            nonlocal call_count
            call_count += 1
            return part_queryset

        monkeypatch.setattr(
            s.ProjectVersionBomService, "_get_matching_parts", fake_get_matching_part
        )
        _part = s.ProjectVersionBomService()._get_part(
            row=s.BillOfMaterialsRow(
                **{
                    "#": 1,
                    "Reference": "F1, F2",
                    "Qty": 2,
                    "PartNum": "asdf",
                    "Vendor": "",
                    "Value": "asdf6789",
                    "Footprint": "asdf1234",
                }
            ),
        )
        assert call_count == 1
        assert _part == part

    def test__get_part__missing(self, monkeypatch):
        """
        GIVEN a BOM row does not reference either a vendor or a part number
        AND th BOM row references a value and symbol which describes no part
        in the catalog
        WHEN _get_part is run for that BOM row
        THEN _get_matching_parts is run for that BOM row
        AND null is returned
        """
        call_count = 0

        def fake_get_matching_part(self, *, row):
            assert row.value == "asdf6789"
            assert row.footprint_name == "asdf1234"
            assert row.symbols == {"F"}
            nonlocal call_count
            call_count += 1
            return m.Part.objects.none()

        monkeypatch.setattr(
            s.ProjectVersionBomService, "_get_matching_parts", fake_get_matching_part
        )
        _part = s.ProjectVersionBomService()._get_part(
            row=s.BillOfMaterialsRow(
                **{
                    "#": 1,
                    "Reference": "F1, F2",
                    "Qty": 2,
                    "PartNum": "",
                    "Vendor": "",
                    "Value": "asdf6789",
                    "Footprint": "asdf1234",
                }
            ),
        )
        assert call_count == 1
        assert _part is None

    def test__build_bom_url(self, project_version):
        """
        GIVEN a project and project version exist
        AND these are correctly configured
        WHEN _build_bom_url is called for that project version
        THEN a valid URL is returned
        """
        ret = s.ProjectVersionBomService()._build_bom_url(project_version)
        assert ret == "https://gitbub.com/fake/fake/raw/v0/nested/deep/test.csv"

    def test__sync_footprints(self, project_part):
        """
        GIVEN a project_part exists which is associated with outdated footprint refs
        WHEN _sync_footprints is run for the project part providing new footprint refs
        THEN existing footprint references which were not provided will be deleted
        AND existing footprint references which are provided will be retained
        AND non-existing footprint references whic are provided will be created
        """
        _old_footprint_ref = m.ProjectPartFootprintRef.objects.create(
            project_part=project_part,
            footprint_ref="F2",
        )
        _old_footprint_ref3 = m.ProjectPartFootprintRef.objects.create(
            project_part=project_part,
            footprint_ref="F3",
        )
        s.ProjectVersionBomService()._sync_footprints(
            {"F1", "F3"}, project_part=project_part
        )
        with pytest.raises(m.ProjectPartFootprintRef.DoesNotExist):
            _old_footprint_ref.refresh_from_db()
        refs = m.ProjectPartFootprintRef.objects.filter(project_part=project_part)
        assert _old_footprint_ref3 in refs
        refs_list = refs.values_list("footprint_ref", flat=True)
        assert "F1" in refs_list
        assert "F3" in refs_list
        assert len(refs_list) == 2

    def test__sync_implicit_parts(
        self,
        project_version,
        part,
        part_factory,
        project_part_factory,
        implicit_project_part_factory,
    ):
        """
        GIVEN a project part references a part
        AND the given part's package is associated with an ImplicitProjectPart
        WHEN _sync_implicit_parts is run for the project part
        THEN a project part is created for the ImplicitProjectPart
        AND the created project part references an appropriate quantity of parts
        AND the created project part has the same line number as the given
          project part
        """
        implicit_part = part_factory(name="implicit part", symbol="IP")
        project_part = project_part_factory(
            project_version=project_version, part=part, line_number=69
        )
        implicit_project_part_factory(
            for_package=part.package, part=implicit_part, quantity=3
        )
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 0
        s.ProjectVersionBomService()._sync_implicit_parts(project_part=project_part)
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        pp = m.ProjectPart.objects.filter(is_implicit=True)[0]
        assert pp.quantity == 6
        assert pp.line_number == project_part.line_number
        pp.delete()

    def test__sync_implicit_parts__remove_old(
        self,
        project_version,
        part,
        part_factory,
        project_part_factory,
        implicit_project_part_factory,
    ):
        """
        GIVEN a BOM has been synced yielding a project part
        AND the project part has an associated implicit project part instance
        AND the ImplicitProjectPart definition has changed such that the
          aforementioned project part instance is no longer representing the
          correct part
        WHEN _sync_implicit_parts is run for the yielded project part
        THEN the old implicit part instance will be deleted
        AND a new implicit part instance reflecting the correct part will be
          created
        """
        implicit_part = part_factory(name="implicit part", symbol="IP")
        old_implicit_part = part_factory(name="old part", symbol="IP")
        project_part = project_part_factory(
            project_version=project_version, part=part, line_number=69
        )
        old_implicit_project_part_instance = project_part_factory(
            project_version=project_version,
            part=old_implicit_part,
            line_number=69,
            is_implicit=True,
        )
        implicit_project_part_factory(
            for_package=part.package, part=implicit_part, quantity=3
        )
        # The old ImplicitProjectPart instance
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        s.ProjectVersionBomService()._sync_implicit_parts(project_part=project_part)
        # The new ImplicitProjectPart instance
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        pp = m.ProjectPart.objects.filter(is_implicit=True)[0]
        assert pp.quantity == 6
        assert pp.line_number == project_part.line_number
        assert pp.part == implicit_part
        with pytest.raises(m.ProjectPart.DoesNotExist):
            old_implicit_project_part_instance.refresh_from_db()
        pp.delete()

    def test__sync_implicit_parts__update(
        self,
        project_version,
        part,
        part_factory,
        project_part_factory,
        implicit_project_part_factory,
    ):
        """
        GIVEN a BOM has been synced yielding a project part
        AND the project part has an associated implicit project part instance
        AND the ImplicitProjectPart definitions has changed such that the
          quantity of implicit parts called for is different
        WHEN _sync_implicit_parts is run for the yielded project part
        THEN the old implicit part instance will be altered to reflect the
          updated quantity
        """
        implicit_part = part_factory(name="implicit part", symbol="IP")
        project_part = project_part_factory(
            project_version=project_version, part=part, line_number=69
        )
        old_project_part = project_part_factory(
            project_version=project_version,
            part=implicit_part,
            line_number=69,
            is_implicit=True,
            quantity=9,
        )
        implicit_project_part_factory(
            for_package=part.package, part=implicit_part, quantity=3
        )
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        s.ProjectVersionBomService()._sync_implicit_parts(project_part=project_part)
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        pp = m.ProjectPart.objects.filter(is_implicit=True)[0]
        assert pp.quantity == 6
        assert pp.line_number == project_part.line_number
        assert pp.part == implicit_part
        assert pp == old_project_part
        pp.delete()

    def test__sync_implicit_parts__multiple(
        self,
        project_version,
        part,
        part_factory,
        project_part_factory,
        implicit_project_part_factory,
    ):
        """
        GIVEN a BOM has been synced yielding a project part
        AND the project part has associated implicit project part instances
        AND the ImplicitProjectPart definitions have not changed
        WHEN _sync_implicit_parts is run for the yielded project part
        THEN the existing implicit part instances will not be altered
        AND no new implicit part instances will be created
        """
        implicit_part = part_factory(name="implicit part", symbol="IP")
        other_implicit_part = part_factory(name="other_implicit part", symbol="IP")
        project_part = project_part_factory(
            project_version=project_version, part=part, line_number=69
        )
        old_project_part = project_part_factory(
            project_version=project_version,
            part=implicit_part,
            line_number=69,
            is_implicit=True,
            quantity=9,
        )
        other_old_project_part = project_part_factory(
            project_version=project_version,
            part=other_implicit_part,
            line_number=69,
            is_implicit=True,
            quantity=2,
        )
        implicit_project_part_factory(
            for_package=part.package, part=implicit_part, quantity=3
        )
        implicit_project_part_factory(
            for_package=part.package, part=other_implicit_part, quantity=2
        )
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 2
        s.ProjectVersionBomService()._sync_implicit_parts(project_part=project_part)
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 2
        pp = m.ProjectPart.objects.filter(is_implicit=True, part=implicit_part)[0]
        assert pp.quantity == 6
        assert pp.line_number == project_part.line_number
        assert pp == old_project_part
        pp.delete()
        opp = m.ProjectPart.objects.filter(is_implicit=True, part=other_implicit_part)[
            0
        ]
        assert opp == other_old_project_part
        assert opp.line_number == project_part.line_number
        assert opp.quantity == 4
        opp.delete()

    def test__sync_row(self, project_version, part, monkeypatch):
        """
        GIVEN a valid BOM row exists for a project version
        AND there exists at least one part which will match the attributes of
          the BOM row
        WHEN _sync_row is run for the BOM row
        THEN a project part will be returned
        AND the project part will reference the aforementioned project version
        AND the project part will reference an a part with matching "Value"
          and reference symbol
        AND the project part will show the correct part quantity for the
          project version
        AND the project part will reference the footprint references from the
          BOM row
        """
        _row = s.BillOfMaterialsRow(
            **{
                "Reference": "A1, A2, A33, D12",
                "#": 69,
                "Qty": 420,
                "PartNum": None,
                "Vendor": None,
                "Value": "asdf6789",
                "Footprint": "asdf1234",
            }
        )

        def fake_get_part(self, *, row):
            assert row.symbols == {"A", "D"}
            assert row == _row
            return part

        monkeypatch.setattr(s.ProjectVersionBomService, "_get_part", fake_get_part)
        project_part = s.ProjectVersionBomService()._sync_row(
            row=_row, project_version=project_version
        )
        assert project_part.project_version == project_version
        assert project_part.part == part
        assert project_part.line_number == 69
        assert project_part.quantity == 420
        refs = project_part.footprint_refs.all()
        assert len(refs) == 4
        _refs = {"A1", "A2", "A33", "D12"}
        for ref in refs:
            _refs.remove(ref.footprint_ref)
        assert len(_refs) == 0
        project_part.delete()

    def test__sync_row__missing_vendor_part(self, project_version, monkeypatch):
        """
        GIVEN a valid BOM row exists for a project version
        AND there does not exist any part which will match the attributes of
          the BOM row
        WHEN _sync_row is run for the BOM row
        THEN a project part will be returned
        AND the project part will reference the aforementioned project version
        AND the project part will have a missing part description which
          possesses the information in the BOM row
        AND the project part will not have a reference to a part
        """
        _row = s.BillOfMaterialsRow(
            **{
                "Reference": "A1, A2, A33, D12",
                "#": 69,
                "Qty": 420,
                "PartNum": "real-part",
                "Vendor": "AmazingVendor",
                "Value": "asdf6789",
                "Footprint": "asdf1234",
            }
        )

        def fake_get_part(self, *, row):
            raise s.MissingVendorPart

        monkeypatch.setattr(s.ProjectVersionBomService, "_get_part", fake_get_part)
        project_part = s.ProjectVersionBomService()._sync_row(
            row=_row, project_version=project_version
        )
        assert project_part.project_version == project_version
        assert project_part.part is None
        assert project_part.missing_part_description is not None
        project_part.delete()

    def test__sync(self, project_version, monkeypatch, project_part_factory, part):
        """
        GIVEN a BOM has been synced yielding project parts
        AND the BOM has been altered such that there are now fewer rows
        WHEN _sync is run for the BOM
        THEN _sync_row will be run for each row of the BOM
        AND any project parts associated with a row removed from the BOM will
          be deleted
        AND any project parts associated with a retained row from the BOM will
          be retained
        """

        class Closable:
            def __init__(self, content):
                self.content = content

            def close(self):
                pass

        def fake_get(url):
            return Closable(
                b"""Qty,Reference,Vendor,PartNum,Footprint,Value
3,"A1, A2, A3","test vendor","test-item-number","Test Footprint","asdf"
"""
            )

        def fake_bom_url(self, project_version):
            return "hyup"

        _real_project_part = project_part_factory(
            project_version=project_version, part=part
        )
        _bad_project_part = project_part_factory(
            project_version=project_version, part=part
        )

        _sync_row_call_count = 0

        def fake_sync_row(self, *, row, project_version):
            nonlocal _sync_row_call_count
            _sync_row_call_count += 1
            return _real_project_part

        monkeypatch.setattr(s.ProjectVersionBomService, "_build_bom_url", fake_bom_url)
        monkeypatch.setattr(s.ProjectVersionBomService, "_sync_row", fake_sync_row)
        monkeypatch.setattr(requests, "get", fake_get)

        s.ProjectVersionBomService()._sync(project_version)
        with pytest.raises(m.ProjectPart.DoesNotExist):
            _bad_project_part.refresh_from_db()
        _project_parts = project_version.project_parts.all()
        assert len(_project_parts) == 1
        assert _real_project_part in _project_parts
        assert _sync_row_call_count == 1

    def test__sync__missing_part(
        self, project_version, monkeypatch, project_part_factory, part
    ):
        """
        GIVEN a BOM for a project version has not been synced
        AND project parts exist for that project version anyhow
        AND the BOM calls for a part which does not exist
        WHEN _sync is run for the BOM
        THEN _sync_row will be run for each row of the BOM
        AND any project parts which are not associatew with a BOM row will
          be deleted
        AND project parts will be created for each row in the BOM
        AND project parts created without a matching part will have a missing
          part description with all details from the BOM row
        """

        class Closable:
            def __init__(self, content):
                self.content = content

            def close(self):
                pass

        def fake_get(url):
            return Closable(
                b"""#,Qty,Reference,Vendor,PartNum,Footprint,Value
1,3,"A1, A2, A3",,,"Unknown Footprint","zxcv"
"""
            )

        def fake_bom_url(self, project_version):
            return "hyup"

        _bad_project_part = project_part_factory(
            project_version=project_version, part=part, line_number=2
        )
        print(_bad_project_part)
        print(_bad_project_part.line_number)
        # def fake_sync_row(self, *, row, project_version):
        #     raise s.ProjectVersionBomService.PartMissing("blah")

        monkeypatch.setattr(s.ProjectVersionBomService, "_build_bom_url", fake_bom_url)
        # monkeypatch.setattr(s.ProjectVersionBomService, "_sync_row", fake_sync_row)
        monkeypatch.setattr(requests, "get", fake_get)

        s.ProjectVersionBomService()._sync(project_version)
        with pytest.raises(m.ProjectPart.DoesNotExist):
            _bad_project_part.refresh_from_db()
        _project_parts = project_version.project_parts.all()
        assert len(_project_parts) == 1
        assert _project_parts[0].part is None
        assert _project_parts[0].missing_part_description is not None

    def test_sync_calls__sync(self, project_version, monkeypatch):
        call_count = 0

        def fake_sync(self, _project_version):
            nonlocal call_count
            call_count += 1
            assert project_version == _project_version
            return {}

        monkeypatch.setattr(s.ProjectVersionBomService, "_sync", fake_sync)
        s.ProjectVersionBomService().sync(project_version.pk)
        assert call_count == 1


class TestPartUsage:
    def test__tabulate_usage__base(self, part, inventory_line_factory):
        inventory_line_factory(part=part, quantity=100)
        part_usage = s.PartUsage(part=part)
        assert part_usage.part == part
        assert part_usage.action_count == 0
        assert part_usage.total_used == 0
        assert part_usage.amortized_usage == 0
        assert part_usage.rolling_horizon_usage == 0
        assert part_usage.in_stock == 100

    def test__tabulate_usage__regular_usage(
        self, part, inventory_line_factory, inventory_action_factory
    ):
        inventory_line = inventory_line_factory(part=part, quantity=100)
        inventory_action_factory(inventory_line=inventory_line, delta=-20, days_ago=45)
        inventory_action_factory(
            inventory_line=inventory_line, delta=-20, days_ago=45 + 90
        )
        inventory_action_factory(
            inventory_line=inventory_line, delta=-20, days_ago=45 + 180
        )
        part_usage = s.PartUsage(part=part)
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
        self, part, inventory_line_factory, inventory_action_factory
    ):
        inventory_line = inventory_line_factory(part=part, quantity=100)
        inventory_action_factory(inventory_line=inventory_line, delta=-10, days_ago=45)
        inventory_action_factory(
            inventory_line=inventory_line, delta=-20, days_ago=45 + 90
        )
        inventory_action_factory(
            inventory_line=inventory_line, delta=-30, days_ago=45 + 180
        )
        part_usage = s.PartUsage(part=part)
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
        self, part, inventory_line_factory, inventory_action_factory
    ):
        inventory_line = inventory_line_factory(part=part, quantity=100)
        inventory_action_factory(inventory_line=inventory_line, delta=-30, days_ago=45)
        inventory_action_factory(
            inventory_line=inventory_line, delta=-20, days_ago=45 + 90
        )
        inventory_action_factory(
            inventory_line=inventory_line, delta=-10, days_ago=45 + 180
        )
        part_usage = s.PartUsage(part=part)
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
        self, part, inventory_line_factory, inventory_action_factory
    ):
        inventory_line = inventory_line_factory(part=part, quantity=100)
        inventory_action_factory(inventory_line=inventory_line, delta=20, days_ago=45)
        part_usage = s.PartUsage(part=part)
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

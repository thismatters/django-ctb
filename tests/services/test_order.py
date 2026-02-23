from unittest.mock import Mock, call

import pytest
from django.utils import timezone

from django_ctb import models as m
from django_ctb import services as s
from django_ctb.exceptions import MissingVendorPart

# TODO: update monkeypatch usage here


class TestVendorOrderService:
    """
    :feature: Vendor Orders can be generated and fulfilled
    """

    def test__complete_order_line(
        self, vendor_order_line_factory, vendor_part, inventory
    ):
        """
        :scenario: Completing an Order Line will create Inventory Line if necessary
                   and create an Inventory Action

        | GIVEN a vendor order has an order line associated to an inventory
        | AND no inventory line exists for the order line part
        | WHEN _complete_order_line is run
        | THEN an inventory line will be created in the given inventory for the
          order line part
        | AND the quantity of parts in the inventory line will be increased by
          the quantity in the inventory line
        | AND an inventory line action will be created showing the inventory
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
        assert action.reservation is None
        action.delete()
        inventory_line.delete()

    def test__complete_order_line__existing_inventory(
        self, vendor_order_line_factory, vendor_part, inventory_line_factory
    ):
        """
        :scenario: Complete Order Line Process will update an Inventory Line and
                   create an Inventory Action

        | GIVEN a vendor order has an order line associated to an inventory
        | AND an inventory line exists for the order line part
        | WHEN _complete_order_line is run
        | AND the quantity of parts in the inventory line will be increased by
          the quantity in the inventory line
        | AND an inventory line action will be created showing the inventory
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
        assert action.reservation is None
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
        :scenario: Complete Vendor Order Process will complete each Order Line and
                   fulfill the Vendor Order

        | GIVEN a vendor order exists with several order lines
        | WHEN _complete_order is called on the vendor order
        | THEN _complete_order_line will be called for each order line
        | AND the vendor order will be marked "fulfilled"
        """
        order_lines = []
        for idx in range(5):
            part = part_factory(name=f"part{idx}", symbol="R")
            vendor_part = vendor_part_factory(part=part, item_number=f"test-item-{idx}")
            order_lines.append(
                vendor_order_line_factory(vendor_part=vendor_part, quantity=100)
            )
        mock_complete_order_line = Mock()
        monkeypatch.setattr(
            s.VendorOrderService, "_complete_order_line", mock_complete_order_line
        )
        s.VendorOrderService()._complete_order(vendor_order)
        vendor_order.refresh_from_db()
        assert vendor_order.fulfilled is not None
        mock_complete_order_line.assert_has_calls([call(line) for line in order_lines])

    def test_complete_order(self, monkeypatch, vendor_order):
        """
        :scenario: Complete Vendor Order Wrapper Completes only existing
                   Vendor Orders

        | GIVEN a vendor order exists
        | WHEN complete_order is called for the vendor order
        | THEN _complete_order is called for the vendor order
        """
        mock_complete_order = Mock()
        monkeypatch.setattr(
            s.VendorOrderService, "_complete_order", mock_complete_order
        )
        s.VendorOrderService().complete_order(vendor_order.pk)
        mock_complete_order.assert_called_once_with(vendor_order)

    def test_complete_order_bad(self, db):
        """
        :scenario: Complete Vendor Order Wrapper raises error for non-extant
                   Vendor Orders

        | WHEN complete_order is called for a non-extant vendor order
        | THEN an exception is raised
        """
        with pytest.raises(m.VendorOrder.DoesNotExist):
            s.VendorOrderService().complete_order(1234)

    def test_complete_order_fulfilled(self, vendor_order):
        """
        :scenario: Complete Vendor Order Wrapper raises error for already
                   fulfilled Vendor Orders

        | GIVEN a vendor order exists which has already been fulfilled
        | WHEN complete_order is called for the vendor order
        | THEN an exception is raised
        """
        vendor_order.fulfilled = timezone.now()
        vendor_order.save()
        with pytest.raises(m.VendorOrder.DoesNotExist):
            s.VendorOrderService().complete_order(vendor_order.pk)

    def test__accumulate_shortfalls(
        self, project_build, part, part_factory, project_build_part_shortage_factory
    ):
        """
        :scenario: Project Build Shortfalls will be binned by Part

        | GIVEN a project build exists
        | AND the project build has several shortfalls
        | WHEN _accumulate_shortfalls is called for the project build
        | THEN any shortfalls which share a common part will be gathered into a
          single entry with the sum total of component count
        | AND all shortfalls from the build will be represented in the return
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
        :scenario: Select Vendor Part Process prefers the cheapest Vendor for
                   the given Part

        | GIVEN a part exists with more than one vendor part
        | WHEN _select_vendor_part is run for the part
        | THEN the vendor part with the lowest cost will be returned
        """
        cheapest = vendor_part_factory(cost=0.01, part=part)
        vendor_part_factory(cost=0.02, part=part)
        vendor_part_factory(cost=0.03, part=part)
        selected = s.VendorOrderService()._select_vendor_part(part)
        assert selected == cheapest

    def test__select_vendor_part__none(self, part):
        """
        :scenario: Select Vendor Part Process raises when it finds no Part

        | GIVEN a part exists with no vendor part
        | WHEN _select_vendor_part is run for the part
        | THEN a MissingVendorPart exception is raised
        """
        with pytest.raises(MissingVendorPart):
            s.VendorOrderService()._select_vendor_part(part)

    def test__populate_vendor_order(
        self, vendor_part, vendor, vendor_order, vendor_order_line, inventory
    ):
        """
        :scenario: Populate Vendor Order Process will add to an existing Order
                   Line if one exists for a Part

        | GIVEN a vendor part exists for a vendor
        | AND a vendor order exists for the given vendor
        | AND a vendor order line exists for the part
        | WHEN _populate_vendor_order is called for the vendor part providing a
          quantity
        | THEN the provided quantity will be added to the existing order line
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
        :scenario: Populate Vendor Order Process will create a new Order Line
                   in an existing Vendor Order as needed.

        | GIVEN a vendor part exists for a vendor
        | AND a vendor order exists for the given vendor
        | AND no vendor order line exists for the part
        | WHEN _populate_vendor_order is called for the vendor part providing a quantity
        | THEN a vendor order will be created with the given vendor
        | AND a vendor order line will be created for the vendor part
        | AND the provided quantity will be represented in the order line
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
        :scenario: Populate Vendor Order Process will create a new Vendor Order
                   when no open Vendor Order exists.

        | GIVEN a vendor part exists for a vendor
        | AND no vendor order exists for the given vendor
        | WHEN _populate_vendor_order is called for the vendor part providing a quantity
        | THEN a vendor order will be created with the given vendor
        | AND a vendor order line will be created for the vendor part
        | AND the provided quantity will be represented in the order line
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
        :scenario: Generate Vendor Orders Process will create Vendor Orders and
                   Order Lines to satisfy any Shortfalls for a Project Build

        | GIVEN a project build exists
        | AND the project build has several shortfalls to several vendors
        | AND the project build has shortfalls for parts with no vendor
        | WHEN generate_vendor_orders is called for the project build
        | THEN vendor orders will be made to the several vendors
        | AND each vendor order will have lines for the parts from that vendor
        | AND shortfalls without a vendor will be ignored
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
        :scenario: Generate Vendor Orders Proces will ignore non-extand Project
                   Builds

        | WHEN generate_vendor_orders is called for a non-extant project build
        | THEN no vendor orders are generated
        """
        assert m.VendorOrder.objects.count() == 0
        s.VendorOrderService().generate_vendor_orders(1234)
        assert m.VendorOrder.objects.count() == 0

    def test_generate_vendor_orders__no_inventory(self, db, project_build):
        """
        :scenario: Generate Vendor Orders Process requires Inventory

        | GIVEN a project build exists
        | AND no inventory exists
        | WHEN generate_vendor_orders is called for the project build
        | THEN no vendor orders are generated
        """

        assert m.Inventory.objects.count() == 0
        assert m.VendorOrder.objects.count() == 0
        s.VendorOrderService().generate_vendor_orders(project_build.pk)
        assert m.VendorOrder.objects.count() == 0

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

    def test__complete_order_line_existing_inventory(
        self, vendor_order_line_factory, vendor_part, inventory_line_factory
    ):
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
        with pytest.raises(m.VendorOrder.DoesNotExist):
            s.VendorOrderService().complete_order(1234)

    def test_complete_order_fulfilled(self, vendor_order):
        vendor_order.fulfilled = timezone.now()
        vendor_order.save()
        with pytest.raises(m.VendorOrder.DoesNotExist):
            s.VendorOrderService().complete_order(vendor_order.pk)


class TestProjectBuildService:
    def test_part_satisfaction_no_inventory(self, part):
        satisfaction = s.PartSatisfaction(part=part, needed=2)
        assert satisfaction.needed == 2
        assert satisfaction.unfulfilled == 2
        assert satisfaction.fulfillments == []

    def test_part_satisfaction_insufficient_inventory(
        self, part, inventory_line_factory
    ):
        _line = inventory_line_factory(part=part, quantity=1)
        satisfaction = s.PartSatisfaction(part=part, needed=2)
        assert satisfaction.needed == 2
        assert satisfaction.unfulfilled == 1
        assert satisfaction.fulfillments[0].inventory_line == _line
        assert satisfaction.fulfillments[0].depletion == 1

    def test_part_satisfaction_sufficient_inventory(self, part, inventory_line_factory):
        _other_line = inventory_line_factory(part=part, quantity=5)
        _line = inventory_line_factory(part=part, quantity=2)
        satisfaction = s.PartSatisfaction(part=part, needed=2)
        assert satisfaction.needed == 2
        assert satisfaction.unfulfilled == 0
        assert satisfaction.fulfillments[0].inventory_line == _line
        assert satisfaction.fulfillments[0].depletion == 2

    def test_part_satisfaction_sufficient_inventory_deprioritized(
        self, part, inventory_line_factory
    ):
        _other_line = inventory_line_factory(part=part, quantity=5)
        _line = inventory_line_factory(part=part, quantity=2, is_deprioritized=True)
        satisfaction = s.PartSatisfaction(part=part, needed=2)
        assert satisfaction.needed == 2
        assert satisfaction.unfulfilled == 0
        assert satisfaction.fulfillments[0].inventory_line == _other_line
        assert satisfaction.fulfillments[0].depletion == 2

    def test_clear_to_build(self, build, monkeypatch):
        call_count = 0

        def fake_clear_to_build(self, _build):
            assert _build == build
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(
            s.ProjectBuildService, "_clear_to_build", fake_clear_to_build
        )
        s.ProjectBuildService().clear_to_build(build.pk)
        assert call_count == 1

    def test_clear_to_build_no(self, build):
        build.completed = timezone.now()
        build.save()

        with pytest.raises(m.ProjectBuild.DoesNotExist):
            s.ProjectBuildService().clear_to_build(build.pk)

    def test_clear_to_build__insufficient_inventory(self, build, monkeypatch):
        def fake_clear_to_build(self, _build):
            raise s.ProjectBuildService.InsufficientInventory(lacking=[])

        monkeypatch.setattr(
            s.ProjectBuildService, "_clear_to_build", fake_clear_to_build
        )
        assert s.ProjectBuildService().clear_to_build(build.pk) == []

    def test__clear_to_build(self, project_part, build, inventory_line_factory):
        _line = inventory_line_factory(part=project_part.part, quantity=10)
        s.ProjectBuildService()._clear_to_build(build)
        assert build.part_reservations.count() == 1
        assert len(m.InventoryAction.objects.all()) == 1
        action = m.InventoryAction.objects.all()[0]
        assert action.inventory_line == _line
        assert action.delta == -6
        assert action.order_line is None
        assert action.build == build
        _line.refresh_from_db()
        assert _line.quantity == 4
        s.ProjectBuildPartReservationService().delete_reservations(
            build.part_reservations.all()
        )
        _line.refresh_from_db()
        assert _line.quantity == 10

    def test__clear_to_build_not(
        self, project_part, vendor_part, build, inventory_line_factory
    ):
        _line = inventory_line_factory(part=project_part.part, quantity=1)

        with pytest.raises(s.ProjectBuildService.InsufficientInventory):
            ret = s.ProjectBuildService()._clear_to_build(build)
        assert build.shortfalls.all().count() == 1
        assert build.shortfalls.all()[0].quantity == 5
        assert build.shortfalls.all()[0].part == project_part.part

    def test__clear_to_build_accumulates_by_part(
        self, build, project_part_factory, inventory_line_factory, part
    ):
        _line = inventory_line_factory(part=part, quantity=10)
        reused_project_part = project_part_factory(
            project_version=build.project_version, part=part, quantity=1, line_number=2
        )
        reservations = s.ProjectBuildService()._clear_to_build(build)
        assert len(reservations) == 1
        assert reservations[0].inventory_action.delta == -9
        _line.refresh_from_db()
        assert _line.quantity == 1
        s.ProjectBuildPartReservationService().delete_reservations(
            build.part_reservations.all()
        )
        _line.refresh_from_db()
        assert _line.quantity == 10

    def test__clear_to_build__excluded_part(
        self,
        project_part,
        build,
        project_part_factory,
        part,
        part_factory,
        inventory_line_factory,
    ):
        _line = inventory_line_factory(part=project_part.part, quantity=10)
        excluded_part = part_factory(name="omitted", symbol="O")
        excluded_project_part = project_part_factory(
            part=excluded_part,
            project_version=build.project_version,
            line_number=2,
            quantity=1,
            is_optional=True,
        )
        build.excluded_project_parts.add(excluded_project_part)
        reservations = s.ProjectBuildService()._clear_to_build(build)
        assert len(reservations) == 1
        assert reservations[0].inventory_action.inventory_line.part == part
        build.excluded_project_parts.clear()
        s.ProjectBuildPartReservationService().delete_reservations(
            build.part_reservations.all()
        )

    def test__complete_build(self, project_part, build, inventory_line_factory):
        _line = inventory_line_factory(part=project_part.part, quantity=10)
        build.cleared = timezone.now()
        build.save()
        reservation = m.ProjectBuildPartReservation.objects.create(
            inventory_action=None,
            project_build=build,
        )
        s.ProjectBuildService()._complete_build(build)
        reservation.refresh_from_db()
        build.refresh_from_db()
        assert reservation.utilized is not None
        assert build.completed is not None
        reservation.delete()

    def test__complete_build_no(
        self, project_part, build, inventory_line_factory, monkeypatch
    ):
        _line = inventory_line_factory(part=project_part.part, quantity=2)

        call_count = 0

        def fake_clear_to_build(self, _build):
            assert _build == build
            nonlocal call_count
            call_count += 1
            raise s.ProjectBuildService.InsufficientInventory(lacking=[])

        monkeypatch.setattr(
            s.ProjectBuildService, "_clear_to_build", fake_clear_to_build
        )
        with pytest.raises(s.ProjectBuildService.InsufficientInventory):
            ret = s.ProjectBuildService()._complete_build(build)
        build.refresh_from_db()
        assert build.completed is None
        assert call_count == 1

    def test__complete_build_already_completed(self, build, monkeypatch):
        build.completed = timezone.now()
        build.save()

        call_count = 0

        def fake_clear_to_build(self, _build):
            assert _build == build
            nonlocal call_count
            call_count += 1
            raise s.ProjectBuildService.InsufficientInventory(lacking=[])

        monkeypatch.setattr(
            s.ProjectBuildService, "_clear_to_build", fake_clear_to_build
        )

        s.ProjectBuildService()._complete_build(build)
        assert call_count == 0

    def test_complete_build(self, build, monkeypatch):
        call_count = 0
        print(build)
        build.cleared = timezone.now()
        build.save()

        def fake_complete_build(self, _build):
            assert _build == build
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(
            s.ProjectBuildService, "_complete_build", fake_complete_build
        )
        s.ProjectBuildService().complete_build(build.pk)
        assert call_count == 1

    def test_complete_build_bad(self, build, monkeypatch):
        with pytest.raises(m.ProjectBuild.DoesNotExist):
            s.ProjectBuildService().complete_build(1234)

    def test_cancel_build(self, build, monkeypatch):
        call_count = 0

        def fake__cancel_build(self, _build):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(s.ProjectBuildService, "_cancel_build", fake__cancel_build)
        s.ProjectBuildService().cancel_build(build.pk)
        assert call_count == 1

    def test_cancel_build__no(self, build, monkeypatch):
        call_count = 0

        def fake__cancel_build(self, _build):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(s.ProjectBuildService, "_cancel_build", fake__cancel_build)
        s.ProjectBuildService().cancel_build(build.pk)
        assert call_count == 1

    def test__cancel_build(self, build, inventory_line_factory, part):
        _line = inventory_line_factory(part=part, quantity=10)
        reservations = s.ProjectBuildService()._clear_to_build(build)
        build.refresh_from_db()
        assert build.cleared is not None
        _line.refresh_from_db()
        assert _line.quantity == 4
        s.ProjectBuildService()._cancel_build(build)
        _line.refresh_from_db()
        assert _line.quantity == 10
        build.refresh_from_db()
        assert build.cleared is None

    def test__cancel_build__completed(self, build, monkeypatch):
        def fake_delete_reservations(self, _build):
            assert False

        monkeypatch.setattr(
            s.ProjectBuildPartReservationService,
            "delete_reservations",
            fake_delete_reservations,
        )
        build.completed = timezone.now()
        build.save()
        s.ProjectBuildService()._cancel_build(build)
        build.refresh_from_db()
        assert build.completed is not None


class TestBillOfMaterialsRow:
    def test_normalize_value(self):
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
        _footprint = s.MouserPartService()._get_footprint(bom_row)
        assert footprint == _footprint

    def test__get_footprint_new(self, footprint, bom_row):
        bom_row.footprint_name = "Other Footprint"
        _footprint = s.MouserPartService()._get_footprint(bom_row)
        assert _footprint.name == "Other Footprint"
        assert _footprint != footprint

    def test__get_package(self, package, bom_row):
        _package = s.MouserPartService()._get_package(bom_row)
        assert _package == package

    def test__get_package_new(self, package, bom_row):
        bom_row.footprint_name = "ASDF:Other Footprint"
        _package = s.MouserPartService()._get_package(bom_row)
        assert _package != package
        assert _package.technology == m.CircuitTechnologyEnum.UNKNOWN
        assert _package.name == "Other Footprint"

    def test__get_part(self, part_factory, bom_row):
        part = part_factory(name="Test Part", value="great", symbol="T")
        _part = s.MouserPartService()._get_part(bom_row)
        assert _part == part

    def test__get_part_new(self, part_factory, bom_row, package):
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
        call_count = 0

        def fake_populate(*args, **kwargs):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(MouserService, "populate", fake_populate)
        part = part_factory(name="Test Part", value="great", symbol="T")
        # This method should _only_ be hit after a part has been found to not exist
        _vendor_part = s.MouserPartService().create_vendor_part(bom_row)
        assert _vendor_part.part == part
        assert _vendor_part.item_number == "ASDF-1234"
        assert _vendor_part.url_path == "placeholder"

        broker.join("default")
        worker.join()
        assert call_count == 1
        _vendor_part.delete()


class TestProjectVersionBomService:
    def test_get_vendor_part(self, vendor_part):
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

    def test_get_vendor_part_missing(self, vendor_part):
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
        assert _vendor_part is None

    def test_get_vendor_part_missing_mouser(self, vendor_part_mouser, monkeypatch):
        def fake_create_vendor_part(self, row):
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

    def test_get_matching_parts(self, part_factory, footprint):
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

    def test_get_matching_parts_discriminating(self, part_factory, footprint):
        log_pot = part_factory(name="Spinny Boi Pot", value="A100K", symbol="RV")
        lin_pot = part_factory(name="Spinny Boi Pot", value="B100K", symbol="RV")
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

    def test_get_matching_parts_quantity_sorting(
        self, part_factory, footprint, inventory_line_factory
    ):
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

    def test_get_matching_parts_deprioritized(
        self, part_factory, footprint, inventory_line_factory
    ):
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

    def test_get_part_vendor_part(self, monkeypatch, vendor_part):
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

    def test_get_part_regular(self, monkeypatch, part_queryset, part):
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
                    "PartNum": "",
                    "Vendor": "",
                    "Value": "asdf6789",
                    "Footprint": "asdf1234",
                }
            ),
        )
        assert call_count == 1
        assert _part == part

    def test_get_part_missing(self, monkeypatch):
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

    def test_build_bom_url(self, project_version):
        ret = s.ProjectVersionBomService()._build_bom_url(project_version)
        assert ret == "https://gitbub.com/fake/fake/raw/v0/nested/deep/test.csv"

    def test_sync_footprints(self, project_part):
        _old_footprint_ref = m.ProjectPartFootprintRef.objects.create(
            project_part=project_part,
            footprint_ref="F2",
        )
        _old_footprint_ref2 = m.ProjectPartFootprintRef.objects.create(
            project_part=project_part,
            footprint_ref="F3",
        )
        s.ProjectVersionBomService()._sync_footprints(
            {"F1", "F3"}, project_part=project_part
        )
        with pytest.raises(m.ProjectPartFootprintRef.DoesNotExist):
            _old_footprint_ref.refresh_from_db()
        refs = m.ProjectPartFootprintRef.objects.filter(project_part=project_part)
        assert _old_footprint_ref2 in refs
        assert "F1" in refs.values_list("footprint_ref", flat=True)

    def test_sync_implicit_parts(
        self,
        project_version,
        part,
        part_factory,
        project_part_factory,
        implicit_project_part_factory,
    ):
        implicit_part = part_factory(name="implicit part", symbol="IP")
        project_part = project_part_factory(
            project_version=project_version, part=part, line_number=69
        )
        implicit_project_part = implicit_project_part_factory(
            for_package=part.package, part=implicit_part, quantity=3
        )
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 0
        s.ProjectVersionBomService()._sync_implicit_parts(project_part=project_part)
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        pp = m.ProjectPart.objects.filter(is_implicit=True)[0]
        assert pp.quantity == 6
        assert pp.line_number == project_part.line_number
        pp.delete()

    def test_sync_implicit_parts_remove_old(
        self,
        project_version,
        part,
        part_factory,
        project_part_factory,
        implicit_project_part_factory,
    ):
        implicit_part = part_factory(name="implicit part", symbol="IP")
        old_part = part_factory(name="old part", symbol="IP")
        project_part = project_part_factory(
            project_version=project_version, part=part, line_number=69
        )
        old_project_part = project_part_factory(
            project_version=project_version,
            part=old_part,
            line_number=69,
            is_implicit=True,
        )
        implicit_project_part = implicit_project_part_factory(
            for_package=part.package, part=implicit_part, quantity=3
        )
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        s.ProjectVersionBomService()._sync_implicit_parts(project_part=project_part)
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        pp = m.ProjectPart.objects.filter(is_implicit=True)[0]
        assert pp.quantity == 6
        assert pp.line_number == project_part.line_number
        assert pp.part == implicit_part
        with pytest.raises(m.ProjectPart.DoesNotExist):
            old_project_part.refresh_from_db()
        pp.delete()

    def test_sync_implicit_parts_update(
        self,
        project_version,
        part,
        part_factory,
        project_part_factory,
        implicit_project_part_factory,
    ):
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
        implicit_project_part = implicit_project_part_factory(
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

    def test_sync_implicit_parts_multiple(
        self,
        project_version,
        part,
        part_factory,
        project_part_factory,
        implicit_project_part_factory,
    ):
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
        implicit_project_part = implicit_project_part_factory(
            for_package=part.package, part=implicit_part, quantity=3
        )
        other_implicit_project_part = implicit_project_part_factory(
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

    def test_sync_row(self, project_version, part, monkeypatch):
        _row = s.BillOfMaterialsRow(
            **{
                "#": 1,
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

    def test__sync(self, project_version, monkeypatch, project_part_factory, part):
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

        def fake_sync_row(self, *, row, project_version):
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

    def test__sync_missing_part(
        self, project_version, monkeypatch, project_part_factory, part
    ):
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

        ret = s.ProjectVersionBomService()._sync(project_version)
        with pytest.raises(m.ProjectPart.DoesNotExist):
            _bad_project_part.refresh_from_db()
        _project_parts = project_version.project_parts.all()
        assert len(_project_parts) == 1
        assert _project_parts[0].part is None
        assert _project_parts[0].missing_part_description is not None

    def test_sync(self, project_version, monkeypatch):
        call_count = 0

        def fake_sync(self, _project_version):
            nonlocal call_count
            call_count += 1
            assert project_version == _project_version
            return {}

        monkeypatch.setattr(s.ProjectVersionBomService, "_sync", fake_sync)
        s.ProjectVersionBomService().sync(project_version.pk)
        assert call_count == 1

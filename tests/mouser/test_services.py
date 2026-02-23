from decimal import Decimal
from unittest.mock import Mock

import pytest

from django_ctb import models as m
from django_ctb.mouser.client import MouserClient, MouserPart, MouserPricebreak
from django_ctb.mouser.services import MouserPartService, MouserService


class TestMouserPartService:
    """
    :feature: Parts appearing on BOMs with Vendor "Mouser" will be autopopulated
              with data from the Mouser API
    """

    @pytest.fixture
    def bom_row(self):
        row = m.BillOfMaterialsRow.model_validate(
            {
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
        :scenario: Footprints listed in the BOM will be used

        | GIVEN a project version BOM row represents a known footprint
        | AND the same row shows the vendor as "Mouser"
        | WHEN _get_footprint is run for the BOM row
        | THEN the known footprint is returned
        """
        _footprint = MouserPartService()._get_footprint(bom_row)
        assert footprint == _footprint

    def test__get_footprint_new(self, footprint, bom_row):
        """
        :scenario: Footprints listed in "Mouser" BOM rows will be created if
                   necessary

        | GIVEN a project version BOM row represents an unknown footprint
        | AND the same row shows the vendor as "Mouser"
        | WHEN _get_footprint is run for the BOM row
        | THEN a new footprint matching the unknown footprint is created and returned
        """
        bom_row.footprint_name = "Other Footprint"
        _footprint = MouserPartService()._get_footprint(bom_row)
        assert _footprint.name == "Other Footprint"
        assert _footprint != footprint

    def test__get_package(self, package, bom_row):
        """
        :scenario: Footprints imply a component Package

        | GIVEN a project version BOM row represents a known footprint
        | AND the same row shows the vendor as "Mouser"
        | AND the known footprint has an associated package
        | WHEN _get_package is run for the BOM row
        | THEN the package for the known footprint is returned
        """
        _package = MouserPartService()._get_package(bom_row)
        assert _package == package

    def test__get_package_new(self, package, bom_row):
        """
        :scenario: Placeholder Packages will be created as necessary with
                   ambigious default field values

        | GIVEN a project version BOM row represents an unknown footprint
        | AND the same row shows the vendor as "Mouser"
        | WHEN _get_package is run for the BOM row
        | THEN a package (with unknown technology) is created and returned returned
        """
        bom_row.footprint_name = "ASDF:Other Footprint"
        _package = MouserPartService()._get_package(bom_row)
        assert _package != package
        assert _package.technology == m.Package.Technology.UNKNOWN
        assert _package.name == "Other Footprint"

    def test__get_part(self, part_factory, bom_row):
        """
        :scenario: Parts represented on "Mouser" BOM rows will resolve to known
                   Parts

        | GIVEN a project version BOM row represents a known part
        | AND the same row shows the vendor as "Mouser"
        | WHEN _get_part is run for the BOM row
        | THEN the known part is returned
        """
        part = part_factory(name="Test Part", value="great", symbol="T")
        _part = MouserPartService()._get_part(bom_row)
        assert _part == part

    def test__get_part_new(self, part_factory, bom_row, package):
        """
        :scenario: Parts represented on "Mouser" BOM rows will be created in the
                   system when they are previously unknown

        | GIVEN a project version BOM row represents an unknown part
        | AND the same row shows the vendor as "Mouser"
        | AND the BOM row component package (gleaned from the BOM footprint) is known
        | WHEN _get_part is run for the BOM row
        | THEN a placeholder part is created which matches the BOM row
        | AND the created part references the appropriate component package
        """
        part = part_factory(name="Test Part", value="awful", symbol="T")
        _part = MouserPartService()._get_part(bom_row)
        assert _part != part
        assert _part.name == "placeholder"
        assert _part.value == "great"
        assert _part.package == package
        assert _part.symbol == "T"
        _part.delete()

    def test__get_vendor(self, vendor_mouser):
        _mouser = MouserPartService()._get_vendor()
        assert _mouser == vendor_mouser

    def test__get_vendor_missing(self, db):
        with pytest.raises(m.Vendor.DoesNotExist):
            MouserPartService()._get_vendor()

    def test_create_vendor_part(
        self, bom_row, part_factory, vendor_mouser, broker, worker, monkeypatch
    ):
        """
        :scenario: Parts represented on "Mouser" BOM rows will be represented
                   with Parts and Vendor Parts which are autopopulated

        | GIVEN a project version BOM row represents an unknown part
        | AND the same row shows the vendor as "Mouser"
        | AND the BOM row component package (gleaned from the BOM footprint) is known
        | WHEN create_vendor_part is run for the BOM row
        | THEN a placeholder part is created which matches the BOM row
        | AND the created part references the appropriate component package
        | AND a vendor part is created which references the "PartNum" of the BOM row
        | AND a task to populate the vendor part with actual data will be started
        """
        mock_populate = Mock()
        monkeypatch.setattr(MouserService, "populate", mock_populate)
        # This method should _only_ be hit after a part has been found to not
        #   exist, but it should work fine either way.
        _vendor_part = MouserPartService().create_vendor_part(bom_row)
        assert _vendor_part.part.name == "placeholder"
        assert _vendor_part.item_number == "ASDF-1234"
        assert _vendor_part.url_path == "placeholder"

        broker.join("default")
        worker.join()
        mock_populate.assert_called_once()
        _vendor_part.part.delete()
        _vendor_part.delete()


class TestMouserService:
    def test__populate(self, monkeypatch, vendor_part_mouser):
        mouser_part = MouserPart(
            description="Fake part",  # type: ignore[unknown-argument]
            name="BIGBOI1234",  # type: ignore[unknown-argument]
            mouser_part_number="233-FAKE",  # type: ignore[unknown-argument]
            url_path="https://www.mouser.com/whatever/path",  # type: ignore[unknown-argument]
            price_breaks=[
                MouserPricebreak(volume=1, cost="$0.01"),  # type: ignore[invalid-argument-type]
                MouserPricebreak(volume=10, cost="$0.009"),  # type: ignore[invalid-argument-type]
                MouserPricebreak(volume=100, cost="$0.008"),  # type: ignore[invalid-argument-type]
            ],  # type: ignore[unknown-argument]
        )  # type: ignore[missing-argument]

        monkeypatch.setattr(MouserClient, "get_part", Mock(return_value=mouser_part))
        MouserService()._populate(vendor_part_mouser)
        vendor_part_mouser.refresh_from_db()
        assert vendor_part_mouser.url_path == "/whatever/path"
        assert vendor_part_mouser.volume == 10
        assert 0.00899 < vendor_part_mouser.cost < 0.00901
        assert vendor_part_mouser.part.name == "BIGBOI1234"
        assert vendor_part_mouser.part.value == "BIGBOI1234"
        assert vendor_part_mouser.part.description == "Fake part"

    def test_populate(self, monkeypatch, vendor_part_mouser):
        mock__populate = Mock()
        monkeypatch.setattr(MouserService, "_populate", mock__populate)
        MouserService().populate(vendor_part_mouser.pk)
        mock__populate.assert_called_once_with(vendor_part_mouser)

    def test_populate__missing(self, db, monkeypatch):
        mock__populate = Mock(side_effect=Exception)
        monkeypatch.setattr(MouserService, "_populate", mock__populate)
        MouserService().populate(123)
        mock__populate.assert_not_called()

    def test__create__missing_part(self, monkeypatch):
        monkeypatch.setattr(
            MouserClient, "get_part", Mock(side_effect=MouserClient.EmptyResponse)
        )
        with pytest.raises(MouserService.MissingPart):
            MouserService()._create("asdf-1234")

    def test__create(self, db, monkeypatch, vendor_mouser):
        assert m.Part.objects.all().count() == 0
        assert vendor_mouser.vendor_parts.all().count() == 0
        mouser_part = MouserPart(
            description="Fake part",  # type: ignore[unknown-argument]
            name="BIGBOI1234",  # type: ignore[unknown-argument]
            mouser_part_number="233-FAKE",  # type: ignore[unknown-argument]
            url_path="https://www.mouser.com/whatever/path",  # type: ignore[unknown-argument]
            price_breaks=[
                MouserPricebreak(volume=1, cost="$0.01"),  # type: ignore[invalid-argument-type]
                MouserPricebreak(volume=10, cost="$0.009"),  # type: ignore[invalid-argument-type]
                MouserPricebreak(volume=100, cost="$0.008"),  # type: ignore[invalid-argument-type]
            ],  # type: ignore[unknown-argument]
        )  # type: ignore[missing-argument]

        monkeypatch.setattr(MouserClient, "get_part", Mock(return_value=mouser_part))
        MouserService()._create("asdf-1234")
        assert m.Part.objects.all().count() == 1
        p = m.Part.objects.get()
        assert p.name == "BIGBOI1234"
        assert p.value == "BIGBOI1234"
        assert p.description == "Fake part"
        assert vendor_mouser.vendor_parts.all().count() == 1
        vp = vendor_mouser.vendor_parts.get()
        assert vp.part == p
        assert vp.item_number == "asdf-1234"
        assert vp.volume == 10
        assert vp.cost == Decimal("0.0090")
        assert vp.url_path == "/whatever/path"
        vp.delete()
        p.delete()

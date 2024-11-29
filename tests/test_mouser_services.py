from decimal import Decimal

import pytest

from django_ctb import models as m
from django_ctb.mouser.services import MouserService
from django_ctb.mouser.client import MouserClient, MouserPart, MouserPricebreak


class TestMouserService:
    def test__populate(self, monkeypatch, vendor_part_mouser):
        mouser_part = MouserPart(
            description="Fake part",
            name="BIGBOI1234",
            mouser_part_number="233-FAKE",
            url_path="https://www.mouser.com/whatever/path",
            price_breaks=[
                MouserPricebreak(volume=1, cost="$0.01"),
                MouserPricebreak(volume=10, cost="$0.009"),
                MouserPricebreak(volume=100, cost="$0.008"),
            ],
        )

        def fake_client_get_part(*args, **kwargs):
            return mouser_part

        monkeypatch.setattr(MouserClient, "get_part", fake_client_get_part)
        MouserService()._populate(vendor_part_mouser)
        vendor_part_mouser.refresh_from_db()
        assert vendor_part_mouser.url_path == "/whatever/path"
        assert vendor_part_mouser.volume == 10
        assert 0.00899 < vendor_part_mouser.cost < 0.00901
        assert vendor_part_mouser.part.name == "BIGBOI1234"
        assert vendor_part_mouser.part.value == "BIGBOI1234"
        assert vendor_part_mouser.part.description == "Fake part"

    def test_populate(self, monkeypatch, vendor_part_mouser):
        call_count = 0

        def fake__populate(self, vendor_part):
            assert vendor_part_mouser == vendor_part
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(MouserService, "_populate", fake__populate)
        MouserService().populate(vendor_part_mouser.pk)
        assert call_count == 1

    def test_populate_missing(self, db, monkeypatch):
        call_count = 0

        def fake__populate(self, vendor_part):
            assert vendor_part_mouser == vendor_part
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr(MouserService, "_populate", fake__populate)
        MouserService().populate(123)
        assert call_count == 0

    def test__create_missing_part(self, monkeypatch):
        def fake_client_get_part(*args, **kwargs):
            raise MouserClient.EmptyResponse

        monkeypatch.setattr(MouserClient, "get_part", fake_client_get_part)
        with pytest.raises(MouserService.MissingPart):
            ret = MouserService()._create("asdf-1234")

    def test__create(self, db, monkeypatch, vendor_mouser):
        assert m.Part.objects.all().count() == 0
        assert vendor_mouser.vendor_parts.all().count() == 0
        mouser_part = MouserPart(
            description="Fake part",
            name="BIGBOI1234",
            mouser_part_number="233-FAKE",
            url_path="https://www.mouser.com/whatever/path",
            price_breaks=[
                MouserPricebreak(volume=1, cost="$0.01"),
                MouserPricebreak(volume=10, cost="$0.009"),
                MouserPricebreak(volume=100, cost="$0.008"),
            ],
        )

        def fake_client_get_part(*args, **kwargs):
            return mouser_part

        monkeypatch.setattr(MouserClient, "get_part", fake_client_get_part)
        ret = MouserService()._create("asdf-1234")
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

from unittest.mock import Mock

import pytest
import requests

from django_ctb.mouser.client import MouserClient

from .data import get_many_part_response, get_part_response, missing_part_response


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class TestMouserClient:
    def test_get_part__missing(self, monkeypatch):
        monkeypatch.setattr(
            requests,
            "post",
            Mock(return_value=FakeResponse(text=missing_part_response)),
        )
        with pytest.raises(MouserClient.EmptyResponse):
            MouserClient().get_part("876-ASDFQWERZXCV")

    def test_get_part__bad_response(self, monkeypatch):
        monkeypatch.setattr(
            requests,
            "post",
            Mock(return_value=FakeResponse(text="bad", status_code=300)),
        )
        with pytest.raises(MouserClient.BadResponse):
            MouserClient().get_part("876-ASDFQWERZXCV")

    def test_get_part__bad_json(self, monkeypatch):
        monkeypatch.setattr(
            requests,
            "post",
            Mock(
                return_value=FakeResponse(text='{"Errors": [], "BlearchResults": {}}')
            ),
        )
        with pytest.raises(Exception):
            MouserClient().get_part("876-ASDFQWERZXCV")

    def test_get_part(self, monkeypatch):
        monkeypatch.setattr(
            requests, "post", Mock(return_value=FakeResponse(get_part_response))
        )
        mouser_part = MouserClient().get_part("863-BAT54SLT1G")
        assert mouser_part.name == "BAT54SLT1G"
        assert mouser_part.description == "Schottky Diodes & Rectifiers 30V 225mW Dual"
        assert (
            mouser_part.url_path
            == "/ProductDetail/onsemi/BAT54SLT1G?qs=vLkC5FC1VN9oCh8qaBIZiQ%3D%3D"
        )

    def test_get_part_many_returned(self, monkeypatch):
        monkeypatch.setattr(
            requests, "post", Mock(return_value=FakeResponse(get_many_part_response))
        )
        mouser_part = MouserClient().get_part("863-BAT54SLT1G-2")
        assert mouser_part.name == "BAT54SLT1G"
        assert mouser_part.description == "Schottky Diodes & Rectifiers 30V 225mW Dual"
        assert (
            mouser_part.url_path
            == "/ProductDetail/onsemi/BAT54SLT1G?qs=vLkC5FC1VN9oCh8qaBIZiQ%3D%3D"
        )

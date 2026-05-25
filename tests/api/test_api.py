import re
from django.urls import reverse
from rest_framework import status
from .test_crud import assert_status


class TestAutogenDocs:
    def test_autogen_schema_available(self, api_client):
        # the URL is defined by the ``test_project``
        response = api_client.get(reverse("schema"))
        assert_status(response, status.HTTP_200_OK)


class TestPartFilterMeta:
    def test_part_filter_meta__aggregates_values(
        self, user_authed_api_client, part_factory
    ):
        values = set()
        suffixes = ["", "K", "u", "m"]
        for idx in range(20):
            value = f"{idx}.{idx}{suffixes[idx % len(suffixes)]}"
            values.add(value)
            part_factory(value=value, symbol="T", name="test part")
        response = user_authed_api_client.get(
            reverse("django-ctb-api:part-filter-meta")
        )
        assert_status(response, status.HTTP_200_OK)
        data = response.json()
        print(data)
        _field_spec_by_name = {}
        for _filter_spec in data["filters"]:
            _field_spec_by_name[_filter_spec["field_name"]] = _filter_spec
        assert "value" in _field_spec_by_name
        assert "name" in _field_spec_by_name
        assert "symbol" in _field_spec_by_name
        assert set(_field_spec_by_name["value"]["options"]) == values
        assert set(_field_spec_by_name["name"]["options"]) == {"test part"}
        assert set(_field_spec_by_name["symbol"]["options"]) == {"T"}
        assert set(_field_spec_by_name["package__name"]["options"]) == {"Test Package"}
        assert {"value": "0", "label": "Through Hole"} in _field_spec_by_name[
            "package__technology"
        ]["choice_options"]

"""
Client for interacting with the Mouser Search API. Includes essential
data models for extracting part data.
"""

import logging

import requests
from pydantic import BaseModel, ConfigDict, Field, field_validator

from django_ctb.conf import settings

logger = logging.getLogger(__name__)


class MouserPricebreak(BaseModel):
    """
    Represents minimum order volumes to cost per item break points
    """

    volume: int = Field(alias="Quantity")
    cost: float = Field(alias="Price")

    model_config = ConfigDict(
        populate_by_name=True,
    )

    @field_validator("cost", mode="before")
    @classmethod
    def _remove_prefix(cls, value: str) -> float:
        return float(value.replace("$", ""))


class MouserPart(BaseModel):
    """
    Represents minimal part data relevant to this inventory
    """

    description: str = Field(alias="Description")
    name: str = Field(alias="ManufacturerPartNumber")  # map to value and name
    price_breaks: list[MouserPricebreak] = Field(alias="PriceBreaks")
    url_path: str = Field(alias="ProductDetailUrl")
    mouser_part_number: str = Field(alias="MouserPartNumber")

    model_config = ConfigDict(
        populate_by_name=True,
    )

    @field_validator("url_path", mode="before")
    @classmethod
    def _remove_prefix(cls, value: str) -> str:
        return value.replace("https://www.mouser.com", "")


class _MouserSearchResponse(BaseModel):
    number_of_result: int = Field(alias="NumberOfResult")
    parts: list[MouserPart] = Field(alias="Parts")


class _MouserSearchResponseRoot(BaseModel):
    search_results: _MouserSearchResponse = Field(alias="SearchResults")


class _MouserSearchByPartRequest(BaseModel):
    mouser_part_number: str = Field(alias="mouserPartNumber")

    model_config = ConfigDict(
        populate_by_name=True,
    )


class _MouserSearchByPartRequestRoot(BaseModel):
    search_by_part_request: _MouserSearchByPartRequest = Field(
        alias="SearchByPartRequest"
    )

    model_config = ConfigDict(
        populate_by_name=True,
    )


class MouserClient:
    """
    Client for getting part data from Mouser Search API
    """

    class BadResponse(Exception):
        """Unexpected response"""

        pass

    class EmptyResponse(Exception):
        """Null response"""

        pass

    def get_part(self, mouser_part_number: str) -> MouserPart:
        """
        Search for the specifid part number and parse the response.
        """
        part_request = _MouserSearchByPartRequestRoot(
            SearchByPartRequest=_MouserSearchByPartRequest(
                mouserPartNumber=mouser_part_number
            )
        )
        _data = part_request.model_dump_json(by_alias=True)
        logger.debug(f"posting to get data {_data}")
        response = requests.post(
            "https://api.mouser.com/api/v1/search/partnumber",
            data=_data,
            params={"apiKey": settings.CTB_MOUSER_API_KEY},
            headers={"accept": "application/json", "content-type": "application/json"},
        )
        if response.status_code >= 300:
            logger.error(
                f"Part response status code: {response.status_code}: {response.text}"
            )
            raise self.BadResponse
        logger.debug(f"Part found! {response.text}")
        try:
            response_model = _MouserSearchResponseRoot.model_validate_json(
                response.text
            )
        except Exception:
            logger.error(f"Can't validate data: {response.text}")
            raise
        if response_model.search_results.number_of_result > 1:
            for part in response_model.search_results.parts:
                if part.mouser_part_number == mouser_part_number:
                    return part
        elif response_model.search_results.number_of_result != 1:
            logger.debug(f"response text: {response.text}")
            raise self.EmptyResponse
        return response_model.search_results.parts[0]

import requests
import logging

from pydantic import BaseModel, Field, field_validator, ConfigDict

from django.conf import settings

logger = logging.getLogger(__name__)


class MouserPricebreak(BaseModel):
    volume: int = Field(alias="Quantity")
    cost: float = Field(alias="Price")

    model_config = ConfigDict(
        populate_by_name=True,
    )

    @field_validator("cost", mode="before")
    @classmethod
    def remove_prefix(cls, value: str) -> float:
        return float(value.replace("$", ""))


class MouserPart(BaseModel):
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
    def remove_prefix(cls, value: str) -> str:
        return value.replace("https://www.mouser.com", "")


class MouserSearchResponse(BaseModel):
    number_of_result: int = Field(alias="NumberOfResult")
    parts: list[MouserPart] = Field(alias="Parts")


class MouserSearchResponseRoot(BaseModel):
    search_results: MouserSearchResponse = Field(alias="SearchResults")


class MouserSearchByPartRequest(BaseModel):
    mouser_part_number: str = Field(alias="mouserPartNumber")

    model_config = ConfigDict(
        populate_by_name=True,
    )


class MouserSearchByPartRequestRoot(BaseModel):
    search_by_part_request: MouserSearchByPartRequest = Field(
        alias="SearchByPartRequest"
    )

    model_config = ConfigDict(
        populate_by_name=True,
    )


class MouserClient:
    def __init__(self):
        self.api_key = settings.MOUSER_API_KEY

    class BadResponse(Exception):
        pass

    class EmptyResponse(Exception):
        pass

    def get_part(self, mouser_part_number: str) -> MouserPart:
        part_request = MouserSearchByPartRequestRoot(
            search_by_part_request=MouserSearchByPartRequest(
                mouser_part_number=mouser_part_number
            )
        )
        _data = part_request.model_dump_json(by_alias=True)
        # logger.warning(f"posting to get data {_data}")
        response = requests.post(
            "https://api.mouser.com/api/v1/search/partnumber",
            data=_data,
            params={"apiKey": self.api_key},
            headers={"accept": "application/json", "content-type": "application/json"},
        )
        if response.status_code >= 300:
            logger.error(
                f"Part response status code: {response.status_code}: {response.text}"
            )
            raise self.BadResponse
        # logger.warning(f"Part found! {response.text}")
        try:
            response_model = MouserSearchResponseRoot.model_validate_json(response.text)
        except Exception:
            logger.error(f"Can't validate data: {response.text}")
            raise
        if response_model.search_results.number_of_result > 1:
            for part in response_model.search_results.parts:
                if part.mouser_part_number == mouser_part_number:
                    return part
        elif response_model.search_results.number_of_result != 1:
            print(response.text)
            raise self.EmptyResponse
        return response_model.search_results.parts[0]

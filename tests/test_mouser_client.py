import requests
import pytest

from django_ctb.mouser.client import MouserClient


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class TestMouserClient:
    def test_get_part_missing(self, monkeypatch):
        def fake_post(*args, **kwargs):
            return FakeResponse(
                text="""{
  "Errors": [],
  "SearchResults": {
    "NumberOfResult": 0,
    "Parts": []
  }
} """
            )

        monkeypatch.setattr(requests, "post", fake_post)
        with pytest.raises(MouserClient.EmptyResponse):
            mouser_part = MouserClient().get_part("876-ASDFQWERZXCV")

    def test_get_part_bad(self, monkeypatch):
        def fake_post(*args, **kwargs):
            return FakeResponse(text="bad", status_code=300)

        monkeypatch.setattr(requests, "post", fake_post)
        with pytest.raises(MouserClient.BadResponse):
            mouser_part = MouserClient().get_part("876-ASDFQWERZXCV")

    def test_get_part(self, monkeypatch):
        def fake_post(*args, **kwargs):
            return FakeResponse(
                """{
  "Errors": [],
  "SearchResults": {
    "NumberOfResult": 1,
    "Parts": [
      {
        "Availability": "1498379 In Stock",
        "DataSheetUrl": "https://www.mouser.com/datasheet/2/308/BAT54SLT1_D-2309936.pdf",
        "Description": "Schottky Diodes & Rectifiers 30V 225mW Dual",
        "FactoryStock": "0",
        "ImagePath": "https://www.mouser.com/images/mouserelectronics/images/SOT_23_3_t.jpg",
        "Category": "Schottky Diodes & Rectifiers",
        "LeadTime": "63 Days",
        "LifecycleStatus": null,
        "Manufacturer": "onsemi",
        "ManufacturerPartNumber": "BAT54SLT1G",
        "Min": "1",
        "Mult": "1",
        "MouserPartNumber": "863-BAT54SLT1G",
        "ProductAttributes": [
          {
            "AttributeName": "Packaging",
            "AttributeValue": "Reel"
          },
          {
            "AttributeName": "Packaging",
            "AttributeValue": "Cut Tape"
          },
          {
            "AttributeName": "Packaging",
            "AttributeValue": "MouseReel",
            "AttributeCost": "$7.00 MouseReel™ blah blah blah"
          },
          {
            "AttributeName": "Standard Pack Qty",
            "AttributeValue": "3000"
          }
        ],
        "PriceBreaks": [
          {
            "Quantity": 1,
            "Price": "$0.15",
            "Currency": "USD"
          },
          {
            "Quantity": 10,
            "Price": "$0.106",
            "Currency": "USD"
          },
          {
            "Quantity": 100,
            "Price": "$0.057",
            "Currency": "USD"
          },
          {
            "Quantity": 1000,
            "Price": "$0.031",
            "Currency": "USD"
          },
          {
            "Quantity": 3000,
            "Price": "$0.026",
            "Currency": "USD"
          },
          {
            "Quantity": 9000,
            "Price": "$0.021",
            "Currency": "USD"
          },
          {
            "Quantity": 24000,
            "Price": "$0.019",
            "Currency": "USD"
          },
          {
            "Quantity": 45000,
            "Price": "$0.016",
            "Currency": "USD"
          },
          {
            "Quantity": 99000,
            "Price": "$0.015",
            "Currency": "USD"
          }
        ],
        "AlternatePackagings": null,
        "ProductDetailUrl": "https://www.mouser.com/ProductDetail/onsemi/BAT54SLT1G?qs=vLkC5FC1VN9oCh8qaBIZiQ%3D%3D",
        "Reeling": true,
        "ROHSStatus": "RoHS Compliant",
        "SuggestedReplacement": "",
        "MultiSimBlue": 0,
        "UnitWeightKg": {
          "UnitWeight": 0.00003
        },
        "AvailabilityInStock": "1498379",
        "AvailabilityOnOrder": [],
        "InfoMessages": [],
        "ProductCompliance": [
          {
            "ComplianceName": "USHTS",
            "ComplianceValue": "8541100070"
          },
          {
            "ComplianceName": "CNHTS",
            "ComplianceValue": "8541590000"
          },
          {
            "ComplianceName": "CAHTS",
            "ComplianceValue": "8541100090"
          },
          {
            "ComplianceName": "KRHTS",
            "ComplianceValue": "8541109000"
          },
          {
            "ComplianceName": "TARIC",
            "ComplianceValue": "8541100000"
          },
          {
            "ComplianceName": "MXHTS",
            "ComplianceValue": "8541100101"
          },
          {
            "ComplianceName": "ECCN",
            "ComplianceValue": "EAR99"
          }
        ]
      }
    ]
  }
}"""
            )

        monkeypatch.setattr(requests, "post", fake_post)
        mouser_part = MouserClient().get_part("863-BAT54SLT1G")
        assert mouser_part.name == "BAT54SLT1G"
        assert mouser_part.description == "Schottky Diodes & Rectifiers 30V 225mW Dual"
        assert (
            mouser_part.url_path
            == "/ProductDetail/onsemi/BAT54SLT1G?qs=vLkC5FC1VN9oCh8qaBIZiQ%3D%3D"
        )

    def test_get_part_many_returned(self, monkeypatch):
        def fake_post(*args, **kwargs):
            return FakeResponse(
                """{
  "Errors": [],
  "SearchResults": {
    "NumberOfResult": 2,
    "Parts": [
      {
        "Availability": "1498379 In Stock",
        "DataSheetUrl": "https://www.mouser.com/datasheet/2/308/BAT54SLT1_D-2309936.pdf",
        "Description": "Schottky Diodes & Rectifiers 30V 225mW Dual",
        "FactoryStock": "0",
        "ImagePath": "https://www.mouser.com/images/mouserelectronics/images/SOT_23_3_t.jpg",
        "Category": "Schottky Diodes & Rectifiers",
        "LeadTime": "63 Days",
        "LifecycleStatus": null,
        "Manufacturer": "onsemi",
        "ManufacturerPartNumber": "BAT54SLT1G",
        "Min": "1",
        "Mult": "1",
        "MouserPartNumber": "863-BAT54SLT1G",
        "ProductAttributes": [
          {
            "AttributeName": "Packaging",
            "AttributeValue": "Reel"
          },
          {
            "AttributeName": "Packaging",
            "AttributeValue": "Cut Tape"
          },
          {
            "AttributeName": "Packaging",
            "AttributeValue": "MouseReel",
            "AttributeCost": "$7.00 MouseReel™ blah blah blah"
          },
          {
            "AttributeName": "Standard Pack Qty",
            "AttributeValue": "3000"
          }
        ],
        "PriceBreaks": [
          {
            "Quantity": 1,
            "Price": "$0.15",
            "Currency": "USD"
          },
          {
            "Quantity": 10,
            "Price": "$0.106",
            "Currency": "USD"
          },
          {
            "Quantity": 100,
            "Price": "$0.057",
            "Currency": "USD"
          },
          {
            "Quantity": 1000,
            "Price": "$0.031",
            "Currency": "USD"
          },
          {
            "Quantity": 3000,
            "Price": "$0.026",
            "Currency": "USD"
          },
          {
            "Quantity": 9000,
            "Price": "$0.021",
            "Currency": "USD"
          },
          {
            "Quantity": 24000,
            "Price": "$0.019",
            "Currency": "USD"
          },
          {
            "Quantity": 45000,
            "Price": "$0.016",
            "Currency": "USD"
          },
          {
            "Quantity": 99000,
            "Price": "$0.015",
            "Currency": "USD"
          }
        ],
        "AlternatePackagings": null,
        "ProductDetailUrl": "https://www.mouser.com/ProductDetail/onsemi/BAT54SLT1G?qs=vLkC5FC1VN9oCh8qaBIZiQ%3D%3D",
        "Reeling": true,
        "ROHSStatus": "RoHS Compliant",
        "SuggestedReplacement": "",
        "MultiSimBlue": 0,
        "UnitWeightKg": {
          "UnitWeight": 0.00003
        },
        "AvailabilityInStock": "1498379",
        "AvailabilityOnOrder": [],
        "InfoMessages": [],
        "ProductCompliance": [
          {
            "ComplianceName": "USHTS",
            "ComplianceValue": "8541100070"
          },
          {
            "ComplianceName": "CNHTS",
            "ComplianceValue": "8541590000"
          },
          {
            "ComplianceName": "CAHTS",
            "ComplianceValue": "8541100090"
          },
          {
            "ComplianceName": "KRHTS",
            "ComplianceValue": "8541109000"
          },
          {
            "ComplianceName": "TARIC",
            "ComplianceValue": "8541100000"
          },
          {
            "ComplianceName": "MXHTS",
            "ComplianceValue": "8541100101"
          },
          {
            "ComplianceName": "ECCN",
            "ComplianceValue": "EAR99"
          }
        ]
      },
      {
        "Availability": "1498379 In Stock",
        "DataSheetUrl": "https://www.mouser.com/datasheet/2/308/BAT54SLT1_D-2309936.pdf",
        "Description": "Schottky Diodes & Rectifiers 30V 225mW Dual",
        "FactoryStock": "0",
        "ImagePath": "https://www.mouser.com/images/mouserelectronics/images/SOT_23_3_t.jpg",
        "Category": "Schottky Diodes & Rectifiers",
        "LeadTime": "63 Days",
        "LifecycleStatus": null,
        "Manufacturer": "onsemi",
        "ManufacturerPartNumber": "BAT54SLT1G",
        "Min": "1",
        "Mult": "1",
        "MouserPartNumber": "863-BAT54SLT1G-2",
        "ProductAttributes": [
          {
            "AttributeName": "Packaging",
            "AttributeValue": "Reel"
          },
          {
            "AttributeName": "Packaging",
            "AttributeValue": "Cut Tape"
          },
          {
            "AttributeName": "Packaging",
            "AttributeValue": "MouseReel",
            "AttributeCost": "$7.00 MouseReel™ blah blah blah"
          },
          {
            "AttributeName": "Standard Pack Qty",
            "AttributeValue": "3000"
          }
        ],
        "PriceBreaks": [
          {
            "Quantity": 1,
            "Price": "$0.15",
            "Currency": "USD"
          },
          {
            "Quantity": 10,
            "Price": "$0.106",
            "Currency": "USD"
          },
          {
            "Quantity": 100,
            "Price": "$0.057",
            "Currency": "USD"
          },
          {
            "Quantity": 1000,
            "Price": "$0.031",
            "Currency": "USD"
          },
          {
            "Quantity": 3000,
            "Price": "$0.026",
            "Currency": "USD"
          },
          {
            "Quantity": 9000,
            "Price": "$0.021",
            "Currency": "USD"
          },
          {
            "Quantity": 24000,
            "Price": "$0.019",
            "Currency": "USD"
          },
          {
            "Quantity": 45000,
            "Price": "$0.016",
            "Currency": "USD"
          },
          {
            "Quantity": 99000,
            "Price": "$0.015",
            "Currency": "USD"
          }
        ],
        "AlternatePackagings": null,
        "ProductDetailUrl": "https://www.mouser.com/ProductDetail/onsemi/BAT54SLT1G?qs=vLkC5FC1VN9oCh8qaBIZiQ%3D%3D",
        "Reeling": true,
        "ROHSStatus": "RoHS Compliant",
        "SuggestedReplacement": "",
        "MultiSimBlue": 0,
        "UnitWeightKg": {
          "UnitWeight": 0.00003
        },
        "AvailabilityInStock": "1498379",
        "AvailabilityOnOrder": [],
        "InfoMessages": [],
        "ProductCompliance": [
          {
            "ComplianceName": "USHTS",
            "ComplianceValue": "8541100070"
          },
          {
            "ComplianceName": "CNHTS",
            "ComplianceValue": "8541590000"
          },
          {
            "ComplianceName": "CAHTS",
            "ComplianceValue": "8541100090"
          },
          {
            "ComplianceName": "KRHTS",
            "ComplianceValue": "8541109000"
          },
          {
            "ComplianceName": "TARIC",
            "ComplianceValue": "8541100000"
          },
          {
            "ComplianceName": "MXHTS",
            "ComplianceValue": "8541100101"
          },
          {
            "ComplianceName": "ECCN",
            "ComplianceValue": "EAR99"
          }
        ]
      }
    ]
  }
}"""
            )

        monkeypatch.setattr(requests, "post", fake_post)
        mouser_part = MouserClient().get_part("863-BAT54SLT1G-2")
        assert mouser_part.name == "BAT54SLT1G"
        assert mouser_part.description == "Schottky Diodes & Rectifiers 30V 225mW Dual"
        assert (
            mouser_part.url_path
            == "/ProductDetail/onsemi/BAT54SLT1G?qs=vLkC5FC1VN9oCh8qaBIZiQ%3D%3D"
        )

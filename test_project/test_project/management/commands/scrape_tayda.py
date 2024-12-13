import re
import io
import logging

from django.core.management.base import BaseCommand
from bs4 import BeautifulSoup
import cloudscraper

from django_ctb import models

logger = logging.getLogger(__name__)


class TaydaScraper:
    name = ""
    symbol = ""
    technology = models.CircuitTechnologyEnum.THROUGH_HOLE
    package_name = ""
    unit = models.UnitEnum.NONE
    volume = 1
    name_regex = None
    name_reject = None
    name_accept = None
    custom_info_regex = None
    custom_info_reject = None
    custom_info_accept = None

    def __init__(self, page_content, vendor):
        self.package = None
        if self.package_name:
            self.package, _ = models.Package.objects.get_or_create(
                name=self.package_name, technology=self.technology
            )
        self.vendor = vendor
        self.base_url = vendor.base_url
        self.soup = BeautifulSoup(page_content, features="html.parser")

    def get_package(self, **kwargs):
        return self.package

    def parse_name(self, name):
        if self.name_regex is not None:
            matches = self.name_regex.match(name)
            return matches.groupdict()
        return {}

    def parse_custom_info(self, custom_info):
        matches = self.custom_info_regex.match(custom_info)
        return matches.groupdict()

    def massage_item_data__value(self, value):
        return value.replace(" ", "")

    def massage_item_data(self, item_data):
        to_update = {}
        for key, value in item_data.items():
            if hasattr(self, f"massage_item_data__{key}"):
                item_data[key] = getattr(self, f"massage_item_data__{key}")(value)
        for key, value in item_data.items():
            if value is not None:
                item_data[key] = value
            if key.endswith("_"):
                to_update[key[:-1]] = value
        for key, value in to_update.items():
            del item_data[key + "_"]
            if value is not None and not key.endswith("_"):
                item_data[key] = value
        return item_data

    def parse_item(self, item_tag):
        link = item_tag.find("a", class_="product-item-link")
        # get name
        name = link.string.strip()
        print(f">> Name like: {name}")
        if self.name_reject is not None:
            if self.name_reject.match(name):
                print(">> Skipping this entry -- name reject")
                return
        if self.name_accept is not None:
            if not self.name_accept.match(name):
                print(">> Cannot accept this entry")
                return
        custom_info = item_tag.find("div", class_="custom-info")
        if custom_info is not None:
            custom_info = custom_info.text
        if self.custom_info_reject is not None and custom_info is not None:
            if self.custom_info_reject.match(custom_info):
                print(">> Skipping this entry (custom-info rejectable)")
                return
        if self.custom_info_accept is not None and custom_info is not None:
            if not self.custom_info_accept.match(custom_info):
                print(">> Skipping this entry (custom-info not acceptable)")
                return
        item_data = self.parse_name(name)
        print(f">> Parsed into: {item_data}")
        if self.custom_info_regex is not None and custom_info is not None:
            print(f">> Custom info: {custom_info}")
            item_data.update(self.parse_custom_info(custom_info))
            print(f">> Parsed into: {item_data}")
        package = self.get_package(**item_data)
        item_data = self.massage_item_data(item_data)
        print(f">> Morphed into: {item_data}")
        # get url path
        path = link["href"].replace(self.base_url, "")
        print(f">> Stripped path: {path}")
        # get item number
        sku_qty = item_tag.find("div", class_="product-item-sku-qty").string
        print(f">> sku_qty like: {sku_qty}")
        _sku, _ = sku_qty.split("|")
        _, sku = _sku.rsplit(":", maxsplit=1)
        sku = sku.strip()
        print(f">> item number: {sku}")
        cost = item_tag.find("span", class_="price").string.strip(" $")
        print(f">> cost: {cost}")
        part, _ = models.Part.objects.update_or_create(
            symbol=self.symbol,
            package=package,
            description=name,
            **item_data,
            defaults={
                "name": self.name,
                "unit": self.unit,
                "_is_scraped": True,
            },
        )
        models.VendorPart.objects.update_or_create(
            vendor=self.vendor,
            part=part,
            defaults={
                "item_number": sku,
                "url_path": path,
                "cost": cost,
                "volume": self.volume,
            },
        )
        print(f">> Created part and vendor part")

    def parse(self):
        # get each item on page
        print("parsing")
        for item_tag in self.soup.find_all("li", class_="product-item"):
            print(f"Found item")
            self.parse_item(item_tag)
            print(f"Done parsing item")


class SmdResistorScraper(TaydaScraper):
    name = "SMD Resistor"
    technology = models.CircuitTechnologyEnum.SURFACE_MOUNT
    symbol = "R"
    package_name = "0805"
    unit = models.UnitEnum.OHM
    volume = 50
    name_regex = re.compile(
        r"(?P<value>[\d.]+[KM]?)\s+Ohm\s+"
        r"(?P<loading_limit>[\d/]+W)\s+"
        r"(?P<tolerance>[\d]+)%\s+"
        r"0805\s+SMD\s+Chip\s+Resistor.*",
        re.I,
    )


class SmdCapacitorScraper(TaydaScraper):
    name = "SMD Capacitor"
    symbol = "C"
    technology = models.CircuitTechnologyEnum.SURFACE_MOUNT
    package_name = "0805"
    unit = models.UnitEnum.FARAD
    volume = 50
    name_regex = re.compile(
        r"(?P<value>[\d.]+\s?[npu]?)F\s+(?:[\d.]+\wF\s+)?"
        r"(?:(?P<tolerance_>[\d]+)%\s+)?"
        r"(?P<loading_limit>[\d/]+V)\s+"
        r"(?:±?(?P<tolerance>[\d]+)%\s+)?"
        r"(?:X7R\s+)?SMD\s+(?:Ceramic\s+)?Chip\s+Capacitor.*",
        re.I,
    )


class RadialTantalumCapacitorScraper(TaydaScraper):
    name = "Radial Tantalum Capacitor"
    symbol = "C"
    package_name = "Radial Cap D5"
    unit = models.UnitEnum.FARAD
    volume = 1
    name_reject = re.compile(".*chip.*", re.I)
    name_regex = re.compile(
        r"(?P<value>[\d.]+\s?[npu]?)F\s+(?:[\d.]+\wF\s+)?"
        r"(?:(?P<tolerance_>[\d]+)%\s+)?"
        r"(?P<loading_limit>[\d/.]+V\s)"
        r"(?:\s+±?(?P<tolerance>[\d]+)%\s+)?"
        r"(?:[\w\s]+)?",
        re.I,
    )

    def massage_item_data(self, item_data):
        item_data = super().massage_item_data(item_data)
        item_data["value"] = f"{item_data['value']} {item_data['loading_limit']} Tant"
        return item_data


class RadialCapacitorScraper(TaydaScraper):
    name = "Radial Capacitor"
    symbol = "C"
    package_name = "Radial Cap D5"
    unit = models.UnitEnum.FARAD
    volume = 1
    name_reject = re.compile(".*axial.*", re.I)
    name_regex = re.compile(
        r"(?P<value>[\d.]+\s?[npu]?)F\s+(?:[\d.]+\wF\s+)?"
        r"(?:(?P<tolerance_>[\d]+)%\s+)?"
        r"(?P<loading_limit>[\d/.]+V)\s+(?P<temp>\d+C)"
        r"(?:\s+±?(?P<tolerance>[\d]+)%\s+)?"
        r"(?:[\w\s]+)?\s+(?P<diameter__>[\d.]+)x[\d.]+mm.*",
        re.I,
    )

    def massage_item_data(self, item_data):
        item_data = super().massage_item_data(item_data)
        item_data["value"] = f"{item_data['value']} {item_data['loading_limit']}"
        item_data["loading_limit"] = f"{item_data['loading_limit']} {item_data['temp']}"
        del item_data["temp"]
        return item_data

    def get_package(self, diameter__, **kwargs):
        package, _ = models.Package.objects.get_or_create(
            technology=models.CircuitTechnologyEnum.THROUGH_HOLE,
            name=f"Radial Cap D{diameter__}",
        )
        return package


class RadialMylarCapacitorScraper(TaydaScraper):
    name = "Radial Mylar Capacitor"
    symbol = "C"
    package_name = "Mylar Cap"
    unit = models.UnitEnum.FARAD
    volume = 1
    name_reject = re.compile(".*axial.*", re.I)
    name_regex = re.compile(
        r"(?P<value>[\d.]+\s?[npu]?)F\s+(?:[\(\)\d.]+(?:\wF)?\s+)?"
        r"(?:(?P<tolerance_>[\d]+)%\s+)?"
        r"(?P<loading_limit>[\d/.]+V)\s?"
        r"(?:(?P<tolerance>[\d]+)%\s+)?.*Mylar.*",
        re.I,
    )
    custom_info_reject = re.compile(r"Size.*", re.I)
    custom_info_regex = re.compile(r".*Spacing: (?P<spacing__>[\d.]+mm).*", re.I)

    def get_package(self, spacing__=None, **kwargs):
        if spacing__ is not None:
            package, _ = models.Package.objects.get_or_create(
                technology=models.CircuitTechnologyEnum.THROUGH_HOLE,
                name=f"Mylar Cap S{spacing__}",
            )
            return package
        return self.package


class PolyesterFilmBoxTypeCapacitorScraper(TaydaScraper):
    name = "Polyester Film Box Capacitor"
    symbol = "C"
    package_name = "R82-7.2mm"
    unit = models.UnitEnum.FARAD
    volume = 1
    name_reject = re.compile(".*(?:10%|WIMA).*", re.I)
    custom_info_accept = re.compile(r"JB Capacitor.*", re.I)
    name_regex = re.compile(
        r"(?P<value>[\d.]+\s?[npu]?)F\s+(?:[\(\)\d.]+(?:\wF)?\s+)?"
        r"(?P<loading_limit>[\d/.]+V)\s?"
        r"(?:(?P<tolerance>[\d]+)(?:\.\d+)?%\s+)?"
        r"(?:[\w\s]+)?Polyester Film Box Type Capacitor.*",
        re.I,
    )

    def massage_item_data(self, item_data):
        item_data = super().massage_item_data(item_data)
        item_data["value"] = f"{item_data['value']} box"
        return item_data


class Smd0603CapacitorScraper(SmdCapacitorScraper):
    package_name = "0603"
    technology = models.CircuitTechnologyEnum.SURFACE_MOUNT


class CermetTrimmerScraper(TaydaScraper):
    name = "3296W Trimmer"
    symbol = "RV"
    package_name = "3296W"
    unit = models.UnitEnum.OHM
    name_regex = re.compile(r"(?P<value>[\d]+[KM]?)\s+Ohm\s+.*", re.I)


class Cermet3006PTrimmerScraper(TaydaScraper):
    name = "3006P Trimmer"
    symbol = "RV"
    package_name = "3006P"
    unit = models.UnitEnum.OHM
    name_regex = re.compile(r"(?P<value>[\d]+[KM]?)\s+Ohm\s+.*", re.I)


class AlphaPotScraper(TaydaScraper):
    name = "Alpha Potentiomenter"
    symbol = "RV"
    package_name = "RV16AF-41-15R1"
    # package_name = "RV16A01F-41-15R1"  # Dual gang
    unit = models.UnitEnum.OHM
    name_reject = re.compile(r".*(?:Tayda).*")
    name_regex = re.compile(r"[^Dd]*(?P<dual__>Dual)?.*")
    custom_info_reject = re.compile(r".*(?:9mm).*", re.I)
    custom_info_regex = re.compile(r".*(?P<value>[ABCW]\d+[KM]?).*", re.I)

    def get_package(self, dual__, **kwargs):
        if dual__ is not None:
            package, _ = models.Package.objects.get_or_create(
                technology=models.CircuitTechnologyEnum.THROUGH_HOLE,
                name="RV16A01F-41-15R",
            )
            return package
        return self.package


class SubMiniToggleSwitchScraper(TaydaScraper):
    name = "Sub Mini Toggle Switch"
    symbol = "SW"
    package_name = ""
    unit = models.UnitEnum.NONE
    name_reject = re.compile(r"^.*Solder Lug", re.I)
    name_accept = re.compile(r"^Sub Mini.*", re.I)
    name_regex = re.compile(
        r"Sub mini toggle switch \dM series "
        r"(?P<value>[\w\d]p[\w\d]t [(?:on)(?:off)-]+).*",
        re.I,
    )

    def get_package(self, value, **kwargs):
        _value, _ = value.split(" ")
        package, _ = models.Package.objects.get_or_create(
            technology=models.CircuitTechnologyEnum.THROUGH_HOLE,
            name=f"2M-{_value.upper()}",
        )
        return package

    def massage_item_data__value(self, value):
        return value


class PushButtonScraper(TaydaScraper):
    name = "Push Button"
    symbol = "SW"
    package_name = ""
    unit = models.UnitEnum.NONE
    name_accept = re.compile(r".*Panel Mount.*", re.I)
    name_regex = re.compile(
        r"Push Button (?:Switch )?(?:Momentary|Latching) Panel Mount "
        r"[\w]+ knob "
        r"(?P<value>.*)",
        re.I,
    )

    def get_package(self, value, **kwargs):
        _value = value.replace(" ", "-")
        package, _ = models.Package.objects.get_or_create(
            technology=models.CircuitTechnologyEnum.THROUGH_HOLE,
            name=f"push-button-{_value.upper()}",
        )
        return package

    def massage_item_data__value(self, value):
        return value


class LedScraper(TaydaScraper):
    name = "3mm LED"
    symbol = "D"
    package_name = "LED D3mm"
    name_accept = re.compile(r"LED 3mm [\w]+$")
    name_regex = re.compile(r"(?P<value>LED) 3mm [\w]+")


class ZenerDiodeScraper(TaydaScraper):
    """TZMB13-GS08 Small Signal Zener Diodes 5mA 13V"""

    name = "Zener Diode"
    symbol = "Z"
    package_name = "MiniMELF"
    name_accept = re.compile(r"^[\w\d]*-GS08 .*$")
    name_regex = re.compile(
        r"^[\w\d]*-GS08 Small Signal Zener Diodes "
        r"(?P<loading_limit>[\d/.]+[um]A)\s?"
        r"(?P<value>[\d.]*?V)",
        re.I,
    )

    def massage_item_data(self, item_data):
        _data = super().massage_item_data(item_data)
        _data["value"] = "Zener " + _data["value"]
        return _data


class Command(BaseCommand):
    help = "Scrape selected set of Tayda Electronics pages to populate parts and vendor parts"
    base_url = "https://www.taydaelectronics.com"

    def handle(self, **kwargs):
        print("here")
        self.session = cloudscraper.CloudScraper()
        params = {"product_list_limit": "all"}
        vendor, _ = models.Vendor.objects.get_or_create(
            name="Tayda", base_url=self.base_url
        )
        pages = {
            "/diodes/zener.html": ZenerDiodeScraper,
            # "/potentiometer-variable-resistors/cermet-potentiometers/3006p.html": Cermet3006PTrimmerScraper,
            # "/potentiometer-variable-resistors/cermet-potentiometers/3296w.html": CermetTrimmerScraper,
            # "/capacitors/smd-ceramic-chip-capacitors/0805.html": SmdCapacitorScraper,
            # "/capacitors/smd-ceramic-chip-capacitors/0603.html": Smd0603CapacitorScraper,
            # "/capacitors/tantalum-capacitors.html": RadialTantalumCapacitorScraper,
            # "/leds/round-leds/3mm-leds.html": LedScraper,
        }
        for path, parser_klass in pages.items():
            response = self.session.get(self.base_url + path, params=params)
            parser_klass(
                page_content=io.BytesIO(response.content), vendor=vendor
            ).parse()

        # Overcome pagination by downloading full html
        scrapes = {
            # "0805 - SMD Chip Resistors - Resistors.html": SmdResistorScraper,
            # "Rotary Potentiometer - Potentiometer _ Variable Resistors.html": AlphaPotScraper,
            # "Electrolytic Capacitors - Capacitors.html": RadialCapacitorScraper,
            # "Polyester Mylar Film Capacitors - Capacitors.html": RadialMylarCapacitorScraper,
            # "Toggle Switch - Switches, Key Pad - Electromechanical.html": SubMiniToggleSwitchScraper,
            # "Push Button - Switches, Key Pad - Electromechanical.html": PushButtonScraper,
            # "Polyester Film Box Type Capacitors - Capacitors.html": PolyesterFilmBoxTypeCapacitorScraper,
        }
        for scrape, parser_klass in scrapes.items():
            with open("scrapes/" + scrape) as file:
                parser_klass(page_content=file, vendor=vendor).parse()
        self.session.close()

        """manual stuff:
        * diodes (1N4148)
        * Audio jacks
        * box headers
        * socket connector
        * LED bezel
        """

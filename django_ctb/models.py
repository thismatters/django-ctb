"""
Data models (and database models) for stock and projects.
"""

import re
from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone
from pydantic import AliasChoices, BaseModel, Field, field_validator

from django_ctb import conf  # noqa: F401

if TYPE_CHECKING:
    from django_stubs_ext.db.models.manager import RelatedManager


class Footprint(models.Model):
    """
    The manifestation of the part onto the printed circuit board. The
    footprint appears on the bill of materials, parts will be selected based
    in part on the footprint name match.
    """

    name = models.CharField(max_length=64)

    def __str__(self):  # pragma: no cover
        return self.name


class Package(models.Model):
    """
    The form factor for a part. E.g. Surface mount 0805, or TO-92.
    """

    class Technology(models.IntegerChoices):
        THROUGH_HOLE = 0
        SURFACE_MOUNT = 1
        UNKNOWN = 2

    technology = models.PositiveSmallIntegerField(
        choices=Technology, default=Technology.UNKNOWN
    )
    name = models.CharField(max_length=32, help_text="e.g. 0805, or TO-92W")
    footprints = models.ManyToManyField(Footprint, blank=True)

    def __str__(self):  # pragma: no cover
        return f"{self.get_technology_display()} {self.name}"  # type: ignore[unresolve-attribute]


class Vendor(models.Model):
    """
    Places where parts can be procured. e.g. Mouser, Tayda Electronics
    """

    name = models.CharField(max_length=64)
    base_url = models.URLField(help_text="sans trailing slash plz")

    def __str__(self):  # pragma: no cover
        return self.name


class Part(models.Model):
    """
    Individual parts which are available for procurement from a vendor and
    will be assembled into a project. e.g. a 100 Ohm surface mount (0805)
    resistor, or an NPN TO-92 transistor.

    The ``value`` attribute of the part will be matched to the ``value`` row
    on the bill of materials.
    """

    class Unit(models.IntegerChoices):
        NONE = 0
        OHM = 1
        FARAD = 2
        HENRY = 3
        VOLT = 4
        AMPERE = 5

    name = models.CharField(max_length=64)
    description = models.CharField(max_length=256, null=True, blank=True)
    value = models.CharField(
        max_length=32,
        help_text="Value as found on BOM e.g. '10K', '22u'",
        null=True,
        blank=True,
    )
    tolerance = models.SmallIntegerField(
        help_text="as percentage", null=True, blank=True
    )
    loading_limit = models.CharField(max_length=16, null=True, blank=True)
    unit = models.PositiveSmallIntegerField(choices=Unit, default=Unit.NONE)
    symbol = models.CharField(
        max_length=4,
        help_text="What prefix might this part have on a circuit schematic?",
        null=True,
        blank=True,
    )
    package = models.ForeignKey(
        Package, on_delete=models.PROTECT, null=True, blank=True
    )
    vendors = models.ManyToManyField(Vendor, related_name="parts", through="VendorPart")
    _is_scraped = models.BooleanField(default=False)
    equivalent_to = models.ForeignKey(
        "Part",
        on_delete=models.SET_NULL,
        related_name="equivalents",
        null=True,
        blank=True,
    )

    if TYPE_CHECKING:
        equivalents: RelatedManager["Part"]
        part_vendors: RelatedManager["VendorPart"]
        inventory_lines: RelatedManager["InventoryLine"]

    def __str__(self):  # pragma: no cover
        return f"{self.name} {self.symbol} {self.value} -- {self.package}"

    @property
    def unit_cost(self):
        """
        Extrapolated cost for each individual part
        """
        part_vendor = self.part_vendors.all().order_by("cost").first()
        if part_vendor is not None:
            return part_vendor.cost
        return 0


class ImplicitProjectPart(models.Model):
    """Certain parts do not appear on the BOM, but must be used for the final
    build. These are represented here. e.g. LED bezel, potentiometer knob, even
    the PCB could fit in this category?"""

    part = models.ForeignKey(Part, on_delete=models.PROTECT)
    for_package = models.ForeignKey(Package, on_delete=models.PROTECT)
    quantity = models.SmallIntegerField(default=1)


class VendorPart(models.Model):
    """
    The representation of a part as sold by a vendor. Pricing, item numbers,
    url paths are stored here.
    """

    vendor = models.ForeignKey(
        Vendor, related_name="vendor_parts", on_delete=models.PROTECT
    )
    part = models.ForeignKey(
        Part, related_name="part_vendors", on_delete=models.CASCADE
    )
    item_number = models.CharField(
        max_length=64, help_text="how the vendor identifies the part"
    )
    cost = models.DecimalField(
        decimal_places=4,
        max_digits=8,
        help_text="Cost per unit when purchased at given volume",
        null=True,
        blank=True,
    )
    volume = models.PositiveIntegerField(
        help_text="Must purchase this many to get cost",
        null=True,
        blank=True,
    )
    url_path = models.CharField(
        max_length=128, help_text="includes the leading slash!", null=True, blank=True
    )
    lot_cost = models.GeneratedField(
        expression=models.F("cost") * models.F("volume"),
        output_field=models.DecimalField(decimal_places=4, max_digits=8),
        db_persist=False,
    )

    @property
    def url(self):  # pragma: no cover
        """
        URL to the vendor part
        """
        return f"{self.vendor.base_url}{self.url_path}"

    def __str__(self):  # pragma: no cover
        return f"{self.vendor} - {self.item_number} - {self.part.name}"

    class Meta:
        ordering = ("vendor__name", "item_number")


class VendorOrder(models.Model):
    """
    Represents orders of parts from a vendor.
    """

    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="orders")
    order_number = models.CharField(max_length=128, null=True, blank=True)
    created = models.DateTimeField(default=timezone.now)
    placed = models.DateTimeField(null=True, blank=True)
    fulfilled = models.DateTimeField(null=True, blank=True)

    def __str__(self):  # pragma: no cover
        return f"{self.vendor} #{self.order_number}"

    if TYPE_CHECKING:
        lines: RelatedManager["VendorOrderLine"]


class VendorOrderLine(models.Model):
    """
    Represents lines for individual parts in orders.
    """

    vendor_order = models.ForeignKey(
        VendorOrder, on_delete=models.CASCADE, related_name="lines"
    )
    vendor_part = models.ForeignKey(
        VendorPart, on_delete=models.PROTECT, related_name="lines"
    )
    quantity = models.PositiveIntegerField()
    cost = models.DecimalField(decimal_places=4, max_digits=8, help_text="per unit")
    for_inventory = models.ForeignKey("Inventory", on_delete=models.PROTECT)

    def __str__(self):  # pragma: no cover
        return (
            f"{self.vendor_order.vendor} {self.vendor_order.order_number} "
            f"x{self.quantity}"
        )


class Inventory(models.Model):
    """
    Container for complete stock of parts available for usage in project
    builds.
    """

    name = models.CharField(max_length=64)

    class Meta:
        verbose_name_plural = "Inventories"

    def __str__(self):  # pragma: no cover
        return self.name


class InventoryLine(models.Model):
    """
    Represents the stock of an individual part.
    """

    created = models.DateTimeField(default=timezone.now)
    updated = models.DateTimeField(auto_now=True)
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT)
    part = models.ForeignKey(
        Part, on_delete=models.PROTECT, related_name="inventory_lines"
    )
    quantity = models.IntegerField(
        default=0,
        help_text="quantity on hand (unused reservations are removed from this number)",
    )
    is_deprioritized = models.BooleanField(default=False)

    if TYPE_CHECKING:
        inventory_actions: RelatedManager["InventoryAction"]

    @property
    def item_numbers(self) -> str:
        """
        Returns all item numbers from all vendors for the part in the
        inventory line (comma separated).
        """
        _item_numbers = []
        for vendor_part in self.part.part_vendors.all():
            _item_numbers.append(vendor_part.item_number)
        return ", ".join(_item_numbers)

    def __str__(self):  # pragma: no cover
        return f"{self.quantity}x {self.part} {self.item_numbers}"

    @property
    def quantity_on_hand(self) -> int:
        """
        Number of parts which are countable in physical inventory
        (includes numbers from pending or cleared reservations).
        """
        pending_quantity = sum(
            self.inventory_actions.filter(
                reservation__isnull=False, reservation__utilized__isnull=True
            ).values_list("delta", flat=True)
        )
        # values for delta are negative
        return self.quantity - pending_quantity


class InventoryAction(models.Model):
    """
    Tracks changes to inventory lines when orders are fulfilled and when
    project build parts are reserved.
    """

    inventory_line = models.ForeignKey(
        InventoryLine, on_delete=models.CASCADE, related_name="inventory_actions"
    )
    # what happened
    delta = models.IntegerField()
    # why did it happen (order fulfilled | project built | correction)
    order_line = models.ForeignKey(
        VendorOrderLine, on_delete=models.PROTECT, null=True, blank=True
    )
    # which reservation (unutilized | utilized)
    reservation = models.ForeignKey(
        "ProjectBuildPartReservation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_actions",
    )
    # when did it happen
    created = models.DateTimeField(default=timezone.now)

    def __str__(self):  # pragma: no cover
        if self.order_line is not None:
            return (
                f"{self.delta} {self.inventory_line.part} from "
                f"{self.order_line.vendor_order.vendor.name}"
            )
        else:
            return f"{self.delta:+} {self.inventory_line.part}"


class Project(models.Model):
    """
    A thing you are building. This is a thin model with just a name and a url
    to a git repo. The repo must have a CSV file which is the Bill Of Materials
    (BOM) for the project. KiCAD generates such BOMs as a default feature.
    """

    class GitServer(models.IntegerChoices):
        UNKNOWN = 0
        GITHUB = 1

    name = models.CharField(max_length=64)

    git_server = models.PositiveSmallIntegerField(
        choices=GitServer, default=GitServer.GITHUB
    )
    git_user = models.CharField(max_length=64, null=True)
    git_repo = models.CharField(max_length=64, null=True)

    @property
    def git_url(self) -> str:
        """
        URL to the git repo represented by the project.
        """
        _url: str = "https://"
        if self.git_server == self.GitServer.GITHUB:
            _url += "github.com"
        _url += f"/{self.git_user}/{self.git_repo}"
        return _url

    def __str__(self):  # pragma: no cover
        return self.name


class ProjectVersion(models.Model):
    """
    A point-in-time representation of the project. Requires a commit ref
    (branch, tag, or commit hash) which exists in the repository, and the
    path within the repo to the bill of materials.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    revision = models.IntegerField(default=0)
    commit_ref = models.CharField(
        max_length=64, help_text="Commit or tag representing the version"
    )
    bom_path = models.CharField(max_length=100)
    pcb_url = models.URLField(help_text="OSH park link to pcb", null=True, blank=True)
    pcb_cost = models.DecimalField(
        decimal_places=2, max_digits=6, help_text="for lot of 3", null=True, blank=True
    )
    synced = models.DateTimeField(null=True, blank=True)
    last_synced_commit = models.CharField(max_length=64, null=True, blank=True)

    def __str__(self):  # pragma: no cover
        return f"{self.project} v{self.revision}"

    if TYPE_CHECKING:
        project_parts: RelatedManager["ProjectPart"]

    @property
    def pcb_unit_cost(self) -> float:
        """
        The cost for a single PCB (assumes a PCB lot size of 3 per the minimum
        batch size at oshpark.com).
        """
        if self.pcb_cost is None:
            return 0.0
        return self.pcb_cost / 3

    @property
    def total_cost(self) -> float:
        """
        Extrapolates the full cost for all parts and PCB for this project
        version.
        """
        return self.pcb_unit_cost + sum([p.line_cost for p in self.project_parts.all()])

    @property
    def _bom_url_template(self) -> str:
        """
        The URL to the Bill of Materials computed from project and version data
        e.g. https://github.com/thismatters/EurorackLfo/raw/main/lfo.csv
        """
        _bom_path = self.bom_path.lstrip("/")
        return f"{self.project.git_url}/raw/{{commit_ref}}/{_bom_path}"

    @property
    def bom_url(self) -> str:
        """
        The URL to the Bill of Materials computed from project and version data
        e.g. https://github.com/thismatters/EurorackLfo/raw/main/lfo.csv
        """
        return self._bom_url_template.format(commit_ref=self.commit_ref)

    def bom_url_for_commit(self, commit_ref: str) -> str:
        """
        The URL to the Bill of Materials computed from project and version data
        using the given commit ref
        e.g. https://github.com/thismatters/EurorackLfo/raw/<commit_ref>/lfo.csv
        """
        return self._bom_url_template.format(commit_ref=commit_ref)


class ProjectPart(models.Model):
    """
    Representation of a BOM line for a project version. Holds references to the
    individual part, the footprint references (where the parts will be placed
    on the PCB), and the BOM line number. Allows for manual assignment of a
    substitute part.
    """

    part = models.ForeignKey(
        Part,
        on_delete=models.PROTECT,
        related_name="project_parts",
        null=True,
        blank=True,
    )
    substitute_part = models.ForeignKey(
        Part,
        on_delete=models.PROTECT,
        related_name="substitute_project_part",
        null=True,
        blank=True,
        help_text=(
            "When set, the substitute part will be used instead of the actual part"
        ),
    )
    missing_part_description = models.CharField(max_length=256, null=True, blank=True)
    project_version = models.ForeignKey(
        ProjectVersion, on_delete=models.CASCADE, related_name="project_parts"
    )
    line_number = models.SmallIntegerField()
    quantity = models.SmallIntegerField()
    is_implicit = models.BooleanField(default=False)
    is_optional = models.BooleanField(default=False)

    if TYPE_CHECKING:
        footprint_refs: RelatedManager["ProjectPartFootprintRef"]

    @property
    def line_cost(self):
        """
        Extrapolates the cost for the parts to satisfy this project part
        """
        if self.part is None:
            return 0
        if self.part.unit_cost is None:
            return 0
        return self.part.unit_cost * self.quantity

    @property
    def footprints(self):
        """
        Formats the footprint refrences into a comma-separated string.
        """
        _footprint_refs = self.footprint_refs.values_list("footprint_ref", flat=True)
        if self.is_optional:
            _footprint_refs = [_ref + "*" for _ref in _footprint_refs]
        return ", ".join(_footprint_refs)

    def __str__(self):
        _part = f"line {self.line_number} (part missing)"
        if self.part is not None:
            _part = str(self.part)
        return f"{_part} for {self.project_version}"


class ProjectPartFootprintRef(models.Model):
    """
    The actual, individual footprint ref where a project part will land on the
    PCB (e.g. R12)
    """

    project_part = models.ForeignKey(
        ProjectPart, on_delete=models.CASCADE, related_name="footprint_refs"
    )
    footprint_ref = models.CharField(max_length=8)

    def __str__(self):  # pragma: no cover
        return self.footprint_ref


class ProjectBuild(models.Model):
    """
    Represents a manufacturing run of a project version. Specify the number of
    instances of the project version that you will build.

    Any ``ProjectPart`` objects which were marked "optional" may be added to
    the ``excluded_project_parts``. When added, these project parts will not
    be omitted from clearing actvities.
    """

    project_version = models.ForeignKey(ProjectVersion, on_delete=models.PROTECT)
    quantity = models.SmallIntegerField()
    created = models.DateTimeField(default=timezone.now)
    cleared = models.DateTimeField(null=True, blank=True)
    completed = models.DateTimeField(null=True, blank=True)
    excluded_project_parts = models.ManyToManyField(
        ProjectPart,
        blank=True,
    )

    if TYPE_CHECKING:
        shortfalls: RelatedManager["ProjectBuildPartShortage"]

    @property
    def is_complete(self) -> bool:
        """
        Returns true if the project build has been completed.
        """
        return self.completed is not None

    def __str__(self):  # pragma: no cover
        suffix = ""
        if self.completed is not None:
            suffix = " [completed]"
        elif self.cleared is not None:
            suffix = " [cleared]"
        return f"{self.quantity}x {self.project_version}{suffix}"


class ProjectBuildPartShortage(models.Model):
    """
    Represents a part shortage which prevents a project build from being
    cleared.
    """

    part = models.ForeignKey(Part, on_delete=models.CASCADE)
    quantity = models.SmallIntegerField()
    project_build = models.ForeignKey(
        ProjectBuild, on_delete=models.CASCADE, related_name="shortfalls"
    )
    created = models.DateTimeField(default=timezone.now)


class ProjectBuildPartReservation(models.Model):
    """
    Reservations for parts to cover a project build.

    Reservations map to a ``Part`` and a ``ProjectPuild``.
    """

    # Okay, so. Project parts map to bom rows, and bom rows do not come with
    # any guarantees about part uniqueness across rows. So, it is possible for
    # more than one project part to share the same actual part. It is also
    # possible for there to be more than one inventory line associated with a
    # given project part (if, say, two equivalent parts have inventory lines
    # which only together cover the project, or if there are just two inventory
    # lines with the same exact part (for whatever reason)).

    project_build = models.ForeignKey(
        ProjectBuild, on_delete=models.CASCADE, related_name="part_reservations"
    )
    # We consolidate across the whole build on the ``part``, then create a
    # reservation which covers the full quantity (perhaps across several
    # inventory actions for equivalent lines as needed), and traceable to the
    # several project parts that share the same part.
    part = models.ForeignKey(
        Part,
        on_delete=models.SET_NULL,
        related_name="reservations",
        null=True,
    )

    # There may be more than one reservation per project part, given that
    # there is more than one build for a given project version.
    #
    # There may be more than one project part per reservation given more than
    # one bom row references the same part (e.g. when two jacks have a
    # different name).
    project_parts = models.ManyToManyField(
        ProjectPart, related_name="part_reservations"
    )
    # There may be more than one inventory action per reservation, given more
    # than one inventory line represents the part and any lacks sufficient
    # stock to complete the build alone (inventory actions cannot apply to
    # more than one reservation). (InventoryActions track the ``reservation``)

    created = models.DateTimeField(default=timezone.now)
    utilized = models.DateTimeField(null=True, blank=True)

    if TYPE_CHECKING:
        inventory_actions: RelatedManager[InventoryAction]

    @property
    def quantity(self) -> int:
        """
        The total quantity of parts encapsulated by this reservation (in a
        comma-separated string).
        """
        return sum(self.inventory_actions.all().values_list("delta", flat=True)) * -1

    @property
    def line_numbers(self) -> str:
        """
        All BOM line numbers encapsulated by this reservation (in a
        comma-sepaated string).
        """
        return ", ".join(
            [
                f"{line_num}"
                for line_num in self.project_parts.all().values_list(
                    "line_number", flat=True
                )
            ]
        )

    @property
    def footprints(self) -> str:
        """
        All footprint refs where parts will be placed (in a comma-separated
        string).
        """
        return (
            ", ".join(
                [
                    project_part.footprints
                    for project_part in self.project_parts.all()
                    if project_part.footprints
                ]
            )
            or "N/A"
        )


class BillOfMaterialsRow(BaseModel):
    """
    Maps to the default KiCAD BOM format with extra columns for "Vendor",
    "PartNum", and "Optional". Silently ignores any additional columns.
    """

    line_number: int | None = Field(validation_alias=AliasChoices("#", "line"))
    references: list[str] = Field(validation_alias=AliasChoices("Reference", "Ref"))
    quantity: int = Field(validation_alias=AliasChoices("Qty", "Qnty"))
    value: str = Field(alias="Value")
    footprint_name: str = Field(alias="Footprint")
    vendor_name: str | None = Field(alias="Vendor", default=None)
    item_number: str | None = Field(alias="PartNum", default=None)
    optional: bool = Field(alias="Optional", default=False)

    @property
    def symbols(self):
        """
        The footprint ref prefixes associated with the row. If the footprint
        refs for a line are "R1, R3", then the symbols will be "R".
        """
        return {r.strip("0123456789") for r in self.references}

    @field_validator("value", mode="before")
    @classmethod
    def normalize_value(cls, value: str):
        """Change "Value" column values to normalize potential formatting of
        component values with SI prefix __outside__ the value, and a period for
        a decimal separator:

        - 3M3 -> 3.3M (SI prefix greater than unity is capitalized)
        - 3U3 -> 3.3u (SI prefix less than unity is lowercased)
        - 1N4553 -> 1N4553 (Nano is excluded so that diodes don't get mangled)

        """
        matches = re.match(r"(?P<whole>\d+)(?P<prefix>[mMkKuUpPn])(?P<frac>\d+)", value)
        if matches is not None:
            _prefix = matches.group("prefix")
            if _prefix in "UP":
                _prefix = _prefix.lower()
            value = f"{matches.group('whole')}.{matches.group('frac')}{_prefix}"
        return value

    @field_validator("references", mode="before")
    @classmethod
    def split_and_strip(cls, value: str) -> list[str]:
        """
        Comma separated values in the "Reference" column will be split and
        stripped
        """
        return [v.strip() for v in value.split(",") if v.strip()]

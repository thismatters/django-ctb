from django.db import models
from django.utils import timezone

from django_enumfield import enum


class UnitEnum(enum.Enum):
    NONE = 0
    OHM = 1
    FARAD = 2
    HENRY = 3
    VOLT = 4
    AMPERE = 5

    __default__ = NONE

    __labels__ = {
        NONE: "None",
        OHM: "Ohm",
        FARAD: "F",
        HENRY: "H",
        VOLT: "V",
        AMPERE: "A",
    }


class CircuitTechnologyEnum(enum.Enum):
    THROUGH_HOLE = 0
    SURFACE_MOUNT = 1
    UNKNOWN = 2

    __labels__ = {
        THROUGH_HOLE: "THT",
        SURFACE_MOUNT: "SMD",
    }


class Footprint(models.Model):
    """Names of footprints as they might appear in BOM"""

    name = models.CharField(max_length=64)

    def __str__(self):  # pragma: no cover
        return self.name


class Package(models.Model):
    technology = enum.EnumField(CircuitTechnologyEnum)
    name = models.CharField(max_length=32, help_text="e.g. 0805, or TO-92W")
    footprints = models.ManyToManyField(Footprint, blank=True)

    def __str__(self):  # pragma: no cover
        return f"{self.technology.label} {self.name}"


class Vendor(models.Model):
    name = models.CharField(max_length=64)
    base_url = models.URLField(help_text="sans trailing slash plz")

    def __str__(self):  # pragma: no cover
        return self.name


class Part(models.Model):
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
    unit = enum.EnumField(UnitEnum)
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

    def __str__(self):  # pragma: no cover
        return f"{self.name} {self.symbol} {self.value} -- {self.package}"

    @property
    def unit_cost(self):
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
    # unit_cost = models.GeneratedField(
    #     expression=models.F("cost") / models.F("volume"),
    #     output_field=models.DecimalField(decimal_places=4, max_digits=8),
    #     db_persist=False,
    # )

    @property
    def url(self):  # pragma: no cover
        return f"{self.vendor.base_url}{self.url_path}"

    def __str__(self):  # pragma: no cover
        return f"{self.vendor} - {self.item_number}"

    class Meta:
        ordering = ("vendor__name", "item_number")


class VendorOrder(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    order_number = models.CharField(max_length=128, null=True)
    created = models.DateTimeField(default=timezone.now)
    fulfilled = models.DateTimeField(null=True, blank=True)

    def __str__(self):  # pragma: no cover
        return f"{self.vendor} #{self.order_number}"


class VendorOrderLine(models.Model):
    vendor_order = models.ForeignKey(
        VendorOrder, on_delete=models.CASCADE, related_name="lines"
    )
    vendor_part = models.ForeignKey(
        VendorPart, on_delete=models.PROTECT, related_name="lines"
    )
    quantity = models.PositiveIntegerField()
    cost = models.DecimalField(decimal_places=4, max_digits=8, help_text="per unit")
    for_inventory = models.ForeignKey("Inventory", on_delete=models.PROTECT)


class Inventory(models.Model):
    name = models.CharField(max_length=64)

    class Meta:
        verbose_name_plural = "Inventories"

    def __str__(self):  # pragma: no cover
        return self.name


class InventoryLine(models.Model):
    created = models.DateTimeField(default=timezone.now)
    updated = models.DateTimeField(auto_now=True)
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT)
    part = models.ForeignKey(
        Part, on_delete=models.PROTECT, related_name="inventory_lines"
    )
    quantity = models.IntegerField(default=0)
    is_deprioritized = models.BooleanField(default=False)


class InventoryAction(models.Model):
    inventory_line = models.ForeignKey(InventoryLine, on_delete=models.CASCADE)
    # what happened
    delta = models.IntegerField()
    # why did it happen (order fulfilled | project built | correction)
    order_line = models.ForeignKey(
        VendorOrderLine, on_delete=models.PROTECT, null=True, blank=True
    )
    build = models.ForeignKey(
        "ProjectBuild", on_delete=models.PROTECT, null=True, blank=True
    )
    # when did it happen
    created = models.DateTimeField(default=timezone.now)


class Project(models.Model):
    name = models.CharField(max_length=64)
    git_url = models.URLField(
        null=True,
        help_text="The URL of the repo, not the clone URI",
    )

    def __str__(self):  # pragma: no cover
        return self.name


class ProjectVersion(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    revision = models.IntegerField(default=0)
    commit_ref = models.CharField(
        max_length=64, help_text="Commit or tag representing the version"
    )
    bom_path = models.CharField(max_length=100)
    pcb_url = models.URLField(help_text="OSH park link to pcb", null=True, blank=True)
    parts = models.ManyToManyField(Part, related_name="projects", through="ProjectPart")
    pcb_cost = models.DecimalField(
        decimal_places=2, max_digits=6, help_text="for lot of 3", null=True, blank=True
    )
    synced = models.DateTimeField(null=True, blank=True)

    def __str__(self):  # pragma: no cover
        return f"{self.project} v{self.revision}"

    @property
    def pcb_unit_cost(self):
        if self.pcb_cost is None:
            return 0
        return self.pcb_cost / 3

    @property
    def total_cost(self):
        return self.pcb_unit_cost + sum([p.line_cost for p in self.project_parts.all()])


class ProjectPart(models.Model):
    part = models.ForeignKey(
        Part,
        on_delete=models.PROTECT,
        related_name="project_parts",
        null=True,
        blank=True,
    )
    missing_part_description = models.CharField(max_length=256, null=True, blank=True)
    project_version = models.ForeignKey(
        ProjectVersion, on_delete=models.CASCADE, related_name="project_parts"
    )
    line_number = models.SmallIntegerField()
    quantity = models.SmallIntegerField()
    is_implicit = models.BooleanField(default=False)

    @property
    def line_cost(self):
        return self.part.unit_cost * self.quantity

    # derived field for footprint refs?


class ProjectPartFootprintRef(models.Model):
    project_part = models.ForeignKey(
        ProjectPart, on_delete=models.CASCADE, related_name="footprint_refs"
    )
    footprint_ref = models.CharField(max_length=8)

    def __str__(self):  # pragma: no cover
        return self.footprint_ref


class ProjectBuild(models.Model):
    project_version = models.ForeignKey(ProjectVersion, on_delete=models.PROTECT)
    quantity = models.SmallIntegerField()
    created = models.DateTimeField(default=timezone.now)
    cleared = models.DateTimeField(null=True, blank=True)
    completed = models.DateTimeField(null=True, blank=True)

    def __str__(self):  # pragma: no cover
        return f"{self.quantity}x {self.project_version}"


class ProjectBuildPartShortage(models.Model):
    part = models.ForeignKey(Part, on_delete=models.CASCADE)
    quantity = models.SmallIntegerField()
    project_build = models.ForeignKey(
        ProjectBuild, on_delete=models.CASCADE, related_name="shortfalls"
    )
    created = models.DateTimeField(default=timezone.now)


class ProjectBuildPartReservation(models.Model):
    """When clear to build, the parts for the build will be deducted from
    their respective inventory lines and reserved here"""

    inventory_action = models.ForeignKey(
        InventoryAction, on_delete=models.PROTECT, null=True
    )
    project_build = models.ForeignKey(
        ProjectBuild, on_delete=models.CASCADE, related_name="part_reservations"
    )
    created = models.DateTimeField(default=timezone.now)
    utilized = models.DateTimeField(null=True, blank=True)

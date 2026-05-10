import factory
import factory.fuzzy

from django_ctb import models as m


class FootprintFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.Footprint"


class PackageFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.Package"

    @factory.post_generation  # type: ignore
    def footprints(self, create, extracted, **kwargs):
        if not create or not extracted:
            return

        self.footprints.add(*extracted)  # type: ignore


class VendorFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.Vendor"


class PartFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.Part"

    package = factory.SubFactory(PackageFactory)  # type: ignore

    # maybe not yet...
    # equivalent_to = factory.SubFactory(PartFactory)  # type: ignore

    @factory.post_generation  # type: ignore
    def vendors(self, create, extracted, **kwargs):
        if not create or not extracted:
            return

        self.vendors.add(*extracted)  # type: ignore


class ImplicitProjectPartFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ImplicitProjectPart"

    part = factory.SubFactory(PartFactory)  # type: ignore
    for_package = factory.SubFactory(PackageFactory)  # type: ignore


class VendorPartFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.VendorPart"

    vendor = factory.SubFactory(VendorFactory)  # type: ignore
    part = factory.SubFactory(PartFactory)  # type: ignore
    cost = factory.Faker(  # type: ignore
        "pydecimal", min_value=0.01, max_value=9999, left_digits=4, right_digits=4
    )


class VendorOrderFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.VendorOrder"

    vendor = factory.SubFactory(VendorFactory)  # type: ignore


class InventoryFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.Inventory"


class VendorOrderLineFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.VendorOrderLine"

    vendor_order = factory.SubFactory(VendorOrderFactory)  # type: ignore
    vendor_part = factory.SubFactory(VendorPartFactory)  # type: ignore
    for_inventory = factory.SubFactory(InventoryFactory)  # type: ignore

    # quantity = factory.fuzzy.FuzzyInteger(1, 1000)
    quantity = factory.Faker("random_int", min=1, max=1000)  # type: ignore
    cost = factory.Faker(  # type: ignore
        "pydecimal", min_value=0.01, max_value=9999, left_digits=4, right_digits=4
    )


class InventoryLineFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.InventoryLine"

    inventory = factory.SubFactory(InventoryFactory)  # type: ignore
    part = factory.SubFactory(PartFactory)  # type: ignore


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.Project"


class ProjectVersionFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ProjectVersion"

    project = factory.SubFactory(ProjectFactory)  # type: ignore
    pcb_cost = factory.Faker(  # type: ignore
        "pydecimal", min_value=0.01, max_value=9999, left_digits=4, right_digits=4
    )


class ProjectPartFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ProjectPart"

    part = factory.SubFactory(PartFactory)  # type: ignore
    project_version = factory.SubFactory(ProjectVersionFactory)  # type: ignore


class ProjectPartFootprintRefFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ProjectPartFootprintRef"

    project_part = factory.SubFactory(ProjectPartFactory)  # type: ignore


class ProjectBuildFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ProjectBuild"

    project_version = factory.SubFactory(ProjectVersionFactory)  # type: ignore
    quantity = factory.Faker("random_int", min=1, max=10)  # type: ignore

    @factory.post_generation  # type: ignore
    def excluded_project_parts(self, create, extracted, **kwargs):
        if not create or not extracted:
            return

        self.excluded_project_parts.add(*extracted)  # type: ignore


class ProjectBuildPartShortageFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ProjectBuildPartShortage"

    part = factory.SubFactory(PartFactory)  # type: ignore
    project_build = factory.SubFactory(ProjectBuildFactory)  # type: ignore


class ProjectBuildPartReservationFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ProjectBuildPartReservation"

    part = factory.SubFactory(PartFactory)  # type: ignore
    project_build = factory.SubFactory(ProjectBuildFactory)  # type: ignore

    @factory.post_generation  # type: ignore
    def project_parts(self, create, extracted, **kwargs):
        if not create or not extracted:
            return

        self.project_parts.add(*extracted)  # type: ignore


class InventoryActionFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.InventoryAction"

    inventory_line = factory.SubFactory(InventoryLineFactory)  # type: ignore
    # order_line = factory.SubFactory(VendorOrderLineFactory)  # type: ignore
    # reservation = factory.SubFactory(ProjectBuildPartReservationFactory)  # type: ignore

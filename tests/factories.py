import factory
import factory.fuzzy

from django_ctb import models


class FootprintFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.Footprint"

    name = factory.Sequence(lambda x: f"footprint {x}")  # type: ignore


class PackageFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.Package"

    name = factory.Sequence(lambda x: f"package {x}")  # type: ignore


class VendorFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.Vendor"

    base_url = factory.Sequence(lambda x: f"http://vendor{x}.com")  # type: ignore
    name = factory.Sequence(lambda x: f"vendor {x}")  # type: ignore


class PartFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.Part"

    package = factory.Iterator(models.Package.objects.all())  # type: ignore
    name = factory.Sequence(lambda x: f"part {x}")  # type: ignore

    # maybe not yet...
    # equivalent_to = factory.SubFactory(PartFactory)  # type: ignore

    @factory.post_generation  # type: ignore
    def vendors(self, create, extracted, **kwargs):
        if not create or not extracted:
            return

        self.vendors.add(*extracted)  # type: ignore


class VendorPartFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.VendorPart"

    vendor = factory.Iterator(models.Vendor.objects.all())  # type: ignore
    part = factory.Iterator(models.Part.objects.all())  # type: ignore
    item_number = factory.Sequence(lambda x: f"item-{x}")
    cost = factory.Faker(  # type: ignore
        "pydecimal", min_value=0.01, max_value=9999, left_digits=4, right_digits=4
    )
    volume = 42


class OwnerFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.Owner"
        django_get_or_create = ("user",)


class ImplicitProjectPartFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ImplicitProjectPart"

    part = factory.Iterator(models.Part.objects.all())  # type: ignore
    for_package = factory.Iterator(models.Package.objects.all())  # type: ignore


class VendorOrderFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.VendorOrder"

    # vendor = factory.SubFactory(VendorFactory)  # type: ignore
    vendor = factory.Iterator(models.Vendor.objects.all())  # type: ignore


class VendorOrderLineFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.VendorOrderLine"

    vendor_order = factory.Iterator(models.VendorOrder.objects.all())  # type: ignore
    vendor_part = factory.Iterator(models.VendorPart.objects.all())  # type: ignore

    # quantity = factory.fuzzy.FuzzyInteger(1, 1000)
    quantity = factory.Faker("random_int", min=1, max=1000)  # type: ignore
    cost = factory.Faker(  # type: ignore
        "pydecimal", min_value=0.01, max_value=9999, left_digits=4, right_digits=4
    )


class InventoryLineFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.InventoryLine"

    part = factory.Iterator(models.Part.objects.all())  # type: ignore
    owner = factory.Iterator(models.Owner.objects.all())  # type: ignore


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.Project"

    # name = factory.Faker("text", max_nb_chars=20)  # type: ignore
    name = factory.Sequence(lambda x: f"project {x}")  # type: ignore
    git_server = 1
    git_user = factory.Sequence(lambda x: f"user-{x}")  # type: ignore
    git_repo = factory.Sequence(lambda x: f"repo-{x}")  # type: ignore


class ProjectVersionFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ProjectVersion"

    project = factory.Iterator(models.Project.objects.all())  # type: ignore
    revision = factory.Sequence(lambda x: x)  # type: ignore
    commit_ref = factory.Sequence(lambda x: f"branch-{x}")  # type: ignore
    bom_path = factory.Sequence(lambda x: f"bom{x}.csv")  # type: ignore
    pcb_cost = factory.Faker(  # type: ignore
        "pydecimal", min_value=0.01, max_value=9999, left_digits=4, right_digits=2
    )


class ProjectPartFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ProjectPart"

    part = factory.Iterator(models.Part.objects.all())  # type: ignore
    project_version = factory.Iterator(models.ProjectVersion.objects.all())  # type: ignore
    quantity = factory.Faker("random_int", min=1, max=1000)  # type: ignore
    line_number = factory.Sequence(lambda x: x)  # type: ignore


class ProjectPartFootprintRefFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ProjectPartFootprintRef"

    project_part = factory.Iterator(models.ProjectPart.objects.all())  # type: ignore
    footprint_ref = factory.Sequence(lambda x: f"F{x}")


class ProjectBuildFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ProjectBuild"

    project_version = factory.Iterator(models.ProjectVersion.objects.all())  # type: ignore
    quantity = factory.Faker("random_int", min=1, max=10)  # type: ignore

    @factory.post_generation  # type: ignore
    def excluded_project_parts(self, create, extracted, **kwargs):
        if not create or not extracted:
            return

        self.excluded_project_parts.add(*extracted)  # type: ignore


class ProjectBuildPartShortageFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ProjectBuildPartShortage"

    part = factory.Iterator(models.Part.objects.all())  # type: ignore
    project_build = factory.Iterator(models.ProjectBuild.objects.all())  # type: ignore
    quantity = factory.Faker("random_int", min=1, max=10)  # type: ignore


class ProjectBuildPartReservationFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.ProjectBuildPartReservation"

    part = factory.Iterator(models.Part.objects.all())  # type: ignore
    project_build = factory.Iterator(models.ProjectBuild.objects.all())  # type: ignore

    @factory.post_generation  # type: ignore
    def project_parts(self, create, extracted, **kwargs):
        if not create or not extracted:
            return

        self.project_parts.add(*extracted)  # type: ignore


class InventoryActionFactory(factory.django.DjangoModelFactory):
    class Meta:  # type: ignore
        model = "django_ctb.InventoryAction"

    inventory_line = factory.Iterator(models.InventoryLine.objects.all())  # type: ignore
    delta = factory.Faker("random_int", min=-10000, max=-10000)  # type: ignore

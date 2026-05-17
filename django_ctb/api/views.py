"""
API Views for handling CRUD operations on resources
"""

from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django_ctb import models
from django_ctb.api import serializers
from django_ctb.tasks import (
    cancel_build,
    clear_to_build,
    complete_build,
    complete_order,
    generate_vendor_orders,
    populate_mouser_vendor_part,
    sync_project_version,
)


class OwnedSubModelMixin:
    """
    Use for any viewset whose resource is owned indirectly (i.e. the resource
    foreignkeys to a resource which foreignkeys to owner; no limit to the
    number of jumps)

    Subclasses must provide ``owner_ref`` which states the reverse__related
    path (??) to the owner. Must terminate in ``owner``.
    """

    owner_ref: str

    def get_queryset(self):  # noqa: D102
        qs = super().get_queryset()  # type: ignore
        filter_kwargs = {f"{self.owner_ref}__user": self.request.user}  # type: ignore
        qs = qs.filter(**filter_kwargs)
        return qs


class OwnedModelMixin(OwnedSubModelMixin):
    """
    Use for any viewset whose resource is directly owned (i.e. has a foreignkey
    to ``owner``)
    """

    owner_ref = "owner"

    def perform_create(self, serializer):  # noqa: D102
        owner, _ = models.Owner.objects.get_or_create(user=self.request.user)  # type: ignore
        return serializer.save(owner=owner)


@extend_schema(tags=["Parts Library"])
class FootprintViewSet(viewsets.ModelViewSet):
    """
    The manifestation of the part onto the printed circuit board. The
    footprint appears on the bill of materials, parts will be selected based
    in part on the footprint name match.
    """

    queryset = models.Footprint.objects.all()
    serializer_class = serializers.FootprintSerializer
    permission_classes = [IsAuthenticated]


@extend_schema(tags=["Parts Library"])
class PackageViewSet(viewsets.ModelViewSet):
    """
    The form factor for a part. E.g. Surface mount 0805, or TO-92.
    """

    queryset = models.Package.objects.all()
    serializer_class = serializers.PackageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = ("technology",)


@extend_schema(tags=["Parts Library"])
class VendorViewSet(viewsets.ModelViewSet):
    """
    Places where parts can be procured. e.g. Mouser, Tayda Electronics
    """

    queryset = models.Vendor.objects.all()
    serializer_class = serializers.VendorSerializer
    permission_classes = [IsAuthenticated]


@extend_schema(tags=["Parts Library"])
class PartViewSet(viewsets.ModelViewSet):
    """
    Individual parts which are available for procurement from a vendor and
    will be assembled into a project. e.g. a 100 Ohm surface mount (0805)
    resistor, or an NPN TO-92 transistor.

    The ``value`` attribute of the part will be matched to the ``value`` row
    on the bill of materials.
    """

    queryset = models.Part.objects.all()
    serializer_class = serializers.PartSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "name": ["exact", "contains"],
        "value": ["exact", "contains"],
        "unit": ["exact"],
        "symbol": ["exact"],
        "package__name": ["exact", "contains"],
    }


@extend_schema(tags=["Parts Library"])
class VendorPartViewSet(viewsets.ModelViewSet):
    """
    The representation of a part as sold by a vendor. Pricing, item numbers,
    url paths are stored here.
    """

    queryset = models.VendorPart.objects.all()
    serializer_class = serializers.VendorPartSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "vendor": ["exact"],
        "vendor__name": ["exact"],
        "part__name": ["exact", "contains"],
        "part__value": ["exact", "contains"],
        "part__unit": ["exact"],
        "part__symbol": ["exact"],
        "part__package__name": ["exact", "contains"],
    }

    @extend_schema(
        responses={
            200: serializers.GenericActionSerializer,
        }
    )
    @action(
        detail=True,
        methods=["post"],
        serializer_class=serializers.GenericActionSerializer,
        url_path="populate-mouser",
    )
    def populate_mouser(self, request, pk):
        """
        Populate given vendor part with data from Mouser Search API
        """
        populate_mouser_vendor_part.send(int(pk))
        return Response(serializers.GenericActionSerializer().data)


@extend_schema(tags=["Projects"])
class ImplicitProjectPartViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    """
    Certain parts do not appear on the BOM, but must be used for the final
    build. These are represented here. e.g. LED bezel, potentiometer knob
    """

    queryset = models.ImplicitProjectPart.objects.all()
    serializer_class = serializers.ImplicitProjectPartSerializer
    permission_classes = [IsAuthenticated]


@extend_schema(tags=["Procurement"])
class VendorOrderViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    """
    Represents orders of parts from a vendor.
    """

    queryset = models.VendorOrder.objects.all()
    serializer_class = serializers.VendorOrderSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: serializers.GenericActionSerializer,
        }
    )
    @action(
        detail=True,
        methods=["post"],
        serializer_class=serializers.GenericActionSerializer,
    )
    def fulfill(self, request, pk):
        """
        Updates inventory lines for each part in the order, creates inventory
        action with change details. Marks vendor order as fulfilled.

        Ignores any vendor order marked fulfilled.
        """
        complete_order.send(int(pk))
        return Response(serializers.GenericActionSerializer().data)


@extend_schema(tags=["Procurement"])
class VendorOrderLineViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    """
    Represents lines for individual parts in orders.
    """

    queryset = models.VendorOrderLine.objects.all()
    serializer_class = serializers.VendorOrderLineSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "vendor_order__owner"


@extend_schema(tags=["Inventory"])
class InventoryLineViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    """
    Represents the stock of an individual part.
    """

    queryset = models.InventoryLine.objects.all()
    serializer_class = serializers.InventoryLineSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "part": ["exact"],
        "part__name": ["exact", "contains"],
        "part__value": ["exact", "contains"],
        "part__unit": ["exact"],
        "part__symbol": ["exact"],
        "part__package__name": ["exact", "contains"],
    }


@extend_schema(tags=["Inventory"])
class InventoryActionViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    """
    Tracks changes to inventory lines when orders are fulfilled and when
    project build parts are reserved.
    """

    queryset = models.InventoryAction.objects.all()
    serializer_class = serializers.InventoryActionSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "inventory_line__owner"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "order_line__vendor_order": ["exact"],
        "reservation__project_build": ["exact"],
        "inventory_line": ["exact"],
        "inventory_line__part": ["exact"],
    }


@extend_schema(tags=["Projects"])
class ProjectViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    """
    A thing you are building. This is a thin model with just a name and a url
    to a git repo. The repo must have a CSV file which is the Bill Of Materials
    (BOM) for the project. KiCAD generates such BOMs as a default feature.
    """

    queryset = models.Project.objects.all()
    serializer_class = serializers.ProjectSerializer
    permission_classes = [IsAuthenticated]


@extend_schema(tags=["Projects"])
class ProjectVersionViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    """
    A point-in-time representation of the project. Requires a commit ref
    (branch, tag, or commit hash) which exists in the repository, and the
    path within the repo to the bill of materials.
    """

    queryset = models.ProjectVersion.objects.all()
    serializer_class = serializers.ProjectVersionSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "project__owner"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "project": ["exact"],
        "project__name": ["exact", "contains"],
    }

    @extend_schema(
        responses={
            200: serializers.GenericActionSerializer,
        }
    )
    @action(
        detail=True,
        methods=["post"],
        serializer_class=serializers.GenericActionSerializer,
    )
    def sync(self, request, pk):
        """
        Downloads BOM from repository and creates project parts for each row.
        BOM rows which cannot be matched to any part in the system will be
        flagged with a ``missing_part_description``. Parts available through
        supported vendors (Mouser) will be autopopulated provided the PartNum
        is known.

        Rows referencing footprints which are configured with implicit project
        parts will cause additional project parts to be created to represent
        the implicit parts.

        Upon completion of the sync process the commit hash where the BOM was
        found will be saved and the project version will be marked synced.
        """
        sync_project_version.send(int(pk))
        return Response(serializers.GenericActionSerializer().data)


@extend_schema(tags=["Projects"])
class ProjectPartViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    """
    Representation of a BOM line for a project version. Holds references to the
    individual part, the footprint references (where the parts will be placed
    on the PCB), and the BOM line number. Allows for manual assignment of a
    substitute part.
    """

    queryset = models.ProjectPart.objects.all()
    serializer_class = serializers.ProjectPartSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "project_version__project__owner"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "project_version": ["exact"],
        "part": ["exact"],
        "part__name": ["exact", "contains"],
        "part__value": ["exact", "contains"],
        "part__unit": ["exact"],
        "part__symbol": ["exact"],
        "part__package__name": ["exact", "contains"],
    }


@extend_schema(tags=["Projects"])
class ProjectPartFootprintRefViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    """
    The actual, individual footprint ref where a project part will land on the
    PCB (e.g. R12)
    """

    queryset = models.ProjectPartFootprintRef.objects.all()
    serializer_class = serializers.ProjectPartFootprintRefSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "project_part__project_version__project__owner"


@extend_schema(tags=["Builds"])
class ProjectBuildViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    """
    Represents a manufacturing run of a project version. Specify the number of
    instances of the project version that you will build.

    Any ``ProjectPart`` objects which were marked "optional" may be added to
    the ``excluded_project_parts``. When added, these project parts will not
    be omitted from clearing actvities.
    """

    queryset = models.ProjectBuild.objects.all()
    serializer_class = serializers.ProjectBuildSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "project_version__project__owner"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "project_version": ["exact"],
    }

    @extend_schema(
        responses={
            200: serializers.GenericActionSerializer,
        }
    )
    @action(
        detail=True,
        methods=["post"],
        serializer_class=serializers.GenericActionSerializer,
        url_path="clear-to-build",
    )
    def clear_to_build(self, request, pk):
        """
        Reserves sufficient stock of parts to complete a project, or---barring
        availability---reserves stock of parts which are plentiful enough to
        complete the project build and creates shortages for those unfortunate
        parts which have low stocks.
        """
        clear_to_build.send(int(pk))
        return Response(serializers.GenericActionSerializer().data)

    @extend_schema(
        responses={
            200: serializers.GenericActionSerializer,
        }
    )
    @action(
        detail=True,
        methods=["post"],
        serializer_class=serializers.GenericActionSerializer,
    )
    def complete(self, request, pk):
        """
        Marks a project as complete and utilizes reservation. Only operates
        on cleared and incomplete project builds.
        """
        complete_build.send(int(pk))
        return Response(serializers.GenericActionSerializer().data)

    @extend_schema(
        responses={
            200: serializers.GenericActionSerializer,
        }
    )
    @action(
        detail=True,
        methods=["post"],
        serializer_class=serializers.GenericActionSerializer,
    )
    def cancel(self, request, pk):
        """
        Cancels project build and removes any reservations or shortages
        associated with the project. Removes cleared status.
        """
        cancel_build.send(int(pk))
        return Response(serializers.GenericActionSerializer().data)

    @extend_schema(
        responses={
            200: serializers.GenericActionSerializer,
        }
    )
    @action(
        detail=True,
        methods=["post"],
        serializer_class=serializers.GenericActionSerializer,
        url_path="generate-vendor-orders",
    )
    def generate_vendor_orders(self, request, pk):
        """
        Creates or updates vendor orders and order lines to cover shortfalls
        for the given project build. Searches for appropriate vendors for
        each part. Will silently ignore parts that don't have vendors.

        Ignores any project build which is completed.
        """
        generate_vendor_orders.send([int(pk)])
        return Response(serializers.GenericActionSerializer().data)


@extend_schema(tags=["Builds"])
class ProjectBuildPartShortageViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    """
    Represents a part shortage which prevents a project build from being
    cleared.
    """

    queryset = models.ProjectBuildPartShortage.objects.all()
    serializer_class = serializers.ProjectBuildPartShortageSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "project_build__project_version__project__owner"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "project_build": ["exact"],
        "part": ["exact"],
    }


@extend_schema(tags=["Builds"])
class ProjectBuildPartReservationViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    """
    Reservations for parts to cover a project build.
    """

    queryset = models.ProjectBuildPartReservation.objects.all()
    serializer_class = serializers.ProjectBuildPartReservationSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "project_build__project_version__project__owner"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "project_build": ["exact"],
        "part": ["exact"],
    }

# ruff: noqa: D100, D101, D102

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
    owner_ref: str

    def get_queryset(self):
        qs = super().get_queryset()  # type: ignore
        filter_kwargs = {f"{self.owner_ref}__user": self.request.user}  # type: ignore
        qs = qs.filter(**filter_kwargs)
        return qs


class OwnedModelMixin(OwnedSubModelMixin):
    owner_ref = "owner"

    def perform_create(self, serializer):
        owner, _ = models.Owner.objects.get_or_create(user=self.request.user)  # type: ignore
        return serializer.save(owner=owner)


class FootprintViewSet(viewsets.ModelViewSet):
    queryset = models.Footprint.objects.all()
    serializer_class = serializers.FootprintSerializer
    permission_classes = [IsAuthenticated]


class PackageViewSet(viewsets.ModelViewSet):
    queryset = models.Package.objects.all()
    serializer_class = serializers.PackageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = ("technology",)


class VendorViewSet(viewsets.ModelViewSet):
    queryset = models.Vendor.objects.all()
    serializer_class = serializers.VendorSerializer
    permission_classes = [IsAuthenticated]


class PartViewSet(viewsets.ModelViewSet):
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


class VendorPartViewSet(viewsets.ModelViewSet):
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
        populate_mouser_vendor_part.send(int(pk))
        return Response(serializers.GenericActionSerializer().data)


class ImplicitProjectPartViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    queryset = models.ImplicitProjectPart.objects.all()
    serializer_class = serializers.ImplicitProjectPartSerializer
    permission_classes = [IsAuthenticated]


class VendorOrderViewSet(OwnedModelMixin, viewsets.ModelViewSet):
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
        complete_order.send(int(pk))
        return Response(serializers.GenericActionSerializer().data)


class InventoryViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    queryset = models.Inventory.objects.all()
    serializer_class = serializers.InventorySerializer
    permission_classes = [IsAuthenticated]


class VendorOrderLineViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    queryset = models.VendorOrderLine.objects.all()
    serializer_class = serializers.VendorOrderLineSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "vendor_order__owner"


class InventoryLineViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    queryset = models.InventoryLine.objects.all()
    serializer_class = serializers.InventoryLineSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "inventory__owner"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "part": ["exact"],
        "part__name": ["exact", "contains"],
        "part__value": ["exact", "contains"],
        "part__unit": ["exact"],
        "part__symbol": ["exact"],
        "part__package__name": ["exact", "contains"],
    }


class InventoryActionViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    queryset = models.InventoryAction.objects.all()
    serializer_class = serializers.InventoryActionSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "inventory_line__inventory__owner"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "order_line__vendor_order": ["exact"],
        "reservation__project_build": ["exact"],
        "inventory_line": ["exact"],
        "inventory_line__part": ["exact"],
    }


class ProjectViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    queryset = models.Project.objects.all()
    serializer_class = serializers.ProjectSerializer
    permission_classes = [IsAuthenticated]


class ProjectVersionViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
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
        sync_project_version.send(int(pk))
        return Response(serializers.GenericActionSerializer().data)


class ProjectPartViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
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


class ProjectPartFootprintRefViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    queryset = models.ProjectPartFootprintRef.objects.all()
    serializer_class = serializers.ProjectPartFootprintRefSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "project_part__project_version__project__owner"


class ProjectBuildViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
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
        generate_vendor_orders.send([int(pk)])
        return Response(serializers.GenericActionSerializer().data)


class ProjectBuildPartShortageViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    queryset = models.ProjectBuildPartShortage.objects.all()
    serializer_class = serializers.ProjectBuildPartShortageSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "project_build__project_version__project__owner"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "project_build": ["exact"],
        "part": ["exact"],
    }


class ProjectBuildPartReservationViewSet(OwnedSubModelMixin, viewsets.ModelViewSet):
    queryset = models.ProjectBuildPartReservation.objects.all()
    serializer_class = serializers.ProjectBuildPartReservationSerializer
    permission_classes = [IsAuthenticated]
    owner_ref = "project_build__project_version__project__owner"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = {
        "project_build": ["exact"],
        "part": ["exact"],
    }

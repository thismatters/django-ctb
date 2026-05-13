from django.db.models import query
from rest_framework import viewsets

from django_ctb import models
from django_ctb.api import serializers
from rest_framework.permissions import IsAuthenticated


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


class VendorViewSet(viewsets.ModelViewSet):
    queryset = models.Vendor.objects.all()
    serializer_class = serializers.VendorSerializer
    permission_classes = [IsAuthenticated]


class PartViewSet(viewsets.ModelViewSet):
    queryset = models.Part.objects.all()
    serializer_class = serializers.PartSerializer
    permission_classes = [IsAuthenticated]


class VendorPartViewSet(viewsets.ModelViewSet):
    queryset = models.VendorPart.objects.all()
    serializer_class = serializers.VendorPartSerializer
    permission_classes = [IsAuthenticated]


class ImplicitProjectPartViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    queryset = models.ImplicitProjectPart.objects.all()
    serializer_class = serializers.ImplicitProjectPartSerializer
    permission_classes = [IsAuthenticated]


class VendorOrderViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    queryset = models.VendorOrder.objects.all()
    serializer_class = serializers.VendorOrderSerializer
    permission_classes = [IsAuthenticated]


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


class ProjectViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    queryset = models.Project.objects.all()
    serializer_class = serializers.ProjectSerializer
    permission_classes = [IsAuthenticated]

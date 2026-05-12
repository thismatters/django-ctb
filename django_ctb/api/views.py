from django.db.models import query
from rest_framework import viewsets

from django_ctb import models
from django_ctb.api import serializers
from rest_framework.permissions import IsAuthenticated


class OwnedModelMixin:
    def get_queryset(self):
        qs = super().get_queryset()  # type: ignore
        qs = qs.filter(owner__user=self.request.user)  # type: ignore
        return qs

    def perform_create(self, serializer):
        owner, _ = models.Owner.objects.get_or_create(user=self.request.user)  # type: ignore
        return serializer.save(owner=owner)


class VendorOrderViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    queryset = models.VendorOrder.objects.all()
    serializer_class = serializers.VendorOrderSerializer
    permission_classes = [IsAuthenticated]


class InventoryViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    queryset = models.Inventory.objects.all()
    serializer_class = serializers.InventorySerializer
    permission_classes = [IsAuthenticated]


class ProjectViewSet(OwnedModelMixin, viewsets.ModelViewSet):
    queryset = models.Project.objects.all()
    serializer_class = serializers.ProjectSerializer
    permission_classes = [IsAuthenticated]

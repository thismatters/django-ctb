from django.db.models import query
from rest_framework import viewsets

from django_ctb import models
from django_ctb.api import serializers
from rest_framework.permissions import IsAuthenticated


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = models.Project.objects.all()
    serializer_class = serializers.ProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.filter(owner__user=self.request.user)
        return qs

    def perform_create(self, serializer):
        owner, _ = models.Owner.objects.get_or_create(user=self.request.user)
        return serializer.save(owner=owner)

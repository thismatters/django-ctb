# noqa: D101
import logging

import django
from django.db import models as django_models
from django.contrib.auth import get_user_model
from rest_framework import serializers

from django_ctb import models

logger = logging.getLogger(__name__)


class FootprintSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Footprint
        fields = ("id", "name")

    def run_validation(self, data):
        _id = data.pop("id", None)
        validated = super().run_validation(data)
        # if an ID is given, ensure that it matches an existing footprint!
        if _id is not None:
            if not models.Footprint.objects.filter(id=_id).exists():
                raise serializers.ValidationError(f"Unknown footprint with id {_id}")
            validated["id"] = _id
        return validated

    def to_internal_value(self, data):
        # This simplification keeps `id` in `data` (so that we can look up
        #   the instance later)
        return data


class WritableNestedFieldMixin:
    def _get_instances(self, data, *, model_klass, serializer_klass):
        instances = []
        for datum in data:
            # the id for this has already been validated
            _id = datum.pop("id", None)
            _instance = None
            if _id is not None:
                _instance = model_klass.objects.get(id=_id)
            if datum:  # may be empty after that pop
                if _instance:
                    _serializer = serializer_klass(
                        instance=_instance, data=datum, partial=True
                    )
                else:
                    _serializer = serializer_klass(data=datum)
                _serializer.is_valid(raise_exception=True)
                _instance = _serializer.save()
            instances.append(_instance)
        return instances


class PackageSerializer(WritableNestedFieldMixin, serializers.ModelSerializer):
    footprints = FootprintSerializer(many=True)

    class Meta:
        model = models.Package
        fields = ("id", "name", "technology", "footprints")

    def create(self, validated_data):
        footprints = validated_data.pop("footprints", [])
        instance = super().create(validated_data)
        footprint_instances = self._get_instances(
            footprints,
            model_klass=models.Footprint,
            serializer_klass=FootprintSerializer,
        )
        instance.footprints.set(footprint_instances)
        return instance

    def update(self, instance, validated_data):
        footprints = validated_data.pop("footprints", None)
        instance = super().update(instance, validated_data)
        if footprints is not None:
            footprint_instances = self._get_instances(
                footprints,
                model_klass=models.Footprint,
                serializer_klass=FootprintSerializer,
            )
            instance.footprints.set(footprint_instances)
        return instance


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Vendor
        fields = ("id", "name", "base_url")


class SimplePartSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    value = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    unit = serializers.ChoiceField(choices=models.Part.Unit, read_only=True)

    class Meta:
        model = models.Part
        fields = ("id", "name", "description", "value", "unit")


class SimpleVendorPartSerializer(serializers.ModelSerializer):
    part_id = serializers.PrimaryKeyRelatedField(source="part", read_only=True)
    vendor_id = serializers.PrimaryKeyRelatedField(source="vendor", read_only=True)
    vendor_name = serializers.StringRelatedField(source="vendor")
    item_number = serializers.CharField(read_only=True)
    cost = serializers.DecimalField(max_digits=8, decimal_places=4, read_only=True)

    class Meta:
        model = models.Part
        fields = ("id", "part_id", "vendor_id", "vendor_name", "item_number", "cost")


class PartSerializer(serializers.ModelSerializer):
    package_id = serializers.PrimaryKeyRelatedField(
        source="package", queryset=models.Package.objects.all()
    )
    equivalent_to_id = serializers.PrimaryKeyRelatedField(
        source="equivalent_to", queryset=models.Part.objects.all(), allow_null=True
    )
    vendor_parts = SimpleVendorPartSerializer(
        many=True,
        read_only=True,
        help_text="Read only. Manage vendor parts using the dedicated resource endpoint",
    )

    class Meta:
        model = models.Part
        fields = (
            "id",
            "name",
            "description",
            "value",
            "tolerance",
            "loading_limit",
            "unit",
            "symbol",
            "package_id",
            "vendor_parts",
            "equivalent_to_id",
        )


class VendorPartSerializer(serializers.ModelSerializer):
    vendor_id = serializers.PrimaryKeyRelatedField(
        source="vendor", queryset=models.Vendor.objects.all()
    )
    part_id = serializers.PrimaryKeyRelatedField(
        source="part", queryset=models.Part.objects.all()
    )

    class Meta:
        model = models.VendorPart
        fields = (
            "id",
            "vendor_id",
            "part_id",
            "item_number",
            "cost",
            "volume",
            "url_path",
        )


class OwnerSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        source="user", queryset=get_user_model().objects.all()
    )

    class Meta:
        model = models.Owner
        fields = ("id", "user_id")


class ImplicitProjectPartSerializer(serializers.ModelSerializer):
    part_id = serializers.PrimaryKeyRelatedField(
        source="part", queryset=models.Part.objects.all()
    )
    for_package_id = serializers.PrimaryKeyRelatedField(
        source="for_package", queryset=models.Package.objects.all()
    )

    class Meta:
        model = models.ImplicitProjectPart
        fields = ("id", "part_id", "for_package_id", "quantity")


# simple rule: don't make nested serializations for reverse related resources
#   e.g. vendor order lines point _to_ the vendor order, don't attempt
#   to serialize lines on the order.
class VendorOrderSerializer(serializers.ModelSerializer):
    vendor_id = serializers.PrimaryKeyRelatedField(
        source="vendor",
        queryset=models.Vendor.objects.all(),
    )
    # lines = VendorOrderLineSerializer(many=True)

    class Meta:
        model = models.VendorOrder
        fields = (
            "id",
            "vendor_id",
            "order_number",
            "created",
            "placed",
            "fulfilled",
            # "lines",
        )


class InventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Inventory
        fields = ("id", "name")


class VendorOrderLineSerializer(serializers.ModelSerializer):
    vendor_order_id = serializers.PrimaryKeyRelatedField(
        source="vendor_order", queryset=models.VendorOrder.objects.all()
    )
    vendor_part_id = serializers.PrimaryKeyRelatedField(
        source="vendor_part", queryset=models.VendorPart.objects.all()
    )
    for_inventory_id = serializers.PrimaryKeyRelatedField(
        source="for_inventory", queryset=models.Inventory.objects.all()
    )

    class Meta:
        model = models.VendorOrderLine
        fields = (
            "id",
            "vendor_part_id",
            "vendor_order_id",
            "quantity",
            "cost",
            "for_inventory_id",
        )


class InventoryLineSerializer(serializers.ModelSerializer):
    part_id = serializers.PrimaryKeyRelatedField(
        source="part", queryset=models.Part.objects.all()
    )
    inventory_id = serializers.PrimaryKeyRelatedField(
        source="inventory", queryset=models.Inventory.objects.all()
    )

    class Meta:
        model = models.InventoryLine
        fields = (
            "id",
            "part_id",
            "quantity",
            "inventory_id",
            "created",
            "updated",
            "is_deprioritized",
        )


class InventoryActionSerializer(serializers.ModelSerializer):
    inventory_line_id = serializers.PrimaryKeyRelatedField(
        source="inventory_line", queryset=models.InventoryLine.objects.all()
    )
    order_line_id = serializers.PrimaryKeyRelatedField(
        source="order_line",
        queryset=models.VendorOrderLine.objects.all(),
        allow_null=True,
    )
    reservation_id = serializers.PrimaryKeyRelatedField(
        source="reservation",
        queryset=models.ProjectBuildPartReservation.objects.all(),
        allow_null=True,
    )

    class Meta:
        model = models.InventoryAction
        fields = (
            "id",
            "inventory_line_id",
            "order_line_id",
            "reservation_id",
            "delta",
            "created",
        )


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Project
        fields = ("id", "name", "git_server", "git_user", "git_repo")


class ProjectVersionSerializer(serializers.ModelSerializer):
    project_id = serializers.PrimaryKeyRelatedField(
        source="project", queryset=models.Project.objects.all()
    )

    class Meta:
        model = models.ProjectVersion
        fields = (
            "id",
            "project_id",
            "revision",
            "commit_ref",
            "bom_path",
            "pcb_url",
            "pcb_cost",
            "synced",
            "last_synced_commit",
        )


class ProjectPartSerializer(serializers.ModelSerializer):
    project_version_id = serializers.PrimaryKeyRelatedField(
        source="project_version", queryset=models.ProjectVersion.objects.all()
    )
    part_id = serializers.PrimaryKeyRelatedField(
        source="part", queryset=models.Part.objects.all()
    )
    substitute_part_id = serializers.PrimaryKeyRelatedField(
        source="substitute_part", queryset=models.Part.objects.all(), allow_null=True
    )

    class Meta:
        model = models.ProjectPart
        fields = (
            "id",
            "project_version_id",
            "part_id",
            "substitute_part_id",
            "missing_part_description",
            "line_number",
            "quantity",
            "is_implicit",
            "is_optional",
        )


class ProjectPartFootprintRefSerializer(serializers.ModelSerializer):
    project_part_id = serializers.PrimaryKeyRelatedField(
        source="project_part", queryset=models.ProjectPart.objects.all()
    )

    class Meta:
        model = models.ProjectPartFootprintRef
        fields = ("id", "project_part_id", "footprint_ref")


class SimpleProjectPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProjectPart
        fields = ("id",)

    def run_validation(self, data):
        _id = data.pop("id", None)
        validated = super().run_validation(data)
        # if an ID is given, ensure that it matches an existing footprint!
        if _id is not None:
            if not models.ProjectPart.objects.filter(id=_id).exists():
                raise serializers.ValidationError(f"Unknown project part with id {_id}")
            validated["id"] = _id
        return validated

    def to_internal_value(self, data):
        # This simplification keeps `id` in `data` (so that we can look up
        #   the instance later)
        return data


class ProjectBuildSerializer(WritableNestedFieldMixin, serializers.ModelSerializer):
    project_version_id = serializers.PrimaryKeyRelatedField(
        source="project_version", queryset=models.ProjectVersion.objects.all()
    )
    excluded_project_parts = SimpleProjectPartSerializer(many=True)

    class Meta:
        model = models.ProjectBuild
        fields = (
            "id",
            "project_version_id",
            "quantity",
            "created",
            "cleared",
            "completed",
            "excluded_project_parts",
        )

    def create(self, validated_data):
        excluded_project_parts = validated_data.pop("excluded_project_parts", [])
        instance = super().create(validated_data)
        project_parts = self._get_instances(
            excluded_project_parts,
            model_klass=models.ProjectPart,
            serializer_klass=SimpleProjectPartSerializer,
        )
        instance.excluded_project_parts.set(project_parts)
        return instance

    def update(self, instance, validated_data):
        excluded_project_parts = validated_data.pop("excluded_project_parts", None)
        instance = super().update(instance, validated_data)
        if excluded_project_parts is not None:
            project_parts = self._get_instances(
                excluded_project_parts,
                model_klass=models.ProjectPart,
                serializer_klass=SimpleProjectPartSerializer,
            )
            instance.excluded_project_parts.set(project_parts)
        return instance


class ProjectBuildPartShortageSerializer(serializers.ModelSerializer):
    part_id = serializers.PrimaryKeyRelatedField(
        source="part", queryset=models.Part.objects.all()
    )
    project_build_id = serializers.PrimaryKeyRelatedField(
        source="project_build", queryset=models.ProjectBuild.objects.all()
    )
    fallback_part_id = serializers.PrimaryKeyRelatedField(
        source="fallback_part", queryset=models.Part.objects.all(), allow_null=True
    )

    class Meta:
        model = models.ProjectBuildPartShortage
        fields = (
            "id",
            "part_id",
            "quantity",
            "project_build_id",
            "fallback_part_id",
            "created",
        )


class ProjectBuildPartReservationSerializer(
    WritableNestedFieldMixin, serializers.ModelSerializer
):
    project_build_id = serializers.PrimaryKeyRelatedField(
        source="project_build", queryset=models.ProjectBuild.objects.all()
    )
    part_id = serializers.PrimaryKeyRelatedField(
        source="part", queryset=models.Part.objects.all()
    )
    project_parts = SimpleProjectPartSerializer(many=True)

    class Meta:
        model = models.ProjectBuildPartReservation
        fields = (
            "id",
            "project_build_id",
            "part_id",
            "project_parts",
            "created",
            "utilized",
            "order_key",
        )

    def create(self, validated_data):
        _project_parts = validated_data.pop("project_parts", [])
        instance = super().create(validated_data)
        project_parts = self._get_instances(
            _project_parts,
            model_klass=models.ProjectPart,
            serializer_klass=SimpleProjectPartSerializer,
        )
        instance.project_parts.set(project_parts)
        return instance

    def update(self, instance, validated_data):
        _project_parts = validated_data.pop("project_parts", None)
        instance = super().update(instance, validated_data)
        if _project_parts is not None:
            project_parts = self._get_instances(
                _project_parts,
                model_klass=models.ProjectPart,
                serializer_klass=SimpleProjectPartSerializer,
            )
            instance.project_parts.set(project_parts)
        return instance

# noqa: D101
import logging

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


class PackageSerializer(serializers.ModelSerializer):
    footprints = FootprintSerializer(many=True)

    class Meta:
        model = models.Package
        fields = ("id", "name", "technology", "footprints")

    def _get_footprint_instances(self, footprints):
        footprint_instances = []
        for footprint in footprints:
            # the id for this has already been validated
            footprint_id = footprint.pop("id", None)
            footprint_instance = None
            if footprint_id is not None:
                footprint_instance = models.Footprint.objects.get(id=footprint_id)
            if footprint:  # may be empty after that pop
                if footprint_instance:
                    _serializer = FootprintSerializer(
                        instance=footprint_instance, data=footprint, partial=True
                    )
                else:
                    _serializer = FootprintSerializer(data=footprint)
                _serializer.is_valid(raise_exception=True)
                footprint_instance = _serializer.save()
            footprint_instances.append(footprint_instance)
        return footprint_instances

    def create(self, validated_data):
        footprints = validated_data.pop("footprints", [])
        instance = super().create(validated_data)
        footprint_instances = self._get_footprint_instances(footprints=footprints)
        instance.footprints.set(footprint_instances)
        return instance

    def update(self, instance, validated_data):
        footprints = validated_data.pop("footprints", [])
        instance = super().update(instance, validated_data)
        footprint_instances = self._get_footprint_instances(footprints=footprints)
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
        source="vendor",
        queryset=models.Vendor.objects.all(),
    )
    part_id = serializers.PrimaryKeyRelatedField(
        source="part",
        queryset=models.Part.objects.all(),
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
        source="part",
        queryset=models.Part.objects.all(),
    )
    for_package_id = serializers.PrimaryKeyRelatedField(
        source="for_package",
        queryset=models.Package.objects.all(),
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
    class Meta:
        model = models.InventoryAction
        fields = "__all__"


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Project
        fields = ("id", "name", "git_server", "git_user", "git_repo")


class ProjectVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProjectVersion
        fields = "__all__"


class ProjectPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProjectPart
        fields = "__all__"


class ProjectPartFootprintRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProjectPartFootprintRef
        fields = "__all__"


class ProjectBuildSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProjectBuild
        fields = "__all__"


class ProjectBuildPartShortageSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProjectBuildPartShortage
        fields = "__all__"


class ProjectBuildPartReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProjectBuildPartReservation
        fields = "__all__"

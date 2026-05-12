# noqa: D101
import logging
from enum import Enum

from django.contrib.auth import get_user_model
from rest_framework import serializers

from django_ctb import models

logger = logging.getLogger(__name__)


class FootprintSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Footprint
        fields = "__all__"


class PackageSerializer(serializers.ModelSerializer):
    footprints = FootprintSerializer(many=True)

    class Meta:
        model = models.Package
        fields = ("id", "name", "technology", "footprints")


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Vendor
        fields = "__all__"


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
    package = PackageSerializer()
    equivalent_to = SimplePartSerializer()
    vendor_parts = SimpleVendorPartSerializer(many=True)

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
            "package",
            "vendor_parts",
            "equivalent_to",
        )


# TODO: decide whether this is necessary. I don't think there is a reason
# to be messing with these via API just yet. Maybe someday, but for now this
# can be handled via admin/shell
# class VendorPartSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.VendorPart
#         fields = "__all__"


class OwnerSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        source="user", queryset=get_user_model().objects.all()
    )

    class Meta:
        model = models.Owner
        fields = ("id", "user_id")


class ImplicitProjectPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ImplicitProjectPart
        fields = "__all__"


class VendorOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.VendorOrder
        fields = "__all__"


class InventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Inventory
        fields = "__all__"


class VendorOrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.VendorOrderLine
        fields = "__all__"


class InventoryLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.InventoryLine
        fields = "__all__"


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

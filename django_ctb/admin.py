from django.contrib import admin
from django.shortcuts import render
from functools import update_wrapper
from django.utils.encoding import force_str
from django.http import Http404
from django.contrib.admin.utils import unquote
from django.urls import path, reverse

from django_ctb.tasks import (
    sync_project_version,
    clear_to_build,
    complete_build,
    cancel_build,
    complete_order,
    populate_mouser_vendor_part,
)

from django_ctb import models


@admin.register(models.Footprint)
class FootprintAdmin(admin.ModelAdmin):
    list_display = ("name",)


class ImplicitProjectPartInline(admin.TabularInline):
    # fields = ("item_number", "cost", "volume", "url_path")
    model = models.ImplicitProjectPart


@admin.register(models.Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ("name", "technology")
    list_filter = ("technology",)
    inlines = (ImplicitProjectPartInline,)


@admin.register(models.Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name",)


class VendorOrderLineInline(admin.TabularInline):
    model = models.VendorOrderLine


@admin.register(models.VendorOrder)
class VendorOrderAdmin(admin.ModelAdmin):
    list_display = ("vendor", "order_number", "created", "fulfilled")
    inlines = (VendorOrderLineInline,)
    actions = ("_complete_order",)

    def _complete_order(self, request, queryset):
        for row in queryset:
            complete_order.send(row.pk)
        self.message_user(request, f"{len(queryset)} processes started")

    _complete_order.short_description = "Mark order fulfilled"


class VendorPartInline(admin.TabularInline):
    # fields = ("item_number", "cost", "volume", "url_path")
    model = models.VendorPart
    extra = 1


class InventoryLineInline(admin.TabularInline):
    # fields = ("item_number", "cost", "volume", "url_path")
    model = models.InventoryLine
    extra = 1


@admin.register(models.Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ("description", "symbol", "value", "package")
    list_filter = ("symbol", "name", "package", "value")
    inlines = [VendorPartInline, InventoryLineInline]


@admin.register(models.VendorPart)
class VendorPartAdmin(admin.ModelAdmin):
    list_display = ("item_number", "vendor", "part")
    list_filter = ("vendor",)
    actions = ("_populate",)

    def _populate(self, request, queryset):
        for row in queryset:
            populate_mouser_vendor_part.send(row.pk)
        self.message_user(request, f"{len(queryset)} processes started")

    _populate.short_description = "Populate fields (Mouser)"


@admin.register(models.ImplicitProjectPart)
class ImplicityProjectPartAdmin(admin.ModelAdmin):
    list_display = ("part", "for_package", "quantity")


@admin.register(models.Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("name",)


class InventoryActionInline(admin.TabularInline):
    fields = ("delta", "order_line", "build", "created")
    model = models.InventoryAction

    extra = 0


@admin.register(models.InventoryLine)
class InventoryLineAdmin(admin.ModelAdmin):
    list_display = ("part", "quantity", "inventory")
    list_filter = ("inventory", "part__symbol", "part__package__name", "part__value")
    inlines = [InventoryActionInline]


class ProjectVersionInline(admin.TabularInline):
    model = models.ProjectVersion

    extra = 1


@admin.register(models.Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "git_url")
    inlines = (ProjectVersionInline,)


class ProjectBuildInline(admin.TabularInline):
    fields = ("quantity", "created")
    model = models.ProjectBuild


class MissingPartInline(admin.TabularInline):
    fields = ("part", "missing_part_description")
    model = models.ProjectPart
    extra = 0

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(part__isnull=True)


@admin.register(models.ProjectVersion)
class ProjectVersionAdmin(admin.ModelAdmin):
    list_display = ("project", "revision", "commit_ref", "synced", "missing_part_count")
    list_filter = ("project",)
    inlines = [MissingPartInline, ProjectBuildInline]
    actions = ("sync_bom",)

    def sync_bom(self, request, queryset):
        for row in queryset:
            sync_project_version.send(row.pk)
        self.message_user(request, f"{len(queryset)} processes started")

    sync_bom.short_description = "Sync selected version BOMs"

    def missing_part_count(self, obj):
        return obj.project_parts.filter(part__isnull=True).count()

    def _getobj(self, request, object_id):
        opts = self.model._meta

        try:
            obj = self.get_queryset(request).get(pk=unquote(object_id))
        except self.model.DoesNotExist:
            # Don't raise Http404 just yet, because we haven't checked
            # permissions yet. We don't want an unauthenticated user to
            # be able to determine whether a given object exists.
            obj = None

        if obj is None:
            raise Http404(
                f"{force_str(opts.verbose_name)} object with primary key "
                f"'{force_str(object_id)}' does not exist."
            )

        return obj

    def _wrap(self, view):
        def wrapper(*args, **kwargs):
            return self.admin_site.admin_view(view)(*args, **kwargs)

        return update_wrapper(wrapper, view)

    def _view_name(self, name):
        return f"{self.model._meta.app_label}_{self.model._meta.model_name}_{name}"

    def get_urls(self):
        urls = super().get_urls()

        my_urls = [
            path(
                "<object_id>/bom/",
                self._wrap(self.bom_view),
                name=self._view_name("bom"),
            ),
        ]

        return my_urls + urls

    def bom_view(self, request, object_id):
        return render(
            request,
            "admin/inventory/project_version_bom.html",
            {"project_version": self._getobj(request, object_id)},
        )


class ProjectPartFootprintRefInline(admin.TabularInline):
    fields = ("footprint_ref",)
    model = models.ProjectPartFootprintRef


@admin.register(models.ProjectPart)
class ProjectPartAdmin(admin.ModelAdmin):
    list_display = ("project_version", "line_number", "part", "quantity")
    list_filter = ("project_version", "part")
    inlines = [ProjectPartFootprintRefInline]


class ProjectBuildPartShortageInline(admin.TabularInline):
    fields = ("part", "quantity")
    model = models.ProjectBuildPartShortage
    extra = 0


@admin.register(models.ProjectBuild)
class ProjectBuildAdmin(admin.ModelAdmin):
    list_display = (
        "project_version",
        "created",
        "quantity",
        "shortfalls",
        "cleared",
        "completed",
    )
    list_filter = ("project_version",)
    date_hierarchy = "created"
    inlines = [ProjectBuildPartShortageInline]
    actions = ("_clear_to_build", "_complete_build", "_cancel_build")

    def _clear_to_build(self, request, queryset):
        for row in queryset:
            clear_to_build.send(row.pk)
        self.message_user(request, f"{len(queryset)} processes started")

    _clear_to_build.short_description = "Clear to build"

    def _complete_build(self, request, queryset):
        for row in queryset:
            complete_build.send(row.pk)
        self.message_user(request, f"{len(queryset)} processes started")

    _complete_build.short_description = "Complete build"

    def _cancel_build(self, request, queryset):
        for row in queryset:
            cancel_build.send(row.pk)
        self.message_user(request, f"{len(queryset)} processes started")

    _cancel_build.short_description = "Cancel build"

    def shortfalls(self, obj):
        return obj.shortfalls.count()

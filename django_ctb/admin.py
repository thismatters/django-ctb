from functools import update_wrapper

from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.http import Http404
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.encoding import force_str
from django.utils.html import format_html

from django_ctb import models
from django_ctb.tasks import (
    cancel_build,
    clear_to_build,
    complete_build,
    complete_order,
    generate_vendor_orders,
    populate_mouser_vendor_part,
    sync_project_version,
)


class ExtendibleModelAdminMixin:
    def _getobj(self, request, object_id):
        opts = self.model._meta  # type: ignore[unresolve-attribute]

        try:
            obj = self.get_queryset(  # type: ignore[unresolve-attribute]
                request,
            ).get(pk=unquote(object_id))
        except self.model.DoesNotExist:  # type: ignore[unresolve-attribute]
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
            return self.admin_site.admin_view(view)(  # type: ignore[unresolve-attribute]
                *args,
                **kwargs,
            )

        return update_wrapper(wrapper, view)

    def _view_name(self, name):
        return (
            f"{self.model._meta.app_label}_"  # type: ignore[unresolve-attribute]
            f"{self.model._meta.model_name}_{name}"  # type: ignore[unresolve-attribute]
        )


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
    list_display = ("vendor", "order_number", "created", "placed", "fulfilled")
    inlines = (VendorOrderLineInline,)
    actions = ("_complete_order",)

    def _complete_order(self, request, queryset):
        for row in queryset:
            complete_order.send(row.pk)
        self.message_user(request, f"{len(queryset)} processes started")

    _complete_order.short_description = "Mark order fulfilled"  # type: ignore[unresolve-attribute]


class VendorPartInline(admin.TabularInline):
    # fields = ("item_number", "cost", "volume", "url_path")
    model = models.VendorPart
    extra = 1


class InventoryLineInline(admin.TabularInline):
    fields = (
        "inventory",
        "quantity",
        "is_deprioritized",
        "link",
    )
    readonly_fields = ("link",)
    model = models.InventoryLine
    extra = 1

    def link(self, obj):  # pragma: no cover
        if obj is not None:
            return format_html(
                '<a href="{}">Details</a>',
                reverse(
                    "admin:django_ctb_inventoryline_change",
                    kwargs={"object_id": obj.pk},
                ),
            )
        return ""


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

    _populate.short_description = "Populate fields (Mouser)"  # type: ignore[unresolve-attribute]


@admin.register(models.ImplicitProjectPart)
class ImplicityProjectPartAdmin(admin.ModelAdmin):
    list_display = ("part", "for_package", "quantity")


@admin.register(models.Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("name",)


class InventoryActionInline(admin.TabularInline):
    fields = ("delta", "order_line", "reservation", "created")
    model = models.InventoryAction

    extra = 0


@admin.register(models.InventoryLine)
class InventoryLineAdmin(admin.ModelAdmin):
    list_display = ("part", "quantity", "inventory", "item_numbers")
    list_filter = (
        "inventory",
        "part__symbol",
        "part__package__name",
        "part__value",
    )
    inlines = [InventoryActionInline]


class ProjectVersionInline(admin.TabularInline):
    model = models.ProjectVersion
    fields = ("revision", "commit_ref", "bom_path", "pcb_url")

    extra = 1


@admin.register(models.Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "git_repo")
    inlines = (ProjectVersionInline,)


class ProjectBuildInline(admin.TabularInline):
    fields = ("quantity", "created")
    model = models.ProjectBuild


class MissingPartInline(admin.TabularInline):
    fields = ("part", "is_optional", "missing_part_description")
    model = models.ProjectPart
    extra = 0

    def get_queryset(self, request):  # pragma: no cover
        qs = super().get_queryset(request)
        return qs.filter(part__isnull=True)


@admin.register(models.ProjectVersion)
class ProjectVersionAdmin(ExtendibleModelAdminMixin, admin.ModelAdmin):
    list_display = ("project", "revision", "commit_ref", "synced", "missing_part_count")
    list_filter = ("project",)
    inlines = [MissingPartInline, ProjectBuildInline]
    actions = ("sync_bom",)
    readonly_fields = ("last_synced_commit",)

    def sync_bom(self, request, queryset):
        for row in queryset:
            sync_project_version.send(row.pk)
        self.message_user(request, f"{len(queryset)} processes started")

    sync_bom.short_description = "Sync selected version BOMs"  # type: ignore[unresolve-attribute]

    def missing_part_count(self, obj):  # pragma: no cover
        return obj.project_parts.filter(part__isnull=True).count()

    def get_urls(self):  # pragma: no cover
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
            "admin/django_ctb/project_version_bom.html",
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


class ProjectBuildPartReservationInline(admin.TabularInline):
    fields = ("inventory_action", "part", "utilized")
    model = models.ProjectBuildPartReservation
    extra = 0


@admin.register(models.ProjectBuild)
class ProjectBuildAdmin(ExtendibleModelAdminMixin, admin.ModelAdmin):
    list_display = (
        "project_version",
        "quantity",
        "shortfalls",
        "bom",
        "cleared",
        "completed",
        "created",
    )
    list_filter = ("project_version",)
    date_hierarchy = "created"
    inlines = [
        ProjectBuildPartShortageInline,
        ProjectBuildPartReservationInline,
    ]
    actions = (
        "_generate_vendor_orders",
        "_clear_to_build",
        "_complete_build",
        "_cancel_build",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related(
                "shortfalls__part",
                "part_reservations__inventory_actions",
                "part_reservations__inventory_actions__order_line__vendor",
                "part_reservations__part__package",
            )
        )

    def bom(self, obj):  # pragma: no cover
        return format_html(
            '<a href="{}">bom</a>',
            reverse(f"admin:{self._view_name('bom')}", kwargs={"object_id": obj.pk}),
        )

    def get_form(
        self, request, obj, change, **kwargs
    ):  # pragma: no cover  # type: ignore[invalid-method-override]
        self.obj = obj
        return super().get_form(request, obj, change, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):  # pragma: no cover
        if db_field.name == "excluded_project_parts" and self.obj is not None:
            kwargs["queryset"] = models.ProjectPart.objects.filter(
                project_version=self.obj.project_version,
                is_optional=True,
            )
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def _clear_to_build(self, request, queryset):
        for row in queryset:
            clear_to_build.send(row.pk)
        self.message_user(request, f"{len(queryset)} processes started")

    _clear_to_build.short_description = "Clear to build"  # type: ignore[unresolve-attribute]

    def _complete_build(self, request, queryset):
        for row in queryset:
            complete_build.send(row.pk)
        self.message_user(request, f"{len(queryset)} processes started")

    _complete_build.short_description = "Complete build"  # type: ignore[unresolve-attribute]

    def _cancel_build(self, request, queryset):
        for row in queryset:
            cancel_build.send(row.pk)
        self.message_user(request, f"{len(queryset)} processes started")

    _cancel_build.short_description = "Cancel build"  # type: ignore[unresolve-attribute]

    def shortfalls(self, obj):  # pragma: no cover
        return obj.shortfalls.count()

    def _generate_vendor_orders(self, request, queryset):
        generate_vendor_orders.send(list(queryset.values_list("pk", flat=True)))
        self.message_user(request, f"{len(queryset)} processes started")

    _generate_vendor_orders.short_description = "Generate orders from shortfalls"  # type: ignore[unresolve-attribute]

    def get_urls(self):  # pragma: no cover
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
            "admin/django_ctb/project_build_bom.html",
            {"project_build": self._getobj(request, object_id)},
        )

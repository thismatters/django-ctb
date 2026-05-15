# ruff: noqa: D100
from rest_framework import routers

from django_ctb.api import views

router = routers.DefaultRouter()

router.register("footprints", views.FootprintViewSet, basename="footprint")
router.register("packages", views.PackageViewSet, basename="package")
router.register("vendors", views.VendorViewSet, basename="vendor")
router.register("parts", views.PartViewSet, basename="part")
router.register("vendor-parts", views.VendorPartViewSet, basename="vendor-part")
router.register(
    "implicit-project-parts",
    views.ImplicitProjectPartViewSet,
    basename="implicit-project-part",
)
router.register("vendor-orders", views.VendorOrderViewSet, basename="vendor-order")
router.register("inventories", views.InventoryViewSet, basename="inventory")
router.register(
    "vendor-order-lines", views.VendorOrderLineViewSet, basename="vendor-order-line"
)
router.register(
    "inventory-lines", views.InventoryLineViewSet, basename="inventory-line"
)
router.register(
    "inventory-actions", views.InventoryActionViewSet, basename="inventory-action"
)

router.register("projects", views.ProjectViewSet, basename="project")
router.register(
    "project-versions", views.ProjectVersionViewSet, basename="project-version"
)
router.register("project-parts", views.ProjectPartViewSet, basename="project-part")
router.register(
    "project-part-footprint-refs",
    views.ProjectPartFootprintRefViewSet,
    basename="project-part-footprint-ref",
)
router.register("project-builds", views.ProjectBuildViewSet, basename="project-build")
router.register(
    "project-build-part-shortages",
    views.ProjectBuildPartShortageViewSet,
    basename="project-build-part-shortage",
)
router.register(
    "project-build-part-reservations",
    views.ProjectBuildPartReservationViewSet,
    basename="project-build-part-reservation",
)

app_name = "django-ctb-api"

urlpatterns = []
urlpatterns += router.urls

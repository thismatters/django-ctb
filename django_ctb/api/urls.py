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
router.register("projects", views.ProjectViewSet, basename="project")

app_name = "django-ctb-api"

urlpatterns = []
urlpatterns += router.urls

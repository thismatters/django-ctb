from rest_framework import routers

from django_ctb.api import views

router = routers.DefaultRouter()

router.register("projects", views.ProjectViewSet, basename="project")

app_name = "django-ctb-api"

urlpatterns = []
urlpatterns += router.urls

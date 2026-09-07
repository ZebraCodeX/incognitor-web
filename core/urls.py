from django.urls import path, include
from django.contrib.auth import views as auth_views
from rest_framework.routers import DefaultRouter
from . import views
from .api import (
    AuthViewSet,
    BrokerViewSet,
    ScanViewSet,
    DataStopViewSet,
    ProfileViewSet,
    ActivityViewSet,
)

router = DefaultRouter()
router.register(r"auth", AuthViewSet, basename="auth")
router.register(r"brokers", BrokerViewSet, basename="brokers")
router.register(r"scans", ScanViewSet, basename="scans")
router.register(r"data-stops", DataStopViewSet, basename="data-stops")
router.register(r"profile", ProfileViewSet, basename="profile")
router.register(r"activities", ActivityViewSet, basename="activities")

urlpatterns = [
    path("api/", include(router.urls)),
    path("", views.index, name="index"),
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(template_name="core/auth/login.html"), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("scan/new/", views.new_scan, name="new_scan"),
    path("scan/<uuid:scan_id>/", views.scan_detail, name="scan_detail"),
    path("scan/<uuid:scan_id>/start/", views.start_scan, name="start_scan"),
    path("scan/<uuid:scan_id>/status/", views.scan_status_api, name="scan_status_api"),
    path("data-stops/", views.data_stops, name="data_stops"),
    path("brokers/", views.brokers_list, name="brokers"),
    path("profile/", views.profile_view, name="profile"),
]

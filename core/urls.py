from django.contrib.auth import views as auth_views
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import admin_views, views
from .api import (
    ActivityViewSet,
    AdminBrokerViewSet,
    AdminCampaignViewSet,
    AdminExposureViewSet,
    AdminOverviewView,
    AdminUserViewSet,
    AgentJobViewSet,
    AgentViewSet,
    AuditEventViewSet,
    AuthViewSet,
    BrokerViewSet,
    ConsentViewSet,
    DataStopViewSet,
    ExposureViewSet,
    HouseholdMemberViewSet,
    HouseholdViewSet,
    IdentityViewSet,
    NotificationChannelConfigViewSet,
    NotificationViewSet,
    ProfileViewSet,
    PushViewSet,
    RemovalCampaignViewSet,
    ScanViewSet,
    WatchlistViewSet,
)

router = DefaultRouter()
router.register(r"auth", AuthViewSet, basename="auth")
router.register(r"brokers", BrokerViewSet, basename="brokers")
router.register(r"scans", ScanViewSet, basename="scans")
router.register(r"data-stops", DataStopViewSet, basename="data-stops")
router.register(r"profile", ProfileViewSet, basename="profile")
router.register(r"activities", ActivityViewSet, basename="activities")

# Sentinel
router.register(r"identities", IdentityViewSet, basename="identities")
router.register(r"watchlists", WatchlistViewSet, basename="watchlists")
router.register(r"exposures", ExposureViewSet, basename="exposures")
router.register(r"removal-campaigns", RemovalCampaignViewSet, basename="removal-campaigns")
router.register(r"notifications", NotificationViewSet, basename="notifications")
router.register(r"notification-channels", NotificationChannelConfigViewSet, basename="notification-channels")
router.register(r"push", PushViewSet, basename="push")
router.register(r"consents", ConsentViewSet, basename="consents")
router.register(r"agent/jobs", AgentJobViewSet, basename="agent-jobs")
router.register(r"agent", AgentViewSet, basename="agent")
router.register(r"audit-events", AuditEventViewSet, basename="audit-events")

# Households (family plans)
router.register(r"households", HouseholdViewSet, basename="households")
router.register(r"household-members", HouseholdMemberViewSet, basename="household-members")

# Admin / operator oversight (staff only)
router.register(r"admin/users", AdminUserViewSet, basename="admin-users")
router.register(r"admin/exposures", AdminExposureViewSet, basename="admin-exposures")
router.register(r"admin/campaigns", AdminCampaignViewSet, basename="admin-campaigns")
router.register(r"admin/brokers", AdminBrokerViewSet, basename="admin-brokers")

urlpatterns = [
    path("api/admin/overview/", AdminOverviewView.as_view(), name="admin-overview"),
    path("api/auth/token/", obtain_auth_token, name="api-token"),
    path("api/", include(router.urls)),
    path("sw.js", views.service_worker, name="service_worker"),
    path("verify-email/", views.verify_email_page, name="verify_email_page"),
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
    path("exposures/", views.exposures_list, name="exposures"),
    # Staff operator console
    path("console/", admin_views.console_overview, name="console_overview"),
    path("console/users/", admin_views.console_users, name="console_users"),
    path("console/users/<int:user_id>/action/", admin_views.console_user_action, name="console_user_action"),
    path("console/exposures/", admin_views.console_exposures, name="console_exposures"),
    path("console/campaigns/", admin_views.console_campaigns, name="console_campaigns"),
    path("console/brokers/", admin_views.console_brokers, name="console_brokers"),
    path("console/brokers/<uuid:broker_id>/action/", admin_views.console_broker_action, name="console_broker_action"),
    path("console/brokers/rescore/", admin_views.console_rescore_all, name="console_rescore_all"),
]

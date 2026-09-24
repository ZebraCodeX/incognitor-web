from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from core.entitlements import get_entitlements
from core.models import HouseholdMember, UserProfile
from core.throttling import BurstUserThrottle


class EntitlementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("free", "free@e.com", "pw123456!!")
        UserProfile.objects.create(user=self.user, plan=UserProfile.Plan.FREE)
        self.staff = User.objects.create_user("boss", "boss@e.com", "pw123456!!", is_staff=True)
        UserProfile.objects.create(user=self.staff)

    def test_staff_get_unlimited_entitlements(self):
        ent = get_entitlements(self.staff)
        self.assertTrue(ent.is_staff)
        self.assertTrue(ent.unlimited)
        self.assertEqual(ent.max_identities, -1)
        self.assertEqual(ent.max_sends_per_day, -1)

    def test_free_plan_is_limited(self):
        ent = get_entitlements(self.user)
        self.assertFalse(ent.auto_remove)
        self.assertEqual(ent.max_identities, 1)

    def test_staff_bypass_rate_limit(self):
        class FakeRequest:
            class _U:
                is_authenticated = True
                is_staff = True
                is_superuser = False

            user = _U()

        throttle = BurstUserThrottle()
        self.assertTrue(throttle.allow_request(FakeRequest(), None))

    def test_normal_user_subject_to_throttle(self):
        class FakeRequest:
            class _U:
                is_authenticated = True
                is_staff = False
                is_superuser = False
                pk = 42

            user = _U()

        cache.clear()
        throttle = BurstUserThrottle()
        throttle.num_requests = 2
        throttle.duration = 3600
        self.assertTrue(throttle.allow_request(FakeRequest(), None))
        self.assertTrue(throttle.allow_request(FakeRequest(), None))
        self.assertFalse(throttle.allow_request(FakeRequest(), None))
        cache.clear()


class IdentityLimitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("limited", "l@e.com", "pw123456!!")
        UserProfile.objects.create(user=self.user, plan=UserProfile.Plan.FREE)
        self.staff = User.objects.create_user("admin2", "a2@e.com", "pw123456!!", is_staff=True, is_superuser=True)
        UserProfile.objects.create(user=self.staff)

    def _create(self, user, label):
        self.client.force_login(user)
        return self.client.post(
            "/api/identities/",
            {"label": label, "identifiers": [{"kind": "email", "value": f"{label}@e.com"}]},
            content_type="application/json",
        )

    def test_free_plan_identity_limit(self):
        self.assertEqual(self._create(self.user, "one").status_code, 201)
        self.assertEqual(self._create(self.user, "two").status_code, 403)

    def test_staff_have_no_identity_limit(self):
        for i in range(3):
            self.assertEqual(self._create(self.staff, f"id{i}").status_code, 201)


class AdminApiTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("admin3", "ad3@e.com", "pw123456!!", is_staff=True)
        UserProfile.objects.create(user=self.staff)
        self.user = User.objects.create_user("normal", "n@e.com", "pw123456!!")
        UserProfile.objects.create(user=self.user)

    def test_overview_requires_staff(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/api/admin/overview/").status_code, 403)
        self.client.force_login(self.staff)
        resp = self.client.get("/api/admin/overview/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("users", resp.json())

    def test_admin_can_change_plan_and_staff(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            f"/api/admin/users/{self.user.id}/set_plan/",
            {"plan": "family"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.plan, "family")

        resp = self.client.post(
            f"/api/admin/users/{self.user.id}/set_staff/",
            {"is_staff": True},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)


class TokenAuthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tokenuser", "t@e.com", "pw123456!!")
        UserProfile.objects.create(user=self.user)

    def test_obtain_token_and_use_it(self):
        resp = self.client.post(
            "/api/auth/token/",
            {"username": "tokenuser", "password": "pw123456!!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        token = resp.json()["token"]
        self.assertTrue(token)
        resp = self.client.get("/api/exposures/", HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(resp.status_code, 200)


class ConsoleTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("op", "op@e.com", "pw123456!!", is_staff=True)
        UserProfile.objects.create(user=self.staff)
        self.user = User.objects.create_user("plain", "plain@e.com", "pw123456!!")
        UserProfile.objects.create(user=self.user)
        from core.models import Broker

        self.broker = Broker.objects.create(
            name="Acme", slug="acme", website_url="https://acme.com", removal_method="email"
        )

    def test_console_requires_staff(self):
        self.client.force_login(self.user)
        resp = self.client.get("/console/")
        self.assertIn(resp.status_code, (302, 403))

    def test_staff_can_view_console_pages(self):
        self.client.force_login(self.staff)
        for path in ["/console/", "/console/users/", "/console/exposures/",
                     "/console/campaigns/", "/console/brokers/"]:
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_console_set_plan_action(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            f"/console/users/{self.user.id}/action/",
            {"action": "set_plan", "plan": "pro"},
        )
        self.assertEqual(resp.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.plan, "pro")

    def test_console_broker_toggle(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            f"/console/brokers/{self.broker.id}/action/",
            {"action": "toggle_active"},
        )
        self.assertEqual(resp.status_code, 302)
        self.broker.refresh_from_db()
        self.assertFalse(self.broker.is_active)


class HouseholdTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("parent", "p@e.com", "pw123456!!")
        UserProfile.objects.create(user=self.owner, plan=UserProfile.Plan.FAMILY)

    def test_household_create_and_dependent(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            "/api/households/", {"name": "Home"}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 201)
        hid = resp.json()["id"]
        # Owner membership auto-created.
        self.assertTrue(
            HouseholdMember.objects.filter(
                household_id=hid, user=self.owner, role="owner"
            ).exists()
        )
        resp = self.client.post(
            f"/api/households/{hid}/add_dependent/",
            {"label": "Kid"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["is_dependent"])

    def test_family_member_limit(self):
        self.client.force_login(self.owner)
        hid = self.client.post(
            "/api/households/", {"name": "Home"}, content_type="application/json"
        ).json()["id"]
        for i in range(6):
            resp = self.client.post(
                f"/api/households/{hid}/add_member/",
                {"display_name": f"member{i}"},
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 201)
        resp = self.client.post(
            f"/api/households/{hid}/add_member/",
            {"display_name": "overflow"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

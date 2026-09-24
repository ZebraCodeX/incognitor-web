from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from core.crypto import blind_index, mask_identifier
from core.models import ActivityLog, AuditEvent, UserProfile
from core.services.ssrf import UnsafeURLError, validate_outbound_url


class CryptoTests(TestCase):
    def test_blind_index_is_deterministic_and_keyed(self):
        first = blind_index("email", "Alice@Example.com")
        second = blind_index("email", "alice@example.com")
        self.assertEqual(first, second)
        self.assertNotEqual(first, blind_index("phone", "alice@example.com"))
        self.assertEqual(len(first), 64)

    def test_masking(self):
        self.assertEqual(mask_identifier("email", "alice@example.com"), "a***@example.com")
        self.assertEqual(mask_identifier("phone", "+15551234567"), "***-***-4567")
        self.assertNotIn("alice", mask_identifier("email", "alice@example.com"))


class SSRFValidationTests(TestCase):
    def test_blocks_loopback_and_metadata(self):
        for url in [
            "http://127.0.0.1/opt-out",
            "http://localhost/opt-out",
            "http://169.254.169.254/latest/meta-data/",
            "file:///etc/passwd",
        ]:
            with self.assertRaises(UnsafeURLError):
                validate_outbound_url(url)

    @override_settings(SENTINEL_ALLOWED_WEBFORM_HOSTS=["broker.example"])
    def test_allowlist_enforced(self):
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("https://evil.example/optout")
        # A host on the allowlist passes (no DNS resolution needed).
        validate_outbound_url("https://broker.example/optout", resolve=False)


class SecurityHeaderTests(TestCase):
    def test_security_headers_present(self):
        resp = self.client.get("/")
        self.assertEqual(resp["X-Frame-Options"], "DENY")
        self.assertIn("Permissions-Policy", resp)
        self.assertTrue(
            "Content-Security-Policy" in resp
            or "Content-Security-Policy-Report-Only" in resp
        )


class AuditEventTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("aud", "aud@e.com", "pw123456!!")

    def test_audit_rows_are_append_only(self):
        event = AuditEvent.objects.create(user=self.user, action="test.action")
        event.action = "tampered"
        with self.assertRaises(ValueError):
            event.save()
        with self.assertRaises(ValueError):
            event.delete()


class ActivityIdorTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice2", "a2@e.com", "pw123456!!")
        self.bob = User.objects.create_user("bob2", "b2@e.com", "pw123456!!")
        UserProfile.objects.create(user=self.alice)
        UserProfile.objects.create(user=self.bob)
        ActivityLog.objects.create(user=self.alice, action="alice_secret")
        ActivityLog.objects.create(user=self.bob, action="bob_secret")

    def test_activity_is_scoped_to_requesting_user(self):
        self.client.force_login(self.alice)
        resp = self.client.get("/api/activities/")
        self.assertEqual(resp.status_code, 200)
        actions = [row["action"] for row in resp.json()]
        self.assertIn("alice_secret", actions)
        self.assertNotIn("bob_secret", actions)


class SignupPasswordValidationTests(TestCase):
    def test_weak_password_rejected(self):
        resp = self.client.post(
            "/api/auth/signup/",
            {
                "username": "weakuser",
                "email": "weak@example.com",
                "password1": "password",
                "password2": "password",
                "first_name": "Weak",
                "last_name": "User",
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())
        self.assertFalse(User.objects.filter(username="weakuser").exists())

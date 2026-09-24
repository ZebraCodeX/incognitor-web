from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from core.models import PushSubscription, UserProfile
from core.services import push


class PushSubscriptionApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("pusher", "push@e.com", "pw123456!!")
        UserProfile.objects.create(user=self.user)

    def test_subscribe_creates_and_updates(self):
        self.client.force_login(self.user)
        payload = {
            "endpoint": "https://push.example/sub/1",
            "keys": {"p256dh": "abc", "auth": "def"},
        }
        resp = self.client.post("/api/push/subscribe/", payload, content_type="application/json")
        self.assertEqual(resp.status_code, 201)
        sub = PushSubscription.objects.get(endpoint=payload["endpoint"])
        self.assertEqual(sub.user, self.user)
        self.assertEqual(sub.p256dh, "abc")

        # Re-subscribing the same endpoint updates rather than duplicating.
        resp = self.client.post("/api/push/subscribe/", payload, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PushSubscription.objects.filter(endpoint=payload["endpoint"]).count(), 1)

    def test_unsubscribe_deactivates(self):
        self.client.force_login(self.user)
        PushSubscription.objects.create(
            user=self.user, endpoint="https://push.example/x", p256dh="a", auth="b"
        )
        resp = self.client.post(
            "/api/push/unsubscribe/",
            {"endpoint": "https://push.example/x"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(PushSubscription.objects.get(endpoint="https://push.example/x").is_active)

    def test_vapid_key_endpoint_when_unconfigured(self):
        self.client.force_login(self.user)
        resp = self.client.get("/api/push/vapid_public_key/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["enabled"])


class PushServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("pushsvc", "ps@e.com", "pw123456!!")
        UserProfile.objects.create(user=self.user)

    def test_send_push_noop_when_unconfigured(self):
        PushSubscription.objects.create(
            user=self.user, endpoint="https://push.example/a", p256dh="a", auth="b"
        )
        self.assertEqual(push.send_push(self.user, "hi"), 0)

    @override_settings(VAPID_PRIVATE_KEY="private", VAPID_PUBLIC_KEY="public")
    @patch("pywebpush.webpush")
    def test_send_push_delivers_to_active_subscriptions(self, mock_webpush):
        PushSubscription.objects.create(
            user=self.user, endpoint="https://push.example/a", p256dh="a", auth="b"
        )
        sent = push.send_push(self.user, "Title", "Body")
        self.assertEqual(sent, 1)
        self.assertTrue(mock_webpush.called)

    @override_settings(VAPID_PRIVATE_KEY="private")
    @patch("core.services.push.send_push")
    def test_notify_dispatches_web_push(self, mock_send):
        from core.services.notifications import notify

        notify(self.user, "New exposure", "details", severity="high")
        self.assertTrue(mock_send.called)

from django.test import TestCase
from django.test import Client
from django.contrib.auth.models import User
from unittest.mock import patch
from core.models import Broker, UserProfile
from core.services.email_engine import EmailDeletionEngine


class ApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com", password="pw12345!"
        )
        UserProfile.objects.create(user=self.user)
        Broker.objects.create(
            name="Broker X",
            slug="broker-x",
            website_url="https://x.com",
            opt_out_email="privacy@x.com",
            removal_method="email",
        )

    def test_signup_api(self):
        resp = self.client.post(
            "/api/auth/signup/",
            {
                "username": "bob",
                "email": "bob@b.com",
                "password1": "testpass123",
                "password2": "testpass123",
                "first_name": "Bob",
                "last_name": "Test",
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["username"], "bob")

    def test_broker_list_requires_auth(self):
        resp = self.client.get("/api/brokers/")
        self.assertEqual(resp.status_code, 403)

    def test_broker_list_authenticated(self):
        self.client.force_login(self.user)
        resp = self.client.get("/api/brokers/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["name"], "Broker X")

    def test_create_scan_requires_auth(self):
        resp = self.client.post("/api/scans/", {"full_name": "A", "email": "a@a.com"}, content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    @patch("core.tasks.run_scan.delay")
    def test_create_scan_authenticated(self, mock_delay):
        self.client.force_login(self.user)
        resp = self.client.post(
            "/api/scans/",
            {"full_name": "Alice Example", "email": "alice@example.com"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["full_name"], "Alice Example")
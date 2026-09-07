from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from unittest.mock import patch, MagicMock
from core.models import Broker, Scan, RemovalRequest, UserProfile
from core.services.scan_engine import ScanEngine


class ScanEngineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com", password="pw12345!"
        )
        UserProfile.objects.create(user=self.user)
        self.email_broker = Broker.objects.create(
            name="Email Broker",
            slug="email-broker",
            website_url="https://e.com",
            opt_out_email="privacy@e.com",
            removal_method="email",
        )
        self.manual_broker = Broker.objects.create(
            name="Manual Broker",
            slug="manual-broker",
            website_url="https://m.com",
            removal_method="manual",
        )
        self.scan = Scan.objects.create(
            user=self.user,
            full_name="Alice Example",
            email="alice@example.com",
        )

    @patch("core.services.scan_engine.EmailDeletionEngine.send_request")
    def test_run_completes(self, mock_send):
        mock_send.return_value = {"sent_to": "privacy@e.com", "subject": "test"}

        engine = ScanEngine(self.scan.id)
        result = engine.run()

        self.assertEqual(result.status, Scan.Status.COMPLETED)
        self.assertEqual(result.total_brokers, 2)
        self.assertTrue(result.completed_at is not None)

        requests = RemovalRequest.objects.filter(scan=self.scan)
        self.assertEqual(requests.count(), 2)

        email_req = requests.get(broker=self.email_broker)
        self.assertEqual(email_req.status, RemovalRequest.Status.SENT)

        manual_req = requests.get(broker=self.manual_broker)
        self.assertEqual(manual_req.status, RemovalRequest.Status.NEEDS_MANUAL)

    @patch("core.services.scan_engine.EmailDeletionEngine.send_request")
    def test_email_failure_marks_failed(self, mock_send):
        mock_send.side_effect = Exception("SMTP down")

        engine = ScanEngine(self.scan.id)
        engine.run()

        req = RemovalRequest.objects.get(scan=self.scan, broker=self.email_broker)
        self.assertEqual(req.status, RemovalRequest.Status.FAILED)
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.failed_count, 1)

    def test_cannot_rerun_completed(self):
        self.scan.status = Scan.Status.COMPLETED
        self.scan.save()
        with self.assertRaises(ValueError):
            ScanEngine(self.scan.id).run()
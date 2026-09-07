from django.test import TestCase
from django.contrib.auth.models import User
from core.models import Broker, Scan, RemovalRequest, DataStopRequest, UserProfile


class BrokerModelTests(TestCase):
    def setUp(self):
        self.broker = Broker.objects.create(
            name="Test Broker",
            slug="test-broker",
            website_url="https://example.com",
            opt_out_email="privacy@example.com",
            removal_method="email",
        )

    def test_broker_str(self):
        self.assertEqual(str(self.broker), "Test Broker")

    def test_default_priority(self):
        b = Broker(name="X", slug="x", website_url="https://x.com")
        b.save()
        self.assertEqual(b.priority, 0)


class ScanModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com", password="pw12345!"
        )
        UserProfile.objects.create(user=self.user)
        self.broker = Broker.objects.create(
            name="Broker A",
            slug="broker-a",
            website_url="https://a.com",
            opt_out_email="privacy@a.com",
            removal_method="email",
        )
        self.scan = Scan.objects.create(
            user=self.user,
            full_name="Alice Example",
            email="alice@example.com",
            total_brokers=10,
            completed_brokers=5,
        )

    def test_progress_percent(self):
        self.assertEqual(self.scan.progress_percent, 50)

    def test_progress_empty(self):
        s = Scan.objects.create(user=self.user, full_name="Bob", email="b@b.com")
        self.assertEqual(s.progress_percent, 0)

    def test_scan_str(self):
        self.assertIn("Alice Example", str(self.scan))


class RemovalRequestModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", email="u@u.com", password="pw12345!")
        self.broker = Broker.objects.create(
            name="Broker B",
            slug="broker-b",
            website_url="https://b.com",
            opt_out_email="privacy@b.com",
        )
        self.scan = Scan.objects.create(user=self.user, full_name="U", email="u@u.com")

    def test_unique_scan_broker(self):
        RemovalRequest.objects.create(scan=self.scan, broker=self.broker, method="email")
        with self.assertRaises(Exception):
            RemovalRequest.objects.create(scan=self.scan, broker=self.broker, method="email")


class DataStopModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="d", email="d@d.com", password="pw12345!")
        self.broker = Broker.objects.create(
            name="Broker D",
            slug="broker-d",
            website_url="https://d.com",
            opt_out_email="privacy@d.com",
        )

    def test_defaults(self):
        stop = DataStopRequest.objects.create(user=self.user, broker=self.broker)
        self.assertTrue(stop.stop_selling)
        self.assertTrue(stop.stop_sharing)
        self.assertTrue(stop.stop_marketing)
        self.assertEqual(stop.status, DataStopRequest.Status.PENDING)
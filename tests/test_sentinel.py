from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.agent import SentinelAgent, triage
from core.agent.base import ExposureSource, Finding
from core.agent.matcher import match_text, name_variants
from core.agent.planner import choose_jurisdiction
from core.models import (
    AgentJob,
    Broker,
    Exposure,
    Notification,
    RemovalCampaign,
    UserProfile,
    Watchlist,
)


class FakeBreachSource(ExposureSource):
    name = "fake"
    kind = "breach"
    disabled_reason = "never"

    def is_configured(self):
        return True

    def search(self, identifiers, context=None):
        return [
            Finding(
                source=self.name,
                kind="breach",
                title="Fake breach of Acme",
                url="https://acme-broker.com/records",
                breach_name="AcmeLeak",
                matched_kind="email",
                matched_value=identifiers.get("email", ""),
                data_classes=["Email addresses", "Passwords"],
                confidence=1.0,
            )
        ]


class MatcherTests(TestCase):
    def test_email_match(self):
        result = match_text("contact me at alice@example.com", {"email": "alice@example.com"})
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["kind"], "email")

    def test_name_variants_and_nicknames(self):
        variants = name_variants("William Smith")
        self.assertIn("bill smith", variants)
        result = match_text("Bill Smith lives here", {"full_name": "William Smith"})
        self.assertGreaterEqual(result["score"], 0.7)


class TriageTests(TestCase):
    def test_critical_for_ssn(self):
        finding = Finding(source="x", kind="breach", title="t", data_classes=["SSN"])
        self.assertEqual(triage.score_severity(finding), "critical")

    def test_high_for_passwords(self):
        finding = Finding(source="x", kind="breach", title="t", data_classes=["Passwords"])
        self.assertEqual(triage.score_severity(finding), "high")

    def test_dedupe_keeps_highest_confidence(self):
        low = Finding(source="x", kind="breach", title="t", url="u", confidence=0.4)
        high = Finding(source="x", kind="breach", title="t", url="u", confidence=0.9)
        self.assertEqual(len(triage.dedupe([low, high])), 1)
        self.assertEqual(triage.dedupe([low, high])[0].confidence, 0.9)


class JurisdictionTests(TestCase):
    def test_state_law_selected(self):
        self.assertEqual(choose_jurisdiction({"state": "California"}), "CCPA/CPRA")

    def test_non_us_defaults_to_gdpr(self):
        self.assertEqual(choose_jurisdiction({"country": "Germany"}), "GDPR")


class AgentOrchestrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("agent", "agent@example.com", "pw123456!!")
        UserProfile.objects.create(user=self.user)
        self.broker = Broker.objects.create(
            name="Acme Broker",
            slug="acme-broker",
            website_url="https://acme-broker.com",
            opt_out_email="privacy@acme-broker.com",
            removal_method="email",
        )
        self.identity = self.user.identities.create(label="Me", is_primary=True)
        self.identity.identifiers.create(
            kind="email", blind_index="deadbeef", masked_value="a***@example.com"
        )
        self.watchlist = Watchlist.objects.create(
            user=self.user, identity=self.identity, name="Default"
        )

    def test_run_creates_exposure_campaign_job_and_notification(self):
        agent = SentinelAgent(self.user)
        run, created = agent.run_watchlist(
            self.watchlist,
            identifiers={"email": "agent@example.com", "full_name": "Agent Example"},
            sources=[FakeBreachSource()],
            allow_auto_remove=True,
        )
        self.assertEqual(run.findings_count, 1)
        self.assertEqual(len(created), 1)

        exposure = created[0]
        self.assertEqual(exposure.kind, "breach")
        self.assertEqual(exposure.severity, "high")
        # The raw email must never be persisted.
        self.assertNotIn("agent@example.com", str(exposure.__dict__))
        self.assertEqual(exposure.masked_evidence, "a***@example.com")

        campaign = RemovalCampaign.objects.get(exposure=exposure)
        self.assertEqual(campaign.channel, "email")
        self.assertEqual(campaign.broker, self.broker)
        self.assertEqual(campaign.jurisdiction, "CCPA/CPRA and GDPR (where applicable)")

        self.assertTrue(AgentJob.objects.filter(exposure=exposure).exists())
        self.assertTrue(Notification.objects.filter(user=self.user).exists())

    def test_rerun_deduplicates(self):
        agent = SentinelAgent(self.user)
        agent.run_watchlist(
            self.watchlist, identifiers={"email": "agent@example.com"},
            sources=[FakeBreachSource()], allow_auto_remove=False,
        )
        run2, created2 = agent.run_watchlist(
            self.watchlist, identifiers={"email": "agent@example.com"},
            sources=[FakeBreachSource()], allow_auto_remove=False,
        )
        self.assertEqual(len(created2), 0)
        self.assertEqual(Exposure.objects.filter(user=self.user).count(), 1)

    def test_escalation_creates_regulator_job(self):
        agent = SentinelAgent(self.user)
        _, created = agent.run_watchlist(
            self.watchlist, identifiers={"email": "agent@example.com"},
            sources=[FakeBreachSource()], allow_auto_remove=True,
        )
        campaign = RemovalCampaign.objects.get(exposure=created[0])
        campaign.status = RemovalCampaign.Status.SUBMITTED
        campaign.submitted_at = timezone.now()
        campaign.deadline_at = timezone.now() - timezone.timedelta(days=1)
        campaign.save()

        escalated = agent.escalate_overdue_campaigns()
        self.assertEqual(escalated, 1)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, RemovalCampaign.Status.ESCALATED)
        self.assertTrue(
            AgentJob.objects.filter(campaign=campaign, job_type=AgentJob.Type.ESCALATE).exists()
        )


class SentinelApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("api", "api@example.com", "pw123456!!")
        UserProfile.objects.create(user=self.user)
        self.other = User.objects.create_user("other", "other@example.com", "pw123456!!")
        UserProfile.objects.create(user=self.other)

    def test_identity_create_computes_blind_index_and_discards_plaintext(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            "/api/identities/",
            {
                "label": "Me",
                "identifiers": [{"kind": "email", "value": "api@example.com"}],
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        identifier = self.user.identities.first().identifiers.first()
        self.assertEqual(identifier.masked_value, "a***@example.com")
        self.assertNotEqual(identifier.blind_index, "")
        # Plaintext is not stored anywhere.
        self.assertFalse(identifier.value_encrypted)

    def test_exposures_are_scoped(self):
        self.user.exposures.create(kind="breach", severity="high", title="mine")
        self.other.exposures.create(kind="breach", severity="high", title="theirs")
        self.client.force_login(self.user)
        resp = self.client.get("/api/exposures/")
        titles = [row["title"] for row in resp.json()]
        self.assertEqual(titles, ["mine"])

    def test_agent_run_endpoint(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            "/api/agent/run/",
            {"identifiers": {"email": "api@example.com"}},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("run_id", resp.json())

    def test_on_device_finding_alerts_and_queues_removal(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            "/api/agent/handle_on_device_finding/",
            {
                "kind": "people_search",
                "identifier_kind": "email",
                "value": "api@example.com",
                "title": "Listing",
                "url": "https://www.spokeo.com/person/1",
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["created"])
        self.assertTrue(Notification.objects.filter(user=self.user).exists())
        self.assertTrue(Exposure.objects.filter(user=self.user).exists())

    def test_agent_job_claim_and_complete(self):
        exposure = self.user.exposures.create(kind="breach", severity="high", title="mine")
        campaign = RemovalCampaign.objects.create(
            user=self.user, exposure=exposure, channel="email",
            status=RemovalCampaign.Status.QUEUED,
        )
        job = AgentJob.objects.create(
            user=self.user, campaign=campaign, job_type=AgentJob.Type.SEND_EMAIL
        )
        self.client.force_login(self.user)
        resp = self.client.post(f"/api/agent/jobs/{job.id}/claim/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "claimed")

        resp = self.client.post(
            f"/api/agent/jobs/{job.id}/complete/",
            {"confirmation_code": "ABC123"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, RemovalCampaign.Status.SUBMITTED)
        self.assertEqual(campaign.confirmation_code, "ABC123")


class SchedulerTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sched", "sched@example.com", "pw123456!!")
        UserProfile.objects.create(user=self.user)

    def test_due_watchlist_queues_monitor_job_once(self):
        from core.tasks import queue_due_watchlist_jobs

        watchlist = Watchlist.objects.create(
            user=self.user, name="Due", next_run_at=timezone.now() - timezone.timedelta(hours=1)
        )
        self.assertEqual(queue_due_watchlist_jobs(), 1)
        self.assertEqual(queue_due_watchlist_jobs(), 0)  # already queued
        self.assertTrue(
            AgentJob.objects.filter(
                watchlist=watchlist, job_type=AgentJob.Type.MONITOR
            ).exists()
        )

    def test_process_user_campaigns_escalates_overdue(self):
        from core.tasks import process_user_campaigns

        exposure = self.user.exposures.create(kind="breach", severity="high", title="x")
        RemovalCampaign.objects.create(
            user=self.user, exposure=exposure, channel="email",
            status=RemovalCampaign.Status.SUBMITTED,
            submitted_at=timezone.now() - timezone.timedelta(days=60),
            deadline_at=timezone.now() - timezone.timedelta(days=30),
        )
        result = process_user_campaigns()
        self.assertEqual(result["escalations"], 1)

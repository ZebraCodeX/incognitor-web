from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.agent import SentinelAgent
from core.agent.base import ExposureSource, Finding
from core.models import (
    AgentJob,
    Broker,
    Exposure,
    RemovalCampaign,
    UserProfile,
    Watchlist,
)
from core.services import aliases, provenance
from core.services.compliance import recompute_all, score_broker
from core.services.ledger import append, verify_chain


class EchoSource(ExposureSource):
    """Returns one finding that matches a specific value/kind."""

    name = "echo"
    kind = "people_search"
    disabled_reason = "never"

    def __init__(self, value, kind="email", url="https://acme-broker.com/p/1",
                 finding_kind=None):
        self.value = value
        self.kind = kind
        self.finding_kind = finding_kind or ("people_search" if kind == "full_name" else "breach")
        self.url = url

    def is_configured(self):
        return True

    def search(self, identifiers, context=None):
        return [
            Finding(
                source=self.name,
                kind=self.finding_kind,
                title="Echo finding",
                url=self.url,
                matched_kind=self.kind,
                matched_value=self.value,
                data_classes=["Email addresses"],
                confidence=0.9,
            )
        ]


class BaseAgentCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("novel", "novel@example.com", "pw123456!!")
        UserProfile.objects.create(user=self.user)
        self.broker = Broker.objects.create(
            name="Acme Broker",
            slug="acme-broker",
            website_url="https://acme-broker.com",
            opt_out_email="privacy@acme-broker.com",
            removal_method="email",
        )
        self.identity = self.user.identities.create(label="Me", is_primary=True)
        self.watchlist = Watchlist.objects.create(
            user=self.user, identity=self.identity, name="Default"
        )

    def run_source(self, source, identifiers=None, auto=False):
        return SentinelAgent(self.user).run_watchlist(
            self.watchlist,
            identifiers=identifiers or {"email": "novel@example.com"},
            sources=[source],
            allow_auto_remove=auto,
        )


class CanaryTests(BaseAgentCase):
    def test_canary_trigger_is_critical_and_marks_provenance(self):
        identifier, value = aliases.create_canary(
            self.identity, self.broker, "novel@example.com"
        )
        _, created = self.run_source(EchoSource(value, kind="email"))
        self.assertEqual(len(created), 1)
        exposure = created[0]
        self.assertEqual(exposure.kind, Exposure.Kind.CANARY)
        self.assertEqual(exposure.severity, "critical")
        self.assertEqual(
            exposure.provenance.get("likely_source_broker_name"), "Acme Broker"
        )
        self.assertTrue(exposure.provenance.get("is_canary"))
        identifier.refresh_from_db()
        self.assertIsNotNone(identifier.triggered_at)

    def test_canary_endpoint_creates_and_returns_value(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            f"/api/identities/{self.identity.id}/canary/",
            {"base_email": "novel@example.com", "broker_id": str(self.broker.id)},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("+acme-broker-", body["value"])
        self.assertTrue(body["masked_value"].endswith("@example.com"))


class AliasProvenanceTests(BaseAgentCase):
    def test_alias_attribution(self):
        _, value = aliases.create_alias(self.identity, self.broker, "novel@example.com")
        _, created = self.run_source(EchoSource(value, kind="email"))
        exposure = created[0]
        self.assertEqual(exposure.provenance.get("via"), "alias")
        self.assertEqual(
            exposure.provenance.get("likely_source_broker_name"), "Acme Broker"
        )

    def test_superspreader_correlation(self):
        # Two normal exposures with the same blind index from different sources.
        self.run_source(EchoSource("novel@example.com", url="https://a-broker.com/1"))
        _, created = self.run_source(EchoSource("novel@example.com", url="https://acme-broker.com/2"))
        # The second finding shares a blind index with the first.
        data = provenance.refresh_exposure(created[0])
        self.assertGreaterEqual(data["shared_count"], 1)


class DeindexTests(BaseAgentCase):
    def test_deindex_job_queued_for_search_result(self):
        _, created = self.run_source(
            EchoSource(
                "novel@example.com",
                url="https://acme-broker.com/profile/1",
                finding_kind="people_search",
            ),
            auto=True,
        )
        exposure = created[0]
        self.assertTrue(
            AgentJob.objects.filter(exposure=exposure, job_type=AgentJob.Type.DEINDEX).exists()
        )


class LedgerTests(BaseAgentCase):
    def test_chain_verifies_and_detects_tampering(self):
        exposure = self.user.exposures.create(kind="breach", severity="high", title="x")
        campaign = RemovalCampaign.objects.create(
            user=self.user, exposure=exposure, channel="email",
            status=RemovalCampaign.Status.QUEUED,
        )
        append(campaign, "request_queued", {"channel": "email"})
        append(campaign, "email_sent", {"to": "privacy@acme-broker.com"})
        self.assertTrue(verify_chain(campaign)["valid"])
        self.assertEqual(verify_chain(campaign)["length"], 2)

        tampered = campaign.evidence.order_by("sequence").first()
        tampered.metadata = {"channel": "forged"}
        tampered.save(update_fields=["metadata"])
        result = verify_chain(campaign)
        self.assertFalse(result["valid"])
        self.assertEqual(result["broken_at"], 0)


class ComplianceTests(BaseAgentCase):
    def test_score_reflects_outcomes(self):
        exposure = self.user.exposures.create(kind="breach", severity="high", title="x")
        for status in [RemovalCampaign.Status.VERIFIED, RemovalCampaign.Status.VERIFIED,
                       RemovalCampaign.Status.FAILED]:
            RemovalCampaign.objects.create(
                user=self.user, exposure=exposure, broker=self.broker,
                channel="email", status=status,
                requested_at=timezone.now() - timezone.timedelta(days=5),
                completed_at=timezone.now(),
            )
        score = score_broker(self.broker)
        self.assertIsNotNone(score)
        self.assertGreater(score, 0)
        self.assertEqual(self.broker.removal_rate, round(2 / 3, 4))
        self.assertGreaterEqual(recompute_all(), 1)

"""The Sentinel agent: orchestrates monitoring, triage and removal campaigns.

Execution model (zero-knowledge, on-device):
- The server never stores plaintext PII. Identifiers are supplied transiently by
  the trusted on-device agent for the duration of a detection run and are
  immediately converted to blind indexes.
- Detection runs server-side against configured sources and persists only
  masked findings.
- Actual removal sending / web-form filling is queued as an :class:`AgentJob`
  for the on-device executor, which holds the vault key.
"""

import logging
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

from core.audit import record as audit_record
from core.crypto import blind_index, mask_identifier
from core.entitlements import UNLIMITED, get_entitlements
from core.models import (
    AgentJob,
    BreachEvent,
    Broker,
    Exposure,
    IdentityIdentifier,
    MonitorRun,
    RemovalCampaign,
    Watchlist,
)
from core.services import provenance as provenance_service
from core.services.deindex import should_deindex
from core.services.ledger import append as ledger_append
from core.services.notifications import notify

from . import triage
from .planner import choose_channel, choose_jurisdiction, deadline_from_now
from .sources import default_sources

logger = logging.getLogger(__name__)


class SentinelAgent:
    def __init__(self, user):
        self.user = user

    # ------------------------------------------------------------------ run
    def run_watchlist(self, watchlist: Watchlist, identifiers: dict | None = None,
                      sources=None, allow_auto_remove: bool | None = None):
        """Run monitoring for a watchlist and return (run, newly_created).

        ``identifiers`` must be supplied by the on-device agent; the server does
        not persist them.
        """
        identifiers = identifiers or {}
        run = MonitorRun.objects.create(
            watchlist=watchlist,
            status=MonitorRun.Status.RUNNING,
            started_at=timezone.now(),
        )

        source_list = sources if sources is not None else default_sources(
            include_breaches=watchlist.include_breaches,
            include_web_search=watchlist.include_web_search,
            include_pastes=watchlist.include_pastes,
        )

        findings = []
        checked = []
        for source in source_list:
            if not source.is_configured():
                continue
            try:
                found = source.search(identifiers, context={"user_id": self.user.id})
                for finding in found:
                    finding.severity = triage.score_severity(finding)
                findings.extend(found)
                checked.append(source.name)
            except Exception as exc:  # noqa: BLE001
                logger.exception("source %s failed: %s", source.name, exc)

        findings = triage.sort_by_severity(triage.dedupe(findings))

        created = []
        for finding in findings:
            exposure, was_created = self._persist_finding(finding, watchlist, run)
            if was_created:
                created.append(exposure)

        run.status = MonitorRun.Status.COMPLETED
        run.sources_checked = checked
        run.findings_count = len(findings)
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "sources_checked", "findings_count", "completed_at"])

        watchlist.last_run_at = timezone.now()
        watchlist.next_run_at = timezone.now() + timezone.timedelta(
            hours=max(watchlist.cadence_hours, 1)
        )
        watchlist.save(update_fields=["last_run_at", "next_run_at"])

        auto = settings.SENTINEL_AUTO_REMOVE if allow_auto_remove is None else allow_auto_remove
        for exposure in created:
            self._alert(exposure)
            if auto:
                self.queue_removal(exposure, identifiers)

        audit_record(
            "sentinel.monitor.completed",
            user=self.user,
            watchlist=str(watchlist.id),
            findings=len(findings),
            created=len(created),
        )
        return run, created

    # -------------------------------------------------------------- persist
    def _persist_finding(self, finding, watchlist, run):
        matched_blind = ""
        if finding.matched_value:
            matched_blind = blind_index(
                finding.matched_kind or "other", finding.matched_value
            )
        fp = triage.fingerprint(finding, matched_blind)

        existing = Exposure.objects.filter(user=self.user, fingerprint=fp).first()
        if existing:
            existing.last_seen = timezone.now()
            existing.confidence = max(existing.confidence, finding.confidence)
            if existing.status == Exposure.Status.REMOVED:
                existing.status = Exposure.Status.REAPPEARED
            existing.save(update_fields=["last_seen", "confidence", "status"])
            return existing, False

        breach_event = None
        if finding.kind == "breach" and finding.breach_name:
            breach_event, _ = BreachEvent.objects.update_or_create(
                source=finding.source,
                breach_name=finding.breach_name,
                defaults={
                    "breach_date": finding.breach_date,
                    "data_classes": finding.data_classes,
                    "pwn_count": finding.pwn_count,
                    "is_verified": bool(finding.metadata.get("is_verified")),
                },
            )

        site_domain = _domain(finding.url)
        masked = mask_identifier(finding.matched_kind, finding.matched_value)
        exposure = Exposure.objects.create(
            user=self.user,
            identity=watchlist.identity,
            watchlist=watchlist,
            monitor_run=run,
            breach_event=breach_event,
            kind=finding.kind,
            severity=finding.severity,
            status=Exposure.Status.NEW,
            title=finding.title[:300],
            source=finding.source,
            url=finding.url[:500],
            site_domain=site_domain,
            matched_blind_index=matched_blind,
            matched_identifier_kind=finding.matched_kind,
            masked_evidence=masked,
            confidence=finding.confidence,
            fingerprint=fp,
            metadata=finding.metadata,
        )

        # Correlate provenance (canary/alias attribution + superspreader graph).
        provenance = provenance_service.attribute(exposure)
        exposure.provenance = provenance
        update_fields = ["provenance"]
        if provenance.get("is_canary"):
            exposure.kind = Exposure.Kind.CANARY
            exposure.severity = Exposure.Severity.CRITICAL
            update_fields += ["kind", "severity"]
            self._mark_canary(exposure)
        exposure.save(update_fields=update_fields)
        return exposure, True

    def _mark_canary(self, exposure):
        IdentityIdentifier.objects.filter(
            identity__user=self.user,
            blind_index=exposure.matched_blind_index,
            role=IdentityIdentifier.Role.CANARY,
        ).update(triggered_at=timezone.now())

    # -------------------------------------------------------------- removal
    def queue_removal(self, exposure: Exposure, identifiers: dict | None = None):
        """Create a removal campaign + on-device job for an exposure."""
        if exposure.campaigns.exclude(
            status__in=[
                RemovalCampaign.Status.FAILED,
                RemovalCampaign.Status.CANCELLED,
            ]
        ).exists():
            return exposure.campaigns.first()

        broker = self._match_broker(exposure)
        channel = choose_channel(broker) if broker else "manual"
        jurisdiction = choose_jurisdiction(identifiers or {})

        campaign = RemovalCampaign.objects.create(
            user=self.user,
            exposure=exposure,
            broker=broker,
            channel=channel,
            status=RemovalCampaign.Status.QUEUED,
            jurisdiction=jurisdiction,
            requested_at=timezone.now(),
            deadline_at=deadline_from_now(),
        )

        exposure.status = Exposure.Status.REMOVAL_QUEUED
        exposure.save(update_fields=["status"])

        # Enforce the plan's daily send cap (staff are unlimited).
        entitlements = get_entitlements(self.user)
        if not self._within_send_quota(entitlements):
            campaign.channel = RemovalCampaign.Channel.MANUAL
            campaign.save(update_fields=["channel"])
            ledger_append(
                campaign, "send_cap_reached",
                {"cap": entitlements.max_sends_per_day, "plan": entitlements.plan},
            )
            audit_record("sentinel.removal.queued", user=self.user, campaign=str(campaign.id),
                         channel="manual")
            return campaign

        job_type = AgentJob.Type.SEND_EMAIL
        if channel == "web_form":
            job_type = AgentJob.Type.FILL_WEB_FORM
        AgentJob.objects.create(
            user=self.user,
            exposure=exposure,
            campaign=campaign,
            job_type=job_type,
            status=AgentJob.Status.QUEUED,
        )
        # Pre-index / cache de-listing, in parallel with the broker opt-out.
        if should_deindex(exposure):
            AgentJob.objects.create(
                user=self.user,
                exposure=exposure,
                campaign=campaign,
                job_type=AgentJob.Type.DEINDEX,
                status=AgentJob.Status.QUEUED,
            )
        ledger_append(
            campaign,
            "request_queued",
            {"channel": channel, "jurisdiction": jurisdiction, "broker": str(broker.id) if broker else ""},
        )
        audit_record(
            "sentinel.removal.queued",
            user=self.user,
            exposure=str(exposure.id),
            campaign=str(campaign.id),
            channel=channel,
        )
        return campaign

    def _within_send_quota(self, entitlements) -> bool:
        if entitlements.max_sends_per_day == UNLIMITED:
            return True
        since = timezone.now() - timezone.timedelta(days=1)
        recent = AgentJob.objects.filter(
            user=self.user,
            job_type=AgentJob.Type.SEND_EMAIL,
            created_at__gte=since,
        ).count()
        return recent < entitlements.max_sends_per_day

    def _match_broker(self, exposure: Exposure):
        domain = exposure.site_domain
        if domain:
            broker = Broker.objects.filter(
                is_active=True, website_url__icontains=domain
            ).first()
            if broker:
                return broker
        if exposure.title:
            first_word = exposure.title.split()[0]
            if len(first_word) > 3:
                return Broker.objects.filter(
                    is_active=True, name__icontains=first_word
                ).first()
        return None

    # -------------------------------------------------------------- alerting
    def alert(self, exposure: Exposure):
        """Public wrapper so other entry points can raise exposure alerts."""
        self._alert(exposure)

    def _alert(self, exposure: Exposure):
        severity = exposure.severity
        if exposure.kind == Exposure.Kind.CANARY:
            source = exposure.provenance.get("likely_source_broker_name", "a broker")
            title = f"Canary triggered: {source} leaked your tripwire data"
            body = (
                f"A unique tripwire you registered with {source} appeared elsewhere. "
                "This is proof that the record was leaked or sold.\n\n"
                f"Evidence: {exposure.url or 'n/a'}"
            )
        else:
            title = f"New {severity} exposure: {exposure.title[:120]}"
            body = (
                f"Source: {exposure.source}\n"
                f"Type: {exposure.get_kind_display()}\n"
                f"Matched: {exposure.masked_evidence or 'n/a'}\n"
                f"URL: {exposure.url or 'n/a'}\n\n"
                "Incognitor has queued a removal request."
            )
        notify(self.user, title, body, severity=severity, exposure=exposure)

    # -------------------------------------------------------------- periodic
    def verify_due_campaigns(self):
        from .verifier import needs_verification

        queued = 0
        for campaign in RemovalCampaign.objects.filter(
            user=self.user,
            status__in=[
                RemovalCampaign.Status.SUBMITTED,
                RemovalCampaign.Status.AWAITING_RESPONSE,
                RemovalCampaign.Status.REMOVED,
            ],
        ):
            if needs_verification(campaign):
                AgentJob.objects.create(
                    user=self.user,
                    campaign=campaign,
                    exposure=campaign.exposure,
                    job_type=AgentJob.Type.VERIFY,
                )
                queued += 1
        return queued

    def escalate_overdue_campaigns(self):
        from .verifier import is_overdue

        escalated = 0
        for campaign in RemovalCampaign.objects.filter(
            user=self.user,
            status__in=[
                RemovalCampaign.Status.SUBMITTED,
                RemovalCampaign.Status.AWAITING_RESPONSE,
                RemovalCampaign.Status.RUNNING,
                RemovalCampaign.Status.QUEUED,
            ],
        ):
            if not campaign.deadline_at or not is_overdue(campaign):
                continue
            campaign.status = RemovalCampaign.Status.ESCALATED
            campaign.save(update_fields=["status"])
            if campaign.exposure:
                campaign.exposure.status = Exposure.Status.FAILED
                campaign.exposure.save(update_fields=["status"])
            AgentJob.objects.create(
                user=self.user,
                campaign=campaign,
                exposure=campaign.exposure,
                job_type=AgentJob.Type.ESCALATE,
            )
            notify(
                self.user,
                f"Escalating: {campaign.broker.name if campaign.broker else 'broker'} missed the removal deadline",
                "Incognitor is preparing a regulator complaint.",
                severity="high",
                exposure=campaign.exposure,
            )
            escalated += 1
        return escalated


def _domain(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower()[4:] if host.lower().startswith("www.") else host.lower()

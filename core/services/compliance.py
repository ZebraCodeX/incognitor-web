"""Anonymised broker compliance scoring.

Aggregates removal outcomes (anonymously across all users) into a 0-100 score
so non-compliant brokers can be prioritised and pressured. No user-level data
leaves this module.
"""

from django.utils import timezone

from core.models import Broker, RemovalCampaign

_REMOVED = {RemovalCampaign.Status.REMOVED, RemovalCampaign.Status.VERIFIED}


def score_broker(broker: Broker):
    campaigns = RemovalCampaign.objects.filter(broker=broker)
    total = campaigns.count()
    if total == 0:
        broker.compliance_score = None
        broker.removal_rate = None
        broker.score_updated_at = timezone.now()
        broker.save(update_fields=["compliance_score", "removal_rate", "score_updated_at"])
        return None

    removed = campaigns.filter(status__in=_REMOVED).count()
    failed = campaigns.filter(status=RemovalCampaign.Status.FAILED).count()
    escalated = campaigns.filter(status=RemovalCampaign.Status.ESCALATED).count()
    rate = removed / total

    # Base score from removal rate; penalise failures and regulator escalations,
    # reward speed.
    score = rate * 100.0
    score -= (failed / total) * 20.0
    score -= (escalated / total) * 25.0

    completed = campaigns.filter(status__in=_REMOVED, requested_at__isnull=False,
                                 completed_at__isnull=False)
    durations = [
        (c.completed_at - c.requested_at).days
        for c in completed
        if c.completed_at and c.requested_at
    ]
    if durations:
        avg_days = sum(durations) / len(durations)
        if avg_days <= 7:
            score += 10
        elif avg_days > 30:
            score -= min((avg_days - 30), 20)

    score = max(0.0, min(100.0, score))
    broker.removal_rate = round(rate, 4)
    broker.compliance_score = round(score, 2)
    broker.score_updated_at = timezone.now()
    broker.save(update_fields=["removal_rate", "compliance_score", "score_updated_at"])
    return broker.compliance_score


def recompute_all() -> int:
    count = 0
    for broker in Broker.objects.filter(is_active=True):
        if score_broker(broker) is not None:
            count += 1
    return count

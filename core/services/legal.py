"""Jurisdiction detection and legally-formatted request/complaint templates."""

# US states with comprehensive consumer privacy statutes (as of 2025/2026).
_US_STATE_LAWS = {
    "california": "CCPA/CPRA",
    "colorado": "CPA",
    "connecticut": "CTDPA",
    "virginia": "VCDPA",
    "utah": "UCPA",
    "texas": "TDPSA",
    "oregon": "OCPA",
    "montana": "MCDPA",
    "iowa": "ICDPA",
    "indiana": "INCDPA",
    "tennessee": "TIPA",
    "delaware": "DPDPA",
    "new jersey": "NJDPA",
    "new hampshire": "NHPA",
    "kentucky": "KCDPA",
    "maryland": "MODPA",
    "minnesota": "MCDPA",
    "rhode island": "RIDPA",
}


def select_jurisdiction(identifiers: dict) -> str:
    """Pick the strongest applicable privacy regime from the subject's location."""
    country = (identifiers or {}).get("country", "").strip().lower()
    state = (identifiers or {}).get("state", "").strip().lower()
    if country and country not in {"us", "usa", "united states"}:
        if country in {"uk", "united kingdom"}:
            return "UK GDPR / DPA 2018"
        if country in {"ca", "canada"}:
            return "PIPEDA"
        return "GDPR"
    if state:
        law = _US_STATE_LAWS.get(state)
        if law:
            return law
        return "CCPA/CPRA + state law"
    return "CCPA/CPRA and GDPR (where applicable)"


_REMOVAL_BODY = """Dear {company} Privacy Team,

I am writing to exercise my legal right to delete all personal information you
hold about me, under the {jurisdiction}.

Please delete every record, profile, listing and derived inference linked to me,
including any data you have sold, shared or disclosed to third parties, and
instruct those recipients to delete it as well.

Identifiers to match:
- Full name: {name}
- Email: {email}
- Phone: {phone}
- Address: {address}

I request that you:
1. Delete all personal information concerning me from your systems and backups.
2. Stop selling, sharing or otherwise disclosing my information.
3. Confirm in writing, within the statutory response period, the categories
   deleted, the recipients notified, and the date of completion.

This request covers all of your subsidiaries, affiliates and processors.

Sincerely,
{name}
{email}
"""

_REGULATOR_BODY = """To the data protection authority,

I am filing a complaint against {company} for failure to honor my verified
deletion/opt-out request submitted on {requested_date} under the
{jurisdiction}. More than {days} days have elapsed without a compliant response.

Subject: {name} <{email}>
Reference: {reference}

I request that you investigate and direct the company to delete my personal
information and cease selling or sharing it.

Sincerely,
{name}
{email}
"""


def render_removal_letter(broker, personal_data: dict, jurisdiction: str):
    context = {
        "company": getattr(broker, "name", None) or "your organization",
        "jurisdiction": jurisdiction,
        "name": personal_data.get("full_name", ""),
        "email": personal_data.get("email", ""),
        "phone": personal_data.get("phone") or "Not provided",
        "address": personal_data.get("address") or "Not provided",
    }
    subject = f"Verified Deletion Request ({jurisdiction}) - {context['name']}"
    return subject, _REMOVAL_BODY.format(**context)


def render_regulator_complaint(broker, personal_data: dict, jurisdiction: str,
                               requested_date: str, days: int, reference: str):
    context = {
        "company": getattr(broker, "name", None) or "the company",
        "jurisdiction": jurisdiction,
        "requested_date": requested_date,
        "days": days,
        "reference": reference or "n/a",
        "name": personal_data.get("full_name", ""),
        "email": personal_data.get("email", ""),
    }
    subject = f"Complaint: {context['company']} non-compliance with {jurisdiction}"
    return subject, _REGULATOR_BODY.format(**context)

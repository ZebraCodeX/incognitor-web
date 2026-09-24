"""GitHub public-code exposure source.

Looks for an email address committed in public code (a common accidental leak).
Requires ``GITHUB_TOKEN``; the code-search API is authenticated-only.
"""

import logging

from django.conf import settings

from ..base import ExposureSource, Finding
from ..http import SourceUnavailable, request

logger = logging.getLogger(__name__)

_API = "https://api.github.com/search/code"


class GitHubSource(ExposureSource):
    name = "github"
    kind = "leak"
    disabled_reason = "GITHUB_TOKEN not set"

    def is_configured(self):
        return bool(getattr(settings, "GITHUB_TOKEN", ""))

    def search(self, identifiers, context=None):
        email = (identifiers or {}).get("email", "").strip()
        if not self.is_configured() or not email:
            return []
        headers = {
            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        }
        params = {"q": f'"{email}" in:file', "per_page": 30}
        try:
            resp = request("GET", _API, headers=headers, params=params)
        except SourceUnavailable:
            return []
        if resp.status_code != 200:
            logger.warning("GitHub search status %s", resp.status_code)
            return []

        findings = []
        for item in resp.json().get("items", []):
            repo = item.get("repository", {}) or {}
            findings.append(
                Finding(
                    source=self.name,
                    kind="leak",
                    title=f"Email in public code: {repo.get('full_name', 'unknown repo')}",
                    url=item.get("html_url", ""),
                    matched_kind="email",
                    matched_value=email,
                    confidence=0.8,
                    metadata={"repository": repo.get("full_name", ""), "path": item.get("path", "")},
                )
            )
        return findings

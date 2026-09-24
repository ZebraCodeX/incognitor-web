"""Web / people-search surface monitoring via Brave Search or Google CSE.

Findings are indexed search results that appear to reference the subject. A
result is only reported when the snippet/title actually matches one of the
subject's identifiers (name, email or phone), which keeps false positives down.
"""

import logging

from django.conf import settings

from ..base import ExposureSource, Finding, build_query_terms
from ..http import SourceUnavailable, request

logger = logging.getLogger(__name__)

_BRAVE = "https://api.search.brave.com/res/v1/web/search"
_GOOGLE = "https://www.googleapis.com/customsearch/v1"

# Domains that are people-search/data-broker sites rather than generic results.
_BROKER_DOMAINS = {
    "spokeo.com", "beenverified.com", "whitepages.com", "intelius.com",
    "radaris.com", "mylife.com", "peekyou.com", "truepeoplesearch.com",
    "fastpeoplesearch.com", "zabasearch.com", "peoplefinder.com",
    "instantcheckmate.com", "truthfinder.com", "checkpeople.com",
    "peoplelooker.com", "ussearch.com", "usphonebook.com",
}


class WebSearchSource(ExposureSource):
    name = "web_search"
    kind = "search_result"
    disabled_reason = "BRAVE_SEARCH_API_KEY or GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX not set"

    def is_configured(self):
        brave = bool(getattr(settings, "BRAVE_SEARCH_API_KEY", ""))
        google = bool(
            getattr(settings, "GOOGLE_CSE_API_KEY", "")
            and getattr(settings, "GOOGLE_CSE_CX", "")
        )
        return brave or google

    def search(self, identifiers, context=None):
        if not self.is_configured():
            return []
        terms = build_query_terms(identifiers or {})
        findings = []
        for term in terms[:3]:
            results = self._brave(term) if settings.BRAVE_SEARCH_API_KEY else []
            if not results and getattr(settings, "GOOGLE_CSE_API_KEY", ""):
                results = self._google(term)
            for result in results:
                finding = self._to_finding(result, identifiers)
                if finding:
                    findings.append(finding)
        return findings

    # -- providers ---------------------------------------------------------
    def _brave(self, term):
        headers = {
            "X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY,
            "Accept": "application/json",
        }
        try:
            resp = request("GET", _BRAVE, headers=headers, params={"q": term, "count": 20})
        except SourceUnavailable:
            return []
        if resp.status_code != 200:
            logger.warning("Brave search status %s", resp.status_code)
            return []
        data = resp.json()
        out = []
        for item in (data.get("web", {}) or {}).get("results", []):
            out.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("description", ""),
                }
            )
        return out

    def _google(self, term):
        params = {
            "key": settings.GOOGLE_CSE_API_KEY,
            "cx": settings.GOOGLE_CSE_CX,
            "q": term,
            "num": 10,
        }
        try:
            resp = request("GET", _GOOGLE, params=params)
        except SourceUnavailable:
            return []
        if resp.status_code != 200:
            return []
        out = []
        for item in resp.json().get("items", []):
            out.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                }
            )
        return out

    # -- mapping -----------------------------------------------------------
    def _to_finding(self, result, identifiers):
        from ..matcher import match_text

        text = f"{result.get('title', '')} {result.get('snippet', '')}"
        match = match_text(text, identifiers or {})
        if not match["score"]:
            return None
        domain = _domain(result.get("url", ""))
        is_broker = any(domain == d or domain.endswith("." + d) for d in _BROKER_DOMAINS)
        return Finding(
            source=self.name,
            kind="people_search" if is_broker else "search_result",
            title=result.get("title", "")[:300] or "Search result",
            url=result.get("url", ""),
            matched_kind=match["kind"],
            matched_value=match["value"],
            confidence=match["score"],
            metadata={"domain": domain, "is_broker": is_broker},
        )


def _domain(url):
    from urllib.parse import urlparse

    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().lstrip("www.")

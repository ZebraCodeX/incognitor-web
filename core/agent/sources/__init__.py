"""Built-in exposure sources and the source registry."""

from .dark_web import DarkWebSource
from .dehashed import DehashedSource
from .github import GitHubSource
from .hibp import HaveIBeenPwnedSource
from .paste import PasteSource
from .public_records import PublicRecordsSource
from .web_search import WebSearchSource


def default_sources(include_breaches=True, include_web_search=True, include_pastes=True):
    """Return the source instances enabled for a watchlist."""
    sources = []
    if include_breaches:
        sources.append(HaveIBeenPwnedSource())
        sources.append(DehashedSource())
        sources.append(DarkWebSource())
    if include_web_search:
        sources.append(WebSearchSource())
        sources.append(GitHubSource())
        sources.append(PublicRecordsSource())
    if include_pastes:
        sources.append(PasteSource())
    return sources


ALL_SOURCES = {
    "hibp": HaveIBeenPwnedSource,
    "dehashed": DehashedSource,
    "web_search": WebSearchSource,
    "github": GitHubSource,
    "paste": PasteSource,
    "public_records": PublicRecordsSource,
    "dark_web": DarkWebSource,
}

__all__ = [
    "default_sources",
    "ALL_SOURCES",
    "HaveIBeenPwnedSource",
    "DehashedSource",
    "DarkWebSource",
    "WebSearchSource",
    "GitHubSource",
    "PasteSource",
    "PublicRecordsSource",
]

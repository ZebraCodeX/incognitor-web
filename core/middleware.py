"""Security middleware for Incognitor.

Adds a hardened Content-Security-Policy plus a few headers that Django does not
set by default, and keeps a thread-local reference to the active request so the
audit-log helper can capture IP / user-agent without threading it through the
whole call stack.
"""

import threading

from django.conf import settings

_local = threading.local()


def get_current_request():
    return getattr(_local, "request", None)


class AuditContextMiddleware:
    """Expose the active request to ``core.audit`` helpers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        try:
            return self.get_response(request)
        finally:
            _local.request = None


class SecurityHeadersMiddleware:
    """Set a Content-Security-Policy and other defense-in-depth headers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only set headers that are not already present.
        if "Content-Security-Policy" not in response and "Content-Security-Policy-Report-Only" not in response:
            policy = self._build_csp()
            if policy:
                if settings.CSP_ENFORCE:
                    response["Content-Security-Policy"] = policy
                else:
                    response["Content-Security-Policy-Report-Only"] = policy

        response.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response

    @staticmethod
    def _build_csp():
        directives = {
            "default-src": settings.CSP_DEFAULT_SRC,
            "script-src": settings.CSP_SCRIPT_SRC,
            "style-src": settings.CSP_STYLE_SRC,
            "font-src": settings.CSP_FONT_SRC,
            "img-src": settings.CSP_IMG_SRC,
            "connect-src": settings.CSP_CONNECT_SRC,
            "object-src": "'none'",
            "base-uri": "'self'",
            "frame-ancestors": "'none'",
            "form-action": "'self'",
        }
        if settings.CSP_REPORT_URI:
            directives["report-uri"] = settings.CSP_REPORT_URI
        return "; ".join(f"{k} {v}" for k, v in directives.items())

import time
import traceback

from django.utils.deprecation import MiddlewareMixin

from common.models import ActivityLog, ErrorLog


class ActivityLogMiddleware(MiddlewareMixin):
    """Capture request/response metadata for auditing."""

    def process_request(self, request):
        request._start_time = time.monotonic()

    def process_response(self, request, response):
        try:
            duration = 0
            if hasattr(request, "_start_time"):
                duration = (time.monotonic() - request._start_time) * 1000
            user = getattr(request, "user", None) if hasattr(request, "user") else None
            ActivityLog.objects.create(
                user=user if getattr(user, "is_authenticated", False) else None,
                path=request.path[:512],
                method=request.method,
                status_code=getattr(response, "status_code", 0),
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                referrer=request.META.get("HTTP_REFERER", ""),
                duration_ms=duration,
                action_type="request",
                extra_meta={
                    "role": getattr(user, "role", None) if user else None,
                },
                session_key=getattr(request, "session", None) and request.session.session_key or "",
            )
        except Exception:
            # Fail-safe: never break the request pipeline
            pass
        return response

    def process_exception(self, request, exception):
        """Capture unhandled exceptions into ErrorLog and re-raise downstream."""
        try:
            user = getattr(request, "user", None) if hasattr(request, "user") else None
            ErrorLog.objects.create(
                user=user if getattr(user, "is_authenticated", False) else None,
                path=getattr(request, "path", "")[:512],
                method=getattr(request, "method", "")[:10],
                status_code=500,
                message=str(exception)[:2000],
                traceback="".join(traceback.format_exception(type(exception), exception, exception.__traceback__))[:8000],
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
                referrer=request.META.get("HTTP_REFERER", "")[:512],
            )
        except Exception:
            pass
        return None

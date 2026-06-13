"""
pyerror.django_support — Django integration (#41).

Provides:
    PyErrorMiddleware
        New-style Django middleware that logs and enriches every unhandled
        exception (analytics + OpenTelemetry + scrubbed JSON payload). By
        default it returns None from process_exception so Django's normal
        500 handling continues. Set ``PYERROR_JSON_ERRORS = True`` in your
        Django settings to return the humanized, scrubbed JSON payload as
        a JsonResponse instead.

        Wiring (settings.py):
            MIDDLEWARE = [
                ...,
                "pyerror.django_support.PyErrorMiddleware",
            ]
            PYERROR_JSON_ERRORS = True  # optional, default False

    management_command()
        Factory returning a Django BaseCommand subclass that prints the
        pyerror analytics report. Wiring: create the file
        ``yourapp/management/commands/pyerror_report.py`` containing:

            from pyerror.django_support import management_command
            Command = management_command()

        Then run ``python manage.py pyerror_report``.

Django is an OPTIONAL dependency: this module imports fine without it, and
all django imports happen lazily inside functions/methods. Instantiating
PyErrorMiddleware (or calling management_command) without Django installed
raises a helpful ImportError.
"""

import json
from typing import Any, Callable, Optional


def _require_django():
    """Raises a helpful ImportError when Django is not installed."""
    try:
        import django  # noqa: F401
    except ImportError:
        raise ImportError(
            "Django is required to use pyerror.django_support. "
            "Install it via 'pip install django'."
        )


class PyErrorMiddleware:
    """
    New-style Django middleware that humanizes unhandled exceptions.

    On every unhandled view exception it:
      1. Logs the error to pyerror analytics.
      2. Mirrors diagnostics onto the active OpenTelemetry span, if any.
      3. Builds a scrubbed JSON payload via pyerror.to_json.
      4. Returns a JsonResponse (status 500) when settings.PYERROR_JSON_ERRORS
         is truthy, otherwise returns None so Django's normal 500 flow
         (DEBUG page / handler500) continues.

    Integration code never raises into the host app: every step is guarded.
    """

    def __init__(self, get_response: Callable):
        _require_django()
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        return self.get_response(request)

    def process_exception(self, request: Any, exc: BaseException) -> Optional[Any]:
        # Log to analytics automatically
        try:
            from pyerror.analytics import log_error
            log_error(exc)
        except Exception:
            pass

        # Mirror diagnostics onto the active OpenTelemetry span, if any
        try:
            from pyerror import otel
            otel.record_exception(exc)
        except Exception:
            pass

        # Build the scrubbed JSON payload
        payload = None
        try:
            import pyerror
            payload = json.loads(pyerror.to_json(exc))
        except Exception:
            payload = None

        # Should we short-circuit with a JSON response?
        json_errors = False
        try:
            from django.conf import settings
            json_errors = bool(getattr(settings, "PYERROR_JSON_ERRORS", False))
        except Exception:
            json_errors = False

        if json_errors and payload is not None:
            try:
                from django.http import JsonResponse
                return JsonResponse(payload, status=500)
            except Exception:
                return None

        # Returning None lets Django's normal exception handling continue.
        return None


def management_command():
    """
    Returns a Django BaseCommand subclass that prints the pyerror
    analytics report (pyerror.get_analytics()).

    Wiring: create ``yourapp/management/commands/pyerror_report.py`` with:

        from pyerror.django_support import management_command
        Command = management_command()

    Then run ``python manage.py pyerror_report``.
    """
    try:
        from django.core.management.base import BaseCommand
    except ImportError:
        raise ImportError(
            "Django is required to use pyerror.django_support.management_command. "
            "Install it via 'pip install django'."
        )

    class Command(BaseCommand):
        help = "Prints the pyerror recurring-error analytics report."

        def handle(self, *args, **options):
            try:
                from pyerror.analytics import get_analytics
                self.stdout.write(str(get_analytics()))
            except Exception as e:
                self.stdout.write(f"pyerror analytics unavailable: {e}")

    return Command

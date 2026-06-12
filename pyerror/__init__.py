"""
pyerror: A Python error intelligence library for learners and production systems.
"""

from pyerror.core import (
    configure,
    humanize,
    beginner_mode,
    explain,
    diagnose,
    suggest,
    add_privacy_rule,
    to_json,
    inspect_last_error,
)
from pyerror.context import ignore, capture_scope
from pyerror.decorators import retry, capture_locals, fallback, self_healing
from pyerror.circuit_breaker import circuit_breaker, CircuitOpenError
from pyerror.wizard import debug_wizard
from pyerror.factory import create
from pyerror.comparison import compare
from pyerror.analytics import get_analytics, clear_analytics
from pyerror.sharing import generate_share_link
from pyerror.report import generate_markdown_report
from pyerror.testing import assert_readable, assert_not_exposed
from pyerror.integrations import configure_integrations, notify_slack, notify_sentry, send_email
from pyerror.system_info import get_system_info
from pyerror.frameworks import register_flask_error_handler, FastAPIErrorMiddleware
from pyerror.logging_handler import integrate_logging
from pyerror.formatting import Formatter

add_scrub_pattern = Formatter.add_scrub_pattern
add_scrub_callback = Formatter.add_scrub_callback

__version__ = "0.1.2"

__all__ = [
    "configure",
    "humanize",
    "beginner_mode",
    "explain",
    "diagnose",
    "suggest",
    "add_privacy_rule",
    "to_json",
    "inspect_last_error",
    "ignore",
    "capture_scope",
    "retry",
    "capture_locals",
    "fallback",
    "self_healing",
    "circuit_breaker",
    "CircuitOpenError",
    "debug_wizard",
    "create",
    "compare",
    "get_analytics",
    "clear_analytics",
    "generate_share_link",
    "generate_markdown_report",
    "assert_readable",
    "assert_not_exposed",
    "configure_integrations",
    "notify_slack",
    "notify_sentry",
    "send_email",
    "get_system_info",
    "register_flask_error_handler",
    "FastAPIErrorMiddleware",
    "integrate_logging",
    "add_scrub_pattern",
    "add_scrub_callback",
]

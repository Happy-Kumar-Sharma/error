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
from pyerror.context import ignore
from pyerror.decorators import retry, capture_locals, fallback
from pyerror.factory import create
from pyerror.comparison import compare
from pyerror.analytics import get_analytics, clear_analytics
from pyerror.sharing import generate_share_link
from pyerror.report import generate_markdown_report
from pyerror.testing import assert_readable, assert_not_exposed
from pyerror.integrations import configure_integrations, notify_slack, notify_sentry, send_email
from pyerror.system_info import get_system_info
from pyerror.frameworks import register_flask_error_handler, FastAPIErrorMiddleware

__version__ = "0.1.0"

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
    "retry",
    "capture_locals",
    "fallback",
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
]

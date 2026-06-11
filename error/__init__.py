"""
error: A Python error intelligence library for learners and production systems.
"""

from error.core import (
    configure,
    humanize,
    beginner_mode,
    explain,
    diagnose,
    suggest,
    add_privacy_rule,
    to_json,
)
from error.context import ignore
from error.decorators import retry, capture_locals, fallback
from error.factory import create
from error.comparison import compare
from error.analytics import get_analytics, clear_analytics
from error.sharing import generate_share_link
from error.report import generate_markdown_report
from error.testing import assert_readable, assert_not_exposed
from error.integrations import configure_integrations, notify_slack, notify_sentry, send_email

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
]

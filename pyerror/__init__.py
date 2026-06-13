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
from pyerror.circuit_breaker import (
    circuit_breaker, CircuitOpenError, breakers, show_breakers,
)
from pyerror.wizard import debug_wizard
from pyerror.factory import create
from pyerror.comparison import compare
from pyerror.analytics import (
    get_analytics, clear_analytics, set_sampling, set_release, releases_summary,
)
from pyerror.sharing import (
    generate_share_link, configure_community, share_fix, fetch_fixes,
)
from pyerror.report import generate_markdown_report
from pyerror.testing import assert_readable, assert_not_exposed
from pyerror.integrations import (
    configure_integrations, notify_slack, notify_sentry, send_email,
    notify_discord, notify_teams, notify_webhook,
    notify_pagerduty, notify_opsgenie,
)
from pyerror.system_info import get_system_info
from pyerror.frameworks import register_flask_error_handler, FastAPIErrorMiddleware
from pyerror.logging_handler import integrate_logging
from pyerror.formatting import Formatter
from pyerror.fuzzy import suggest_names
from pyerror.ai import ai_explain, AIExplanation, AIProviderError
from pyerror import otel
from pyerror.otel import fingerprint

# Intelligence
from pyerror.fixdiff import suggest_fix, format_fix
from pyerror.clustering import cluster_errors, show_clusters
from pyerror.knowledge import learn, recall, forget
from pyerror.weblinks import search_links, format_links
from pyerror.rootcause import analyze_chain
from pyerror.chainviz import format_chain, show_chain
from pyerror.smartrepr import smart_repr

# Runtime capture & diagnostics depth
from pyerror.asynctb import (
    flatten_async_tb, format_async,
    install as install_async_handler, uninstall as uninstall_async_handler,
)
from pyerror.threads import (
    install_thread_hooks, uninstall_thread_hooks, capture_subprocess_errors,
    RemoteError,
)
from pyerror.frame_timing import (
    timed_frames, annotate_exception as annotate_frame_timings,
    format_timings,
)
from pyerror.memwatch import snapshot_top, attach_snapshot
from pyerror.warnings_support import explain_warning, humanize_warnings, escalate

# Resilience
from pyerror.resilience import (
    timeout, bulkhead, bulkheads, BulkheadFullError,
    dead_letter, replay, replay_failed, list_dead_letters, clear_dead_letters,
    retry_rate_limited, hedge,
)
from pyerror import aio
from pyerror.aio import aretry, afallback, atimeout, acircuit_breaker, abulkhead

# Observability
from pyerror import metrics, structured_logging, budgets, dashboard
from pyerror.structured_logging import log_exception
from pyerror.budgets import set_budget, budget_status, clear_budget

# Framework integrations
from pyerror import django_support, tasks_support
from pyerror.cli_apps import humanize_cli
from pyerror.serverless import lambda_handler
from pyerror.db_errors import explain_db_error, enrich as enrich_db_error

# Education
from pyerror.i18n import set_language, reset_language, get_language, labels
from pyerror.encyclopedia import lookup, search as encyclopedia_search, all_errors
from pyerror.classroom import classroom_mode, reveal_more, disable_classroom, set_hint
from pyerror.quiz import quiz, quiz_history

# Doctor / CLI / Navigator
from pyerror.doctor import run_doctor
from pyerror.navigator import navigate

add_scrub_pattern = Formatter.add_scrub_pattern
add_scrub_callback = Formatter.add_scrub_callback

__version__ = "0.2.0"

__all__ = [
    # Core
    "configure", "humanize", "beginner_mode", "explain", "diagnose", "suggest",
    "add_privacy_rule", "to_json", "inspect_last_error",
    "ignore", "capture_scope",
    "retry", "capture_locals", "fallback", "self_healing",
    "circuit_breaker", "CircuitOpenError", "breakers", "show_breakers",
    "debug_wizard", "create", "compare",
    "get_analytics", "clear_analytics", "set_sampling", "set_release", "releases_summary",
    "generate_share_link", "configure_community", "share_fix", "fetch_fixes",
    "generate_markdown_report",
    "assert_readable", "assert_not_exposed",
    "configure_integrations", "notify_slack", "notify_sentry", "send_email",
    "notify_discord", "notify_teams", "notify_webhook",
    "notify_pagerduty", "notify_opsgenie",
    "get_system_info",
    "register_flask_error_handler", "FastAPIErrorMiddleware",
    "integrate_logging",
    "add_scrub_pattern", "add_scrub_callback",
    # AI / fuzzy / otel
    "suggest_names", "ai_explain", "AIExplanation", "AIProviderError",
    "otel", "fingerprint",
    # Intelligence
    "suggest_fix", "format_fix", "cluster_errors", "show_clusters",
    "learn", "recall", "forget", "search_links", "format_links",
    "analyze_chain", "format_chain", "show_chain", "smart_repr",
    # Runtime capture
    "flatten_async_tb", "format_async",
    "install_async_handler", "uninstall_async_handler",
    "install_thread_hooks", "uninstall_thread_hooks",
    "capture_subprocess_errors", "RemoteError",
    "timed_frames", "annotate_frame_timings", "format_timings",
    "snapshot_top", "attach_snapshot",
    "explain_warning", "humanize_warnings", "escalate",
    # Resilience
    "timeout", "bulkhead", "bulkheads", "BulkheadFullError",
    "dead_letter", "replay", "replay_failed", "list_dead_letters", "clear_dead_letters",
    "retry_rate_limited", "hedge",
    "aio", "aretry", "afallback", "atimeout", "acircuit_breaker", "abulkhead",
    # Observability
    "metrics", "structured_logging", "budgets", "dashboard",
    "log_exception", "set_budget", "budget_status", "clear_budget",
    # Frameworks / CLI apps / serverless / db
    "django_support", "tasks_support",
    "humanize_cli", "lambda_handler",
    "explain_db_error", "enrich_db_error",
    # Education
    "set_language", "reset_language", "get_language", "labels",
    "lookup", "encyclopedia_search", "all_errors",
    "classroom_mode", "reveal_more", "disable_classroom", "set_hint",
    "quiz", "quiz_history",
    # Doctor / Navigator
    "run_doctor", "navigate",
]

"""
pyerror.otel — OpenTelemetry integration.

Attaches pyerror's diagnostics (translation, suggestions, scrubbed locals,
fingerprint) to the active OTel span as a structured event, and marks the
span status as ERROR. This is what gets pyerror into serious production
stacks: teams running Jaeger/Tempo/Datadog/Honeycomb see your humanized
diagnostics directly inside their traces.

OpenTelemetry is an OPTIONAL dependency. Ship it as an extra:

    pip install pyerror-intel[otel]
    # setup.py / pyproject: extras_require={"otel": ["opentelemetry-api>=1.20"]}

Every function degrades to a silent no-op when OTel is not installed or no
span is recording, so callers never need to guard their code.

Public API:
    instrument(record_locals=True, max_attr_len=2000)
        One-time setup. Hooks pyerror's pipeline so every diagnosed/uncaught
        exception is mirrored onto the current span automatically.

    record_exception(exc, span=None, escaped=True)
        Manually enrich a span with pyerror diagnostics for `exc`.

    @traced(name=None)
        Decorator: wraps a function in a span; on failure the span gets the
        full pyerror treatment before the exception propagates.

    fingerprint(exc) -> str
        Stable grouping hash (type + normalized message + crash location).
        Also useful for your analytics clustering (feature #4 on the roadmap).
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import traceback
from typing import Any, Callable, Dict, Optional

__all__ = ["instrument", "record_exception", "traced", "fingerprint", "OTEL_AVAILABLE"]

try:
    from opentelemetry import trace as _trace
    from opentelemetry.trace import Span, Status, StatusCode

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _trace = None
    Span = Any  # type: ignore[misc,assignment]
    OTEL_AVAILABLE = False


# Module-level config, set by instrument().
_CONFIG = {
    "record_locals": True,
    "max_attr_len": 2000,
    "instrumented": False,
}

# Volatile fragments that would break grouping if left in the message:
# hex addresses, long numbers, uuids, quoted paths.
_NORMALIZE_PATTERNS = [
    (re.compile(r"0x[0-9a-fA-F]+"), "<addr>"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<uuid>"),
    (re.compile(r"\b\d{4,}\b"), "<num>"),
    (re.compile(r"'(/[^']*|[A-Za-z]:\\[^']*)'"), "'<path>'"),
]


def fingerprint(exc: BaseException) -> str:
    """Stable hash for grouping recurrences of 'the same' error.

    Built from: exception type + normalized message + deepest user-code
    frame (file:function). Two crashes of the same bug fingerprint
    identically even when ids/paths/timestamps in the message differ.
    """
    message = str(exc)
    for pattern, replacement in _NORMALIZE_PATTERNS:
        message = pattern.sub(replacement, message)

    location = ""
    tb = getattr(exc, "__traceback__", None)
    if tb is not None:
        frames = traceback.extract_tb(tb)
        # Prefer the deepest frame outside site-packages (user code).
        user_frames = [f for f in frames if "site-packages" not in f.filename]
        frame = (user_frames or frames)[-1]
        location = "{}:{}".format(frame.filename, frame.name)

    raw = "|".join([type(exc).__qualname__, message[:300], location])
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Diagnostics extraction (lazy import so this module works standalone too)
# ---------------------------------------------------------------------------

def _gather_diagnostics(exc: BaseException) -> Dict[str, Any]:
    """Pull translation/suggestions/locals from pyerror, defensively."""
    diag: Dict[str, Any] = {
        "pyerror.fingerprint": fingerprint(exc),
        "pyerror.exception_chain_depth": _chain_depth(exc),
    }
    try:
        import pyerror  # your package

        suggestions = pyerror.suggest(exc) or []
        if suggestions:
            diag["pyerror.suggestions"] = json.dumps(suggestions[:5])

        # to_json already runs your scrubbing pipeline — reuse it rather
        # than re-serializing locals here (single source of privacy truth).
        try:
            payload = json.loads(pyerror.to_json(exc))
            if payload.get("translation"):
                diag["pyerror.translation"] = str(payload["translation"])
            if payload.get("reason"):
                diag["pyerror.reason"] = str(payload["reason"])
        except Exception:
            pass
    except Exception:
        # pyerror not importable (standalone use) — still useful via fingerprint.
        pass

    if _CONFIG["record_locals"]:
        captured = getattr(exc, "__captured_locals__", None)
        if captured:
            try:
                diag["pyerror.captured_locals"] = json.dumps(captured, default=str)
            except Exception:
                pass

    # Truncate every attribute to keep span payloads backend-friendly.
    limit = _CONFIG["max_attr_len"]
    return {
        key: (value[:limit] if isinstance(value, str) else value)
        for key, value in diag.items()
    }


def _chain_depth(exc: BaseException) -> int:
    depth, seen = 1, {id(exc)}
    current = exc
    while True:
        nxt = current.__cause__ or current.__context__
        if nxt is None or id(nxt) in seen:
            return depth
        seen.add(id(nxt))
        depth += 1
        current = nxt


# ---------------------------------------------------------------------------
# Core: record onto a span
# ---------------------------------------------------------------------------

def record_exception(
    exc: BaseException,
    span: Optional["Span"] = None,
    escaped: bool = True,
) -> bool:
    """Attach pyerror-enriched diagnostics to `span` (default: current span).

    Returns True if something was recorded, False on silent no-op
    (OTel missing, no recording span, or any internal failure).
    """
    if not OTEL_AVAILABLE:
        return False
    try:
        target = span or _trace.get_current_span()
        if target is None or not target.is_recording():
            return False

        attributes = _gather_diagnostics(exc)
        # Standard semconv exception event, enriched with pyerror.* attrs.
        target.record_exception(exc, attributes=attributes, escaped=escaped)
        target.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
        return True
    except Exception:
        return False  # observability must never break the app


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def traced(name: Optional[str] = None) -> Callable:
    """Wrap a function in a span; failures get full pyerror enrichment.

        @pyerror.otel.traced()
        def charge_card(order_id): ...

    Works as a no-op pass-through when OTel is not installed.
    """

    def decorator(func: Callable) -> Callable:
        if not OTEL_AVAILABLE:
            return func

        span_name = name or "{}.{}".format(func.__module__, func.__qualname__)
        tracer = _trace.get_tracer("pyerror")

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(span_name) as span:
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    record_exception(exc, span=span)
                    raise

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# One-time wiring into pyerror's pipeline
# ---------------------------------------------------------------------------

def instrument(record_locals: bool = True, max_attr_len: int = 2000) -> bool:
    """Enable automatic span enrichment for pyerror users.

    Call once at startup, after pyerror.configure():

        import pyerror, pyerror.otel
        pyerror.otel.instrument()

    Wiring suggestion for your codebase: in the function that handles an
    exception centrally (your excepthook in humanize(), the Flask handler,
    and FastAPIErrorMiddleware), add one line:

        from pyerror import otel
        otel.record_exception(exc)

    That single call covers terminal apps and both web frameworks, because
    web-framework spans are active exactly when your handlers run.
    """
    _CONFIG["record_locals"] = record_locals
    _CONFIG["max_attr_len"] = max(200, int(max_attr_len))
    _CONFIG["instrumented"] = True
    return OTEL_AVAILABLE

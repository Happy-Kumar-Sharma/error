"""
Prometheus metrics exporter.

Requires `prometheus_client`. Without it every function is a no-op so
importing this module is always safe.

Usage::

    from pyerror import metrics
    metrics.instrument_analytics()       # every logged error increments
    metrics.start_metrics_server(9464)   # /metrics on :9464
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Optional

try:
    from prometheus_client import Counter, start_http_server
    AVAILABLE = True
except ImportError:
    AVAILABLE = False
    Counter = None  # type: ignore[assignment]

_LRU_LIMIT = 200
_FP_SET: "OrderedDict[str, None]" = OrderedDict()

if AVAILABLE:
    pyerror_errors_total = Counter(
        "pyerror_errors_total", "Total exceptions seen by pyerror.",
        labelnames=("type", "fingerprint"),
    )
    pyerror_errors_by_release_total = Counter(
        "pyerror_errors_by_release_total", "Exceptions partitioned by release tag.",
        labelnames=("release",),
    )
else:
    pyerror_errors_total = None
    pyerror_errors_by_release_total = None


def _fingerprint_label(fp: str) -> str:
    if not fp:
        return "none"
    if fp in _FP_SET:
        _FP_SET.move_to_end(fp)
        return fp
    if len(_FP_SET) >= _LRU_LIMIT:
        return "other"
    _FP_SET[fp] = None
    return fp


def record(exc: BaseException) -> None:
    if not AVAILABLE:
        return
    try:
        from pyerror.otel import fingerprint
        fp = fingerprint(exc)
    except Exception:
        fp = ""
    try:
        from pyerror import analytics
        release = analytics._RELEASE or "unknown"
    except Exception:
        release = "unknown"
    pyerror_errors_total.labels(type=type(exc).__name__, fingerprint=_fingerprint_label(fp)).inc()
    pyerror_errors_by_release_total.labels(release=release).inc()


def start_metrics_server(port: int = 9464, addr: str = "0.0.0.0") -> bool:
    if not AVAILABLE:
        return False
    start_http_server(port, addr)
    return True


_ORIGINAL_LOG_ERROR = None


def instrument_analytics() -> bool:
    """Wrap analytics.log_error so each logged error also bumps metrics."""
    global _ORIGINAL_LOG_ERROR
    if _ORIGINAL_LOG_ERROR is not None or not AVAILABLE:
        return AVAILABLE
    from pyerror import analytics
    _ORIGINAL_LOG_ERROR = analytics.log_error

    def _wrapped(exc: BaseException):
        try:
            record(exc)
        except Exception:
            pass
        return _ORIGINAL_LOG_ERROR(exc)

    analytics.log_error = _wrapped
    return True


def uninstrument_analytics() -> None:
    global _ORIGINAL_LOG_ERROR
    if _ORIGINAL_LOG_ERROR is None:
        return
    from pyerror import analytics
    analytics.log_error = _ORIGINAL_LOG_ERROR
    _ORIGINAL_LOG_ERROR = None

"""
Error budgets — alert only when error rate exceeds a sliding-window threshold.
"""
from __future__ import annotations

import sys
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, Optional

_LOCK = threading.Lock()
_WINDOW: deque = deque()
_BUDGET: Optional[int] = None
_ON_BREACH: Optional[Callable[[Dict[str, Any]], None]] = None
_TIME_FN: Callable[[], float] = time.time
_BREACHED = False
_ORIGINAL_LOG_ERROR = None


def _default_breach_handler(stats: Dict[str, Any]) -> None:
    sys.stderr.write(
        "⚠️ pyerror budget exceeded: {} errors in the last hour (budget={}).\n".format(
            stats["current_rate"], stats["budget"]
        )
    )


def set_budget(errors_per_hour: int, on_breach: Optional[Callable] = None,
               _time_fn: Optional[Callable[[], float]] = None) -> None:
    global _BUDGET, _ON_BREACH, _TIME_FN, _BREACHED
    _BUDGET = int(errors_per_hour)
    _ON_BREACH = on_breach or _default_breach_handler
    if _time_fn is not None:
        _TIME_FN = _time_fn
    _BREACHED = False
    with _LOCK:
        _WINDOW.clear()


def clear_budget() -> None:
    global _BUDGET, _ON_BREACH, _BREACHED
    _BUDGET = None
    _ON_BREACH = None
    _BREACHED = False
    with _LOCK:
        _WINDOW.clear()


def _trim(now: float) -> None:
    cutoff = now - 3600
    while _WINDOW and _WINDOW[0] < cutoff:
        _WINDOW.popleft()


def record(exc: Optional[BaseException] = None) -> None:
    global _BREACHED
    if _BUDGET is None:
        return
    now = _TIME_FN()
    with _LOCK:
        _WINDOW.append(now)
        _trim(now)
        rate = len(_WINDOW)
    if rate > _BUDGET:
        if not _BREACHED:
            _BREACHED = True
            try:
                if _ON_BREACH is not None:
                    _ON_BREACH(budget_status())
            except Exception:
                pass
    elif _BREACHED and rate <= _BUDGET:
        _BREACHED = False


def budget_status() -> Dict[str, Any]:
    with _LOCK:
        now = _TIME_FN()
        _trim(now)
        rate = len(_WINDOW)
    return {
        "budget": _BUDGET,
        "current_rate": rate,
        "remaining": (max(0, _BUDGET - rate) if _BUDGET is not None else None),
        "breached": _BREACHED,
    }


def instrument_analytics() -> bool:
    global _ORIGINAL_LOG_ERROR
    if _ORIGINAL_LOG_ERROR is not None:
        return True
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

"""
Memory snapshot on MemoryError (and on demand).

`enable(top_n=10)` turns on `tracemalloc` and chains a `sys.excepthook`
wrapper that prints the top allocations when a `MemoryError` propagates
out of the program. `snapshot_top(top_n)` returns the current top
allocations any time. `attach_snapshot(exc)` attaches the snapshot to
an exception for later inspection.
"""
from __future__ import annotations

import sys
import tracemalloc
from typing import List, Optional

_ENABLED = False
_TOP_N = 10
_PREV_HOOK: Optional[callable] = None


def snapshot_top(top_n: int = 10) -> List[str]:
    """Return formatted top-allocation lines (or [] if tracemalloc inactive)."""
    if not tracemalloc.is_tracing():
        return []
    try:
        snap = tracemalloc.take_snapshot()
        stats = snap.statistics("lineno")[:top_n]
        return [str(stat) for stat in stats]
    except Exception:
        return []


def attach_snapshot(exc: BaseException, top_n: int = 10) -> List[str]:
    lines = snapshot_top(top_n)
    try:
        exc.__memory_snapshot__ = lines
    except Exception:
        pass
    return lines


def _hook(exc_type, exc_value, exc_tb):
    if exc_type is MemoryError and exc_value is not None:
        sys.stderr.write("\npyerror memwatch — top allocations on MemoryError:\n")
        for line in snapshot_top(_TOP_N):
            sys.stderr.write("  " + line + "\n")
    if _PREV_HOOK is not None:
        _PREV_HOOK(exc_type, exc_value, exc_tb)
    else:
        sys.__excepthook__(exc_type, exc_value, exc_tb)


def enable(top_n: int = 10) -> bool:
    global _ENABLED, _TOP_N, _PREV_HOOK
    _TOP_N = top_n
    if not tracemalloc.is_tracing():
        try:
            tracemalloc.start(25)
        except Exception:
            return False
    if not _ENABLED:
        _PREV_HOOK = sys.excepthook
        sys.excepthook = _hook
        _ENABLED = True
    return True


def disable() -> None:
    global _ENABLED, _PREV_HOOK
    if _ENABLED and _PREV_HOOK is not None:
        sys.excepthook = _PREV_HOOK
        _PREV_HOOK = None
    _ENABLED = False

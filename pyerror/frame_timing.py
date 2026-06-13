"""
Frame-level timing.

Activate with `enable()` (or the `timed_frames()` context manager) to
record per-frame elapsed time via `sys.setprofile`. Annotate an
exception with `annotate_exception(exc)` to attach
`exc.__frame_timings__` — a list of {function, file, line, elapsed_s}
entries computed at the moment of annotation.

This is intentionally a debugging-only feature: profiling slows code
down noticeably. The context manager turns it on around a narrow block
and back off when the block exits.
"""
from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from typing import List, Optional

_STARTS = threading.local()
_PREV_PROFILER = None
_ENABLED = False


def _profiler(frame, event, arg):
    if not hasattr(_STARTS, "stack"):
        _STARTS.stack = {}
    if event == "call":
        _STARTS.stack[id(frame)] = time.perf_counter()
    elif event == "return":
        _STARTS.stack.pop(id(frame), None)


def enable() -> None:
    global _PREV_PROFILER, _ENABLED
    if _ENABLED:
        return
    _PREV_PROFILER = sys.getprofile()
    sys.setprofile(_profiler)
    try:
        threading.setprofile(_profiler)
    except Exception:
        pass
    _ENABLED = True


def disable() -> None:
    global _PREV_PROFILER, _ENABLED
    if not _ENABLED:
        return
    sys.setprofile(_PREV_PROFILER)
    try:
        threading.setprofile(None)
    except Exception:
        pass
    _PREV_PROFILER = None
    _ENABLED = False


def annotate_exception(exc: BaseException) -> List[dict]:
    """Attach exc.__frame_timings__ with elapsed times for stack frames."""
    timings: List[dict] = []
    now = time.perf_counter()
    starts = getattr(_STARTS, "stack", {}) or {}
    tb = getattr(exc, "__traceback__", None)
    while tb is not None:
        frame = tb.tb_frame
        start = starts.get(id(frame))
        elapsed = (now - start) if start is not None else None
        timings.append({
            "function": frame.f_code.co_name,
            "file": frame.f_code.co_filename,
            "line": tb.tb_lineno,
            "elapsed_s": elapsed,
        })
        tb = tb.tb_next
    try:
        exc.__frame_timings__ = timings
    except Exception:
        pass
    return timings


def format_timings(exc: BaseException) -> str:
    timings = getattr(exc, "__frame_timings__", None) or annotate_exception(exc)
    if not timings:
        return "pyerror frame_timing: no timing data"
    lines = ["Frame timings (longest-running first):"]
    for t in sorted(timings, key=lambda x: x["elapsed_s"] or 0, reverse=True):
        elapsed = "n/a" if t["elapsed_s"] is None else "{:.4f}s".format(t["elapsed_s"])
        lines.append("  {} ({}:{}) — {}".format(t["function"], t["file"], t["line"], elapsed))
    return "\n".join(lines)


@contextmanager
def timed_frames():
    """Enable timing inside this block, annotate any escaping exception."""
    enable()
    try:
        yield
    except BaseException as exc:
        annotate_exception(exc)
        raise
    finally:
        disable()

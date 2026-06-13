"""
Interactive traceback navigator.

Single-line commands (no raw-keyboard input — portable across terminals
and trivially testable by injecting an input function):

    n / next    next frame
    p / prev    previous frame
    l / locals  toggle locals display
    j <N>       jump to frame N
    q / quit    exit
"""
from __future__ import annotations

import linecache
import sys
import traceback
from typing import Any, Callable, List, Optional


def _frames_from_exc(exc: BaseException) -> List[Any]:
    frames = []
    tb = getattr(exc, "__traceback__", None)
    while tb is not None:
        frames.append(tb)
        tb = tb.tb_next
    return frames


def _render_frame(tb, index, total, show_locals=False, output=None) -> None:
    out = output or sys.stdout
    frame = tb.tb_frame
    code = frame.f_code
    lineno = tb.tb_lineno
    filename = code.co_filename
    out.write("\n--- frame {}/{} : {} in {} (line {}) ---\n".format(
        index + 1, total, filename, code.co_name, lineno))
    for offset in (-2, -1, 0, 1, 2):
        ln = lineno + offset
        if ln < 1:
            continue
        line = linecache.getline(filename, ln).rstrip("\n")
        marker = ">>" if offset == 0 else "  "
        out.write("  {} {:5d}  {}\n".format(marker, ln, line))
    if show_locals:
        try:
            from pyerror.formatting import Formatter
            from pyerror import core as _core
            masked = Formatter.mask_locals(
                {k: repr(v) for k, v in frame.f_locals.items()},
                _core._mask_secrets, _core._secret_keys,
            )
        except Exception:
            masked = {k: repr(v) for k, v in frame.f_locals.items()}
        out.write("  locals:\n")
        for k, v in list(masked.items())[:20]:
            out.write("    {} = {}\n".format(k, v))


def navigate(exc: Optional[BaseException] = None,
             input_fn: Callable[[str], str] = input,
             output=None) -> None:
    if exc is None:
        exc = getattr(sys, "last_value", None)
        if exc is None:
            _, exc, _ = sys.exc_info()
    if exc is None:
        (output or sys.stdout).write("pyerror navigate: no exception found.\n")
        return
    frames = _frames_from_exc(exc)
    if not frames:
        (output or sys.stdout).write("pyerror navigate: exception has no traceback.\n")
        return

    index = 0
    show_locals = False
    out = output or sys.stdout
    while True:
        _render_frame(frames[index], index, len(frames), show_locals, out)
        try:
            raw = input_fn("(pyerror) [n/p/l/j N/q] ")
        except (EOFError, KeyboardInterrupt):
            return
        cmd = (raw or "").strip().lower()
        if cmd in ("q", "quit", "exit"):
            return
        if cmd in ("n", "next", ""):
            index = min(index + 1, len(frames) - 1)
        elif cmd in ("p", "prev", "previous"):
            index = max(index - 1, 0)
        elif cmd in ("l", "locals"):
            show_locals = not show_locals
        elif cmd.startswith("j"):
            parts = cmd.split()
            if len(parts) == 2 and parts[1].isdigit():
                n = int(parts[1]) - 1
                if 0 <= n < len(frames):
                    index = n
        else:
            out.write("pyerror navigate: commands are n, p, l, j N, q\n")

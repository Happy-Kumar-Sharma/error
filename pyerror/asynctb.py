"""
Async-aware traceback helpers.

`flatten_async_tb(exc)` strips asyncio / concurrent.futures internal frames.
`format_async(exc)` returns a humanized chain-aware string.
`install(loop=None)` / `uninstall()` swap in an asyncio exception handler
that prints humanized output for tasks whose exceptions escape.
"""
from __future__ import annotations

import asyncio
import os
import traceback
from typing import List, Optional

_NOISY_FRAGMENTS = (
    os.sep + "asyncio" + os.sep,
    "/asyncio/",
    os.sep + "concurrent" + os.sep + "futures" + os.sep,
    "/concurrent/futures/",
    "selectors.py",
)

_previous_handler = None
_installed_loop = None


def _is_noisy(filename: str) -> bool:
    return any(fragment in filename for fragment in _NOISY_FRAGMENTS)


def flatten_async_tb(exc: BaseException) -> List[traceback.FrameSummary]:
    """Return user-relevant frame summaries (asyncio internals removed)."""
    tb = getattr(exc, "__traceback__", None)
    if tb is None:
        return []
    frames = traceback.extract_tb(tb)
    return [f for f in frames if not _is_noisy(f.filename)]


def format_async(exc: BaseException) -> str:
    """Render a humanized, asyncio-noise-free traceback for `exc`."""
    user_frames = flatten_async_tb(exc) or traceback.extract_tb(getattr(exc, "__traceback__", None) or None)
    lines = ["Traceback (async-flattened):"]
    for frame in user_frames or []:
        lines.append('  File "{}", line {}, in {}'.format(frame.filename, frame.lineno, frame.name))
        if frame.line:
            lines.append("    " + frame.line)
    lines.append("{}: {}".format(type(exc).__qualname__, exc))
    chain = exc.__cause__ or exc.__context__
    if chain is not None:
        lines.append("")
        lines.append("Caused by:")
        lines.append(format_async(chain))
    return "\n".join(lines)


def _exception_handler(loop, context):
    exc = context.get("exception")
    msg = context.get("message", "")
    if exc is not None:
        try:
            from pyerror.formatting import Formatter
            from pyerror import core as _core
            import sys
            sys.stderr.write(Formatter.format_cli(
                exc, mode=_core._traceback_mode,
                mask_secrets=_core._mask_secrets,
                secret_keys=_core._secret_keys,
            ))
            return
        except Exception:
            pass
    if _previous_handler is not None:
        _previous_handler(loop, context)
    else:
        loop.default_exception_handler(context)


def install(loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
    """Install humanized exception handler on the loop. Returns success bool."""
    global _previous_handler, _installed_loop
    try:
        loop = loop or asyncio.get_event_loop()
    except RuntimeError:
        return False
    _previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(_exception_handler)
    _installed_loop = loop
    return True


def uninstall() -> None:
    global _previous_handler, _installed_loop
    if _installed_loop is not None:
        try:
            _installed_loop.set_exception_handler(_previous_handler)
        except Exception:
            pass
    _previous_handler = None
    _installed_loop = None

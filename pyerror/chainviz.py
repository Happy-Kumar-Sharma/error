"""Visualizes exception cause/context chains (``raise ... from ...``) as a tree.

Walks ``__cause__`` (explicit) and ``__context__`` (implicit) links from the
outermost exception down to the origin, rendering one line per link with
box-drawing characters. All helpers are cycle-safe and never raise into the
host application.
"""
import os
import sys
from typing import List, Optional, Tuple

# Safety cap so a pathological chain can never produce unbounded output
_MAX_CHAIN_DEPTH = 50
_MAX_MESSAGE_LEN = 120


def get_chain(exc: BaseException) -> List[Tuple[BaseException, str]]:
    """Returns the exception chain as (exception, link_kind) tuples.

    Ordered from the outermost exception ("head") down to the origin.
    link_kind is one of "head", "explicit cause" or "implicit context".
    Cycle-safe; returns an empty list for non-exception input.
    """
    chain = []
    try:
        seen = set()
        current = exc
        kind = "head"
        while isinstance(current, BaseException) and id(current) not in seen:
            if len(chain) >= _MAX_CHAIN_DEPTH:
                break
            seen.add(id(current))
            chain.append((current, kind))
            cause = getattr(current, "__cause__", None)
            context = getattr(current, "__context__", None)
            suppress = getattr(current, "__suppress_context__", False)
            if cause is not None:
                current, kind = cause, "explicit cause"
            elif context is not None and not suppress:
                current, kind = context, "implicit context"
            else:
                break
    except Exception:
        pass
    return chain


def _safe_message(exc: BaseException) -> str:
    """Returns a single-line, scrubbed, length-capped exception message."""
    try:
        msg = str(exc)
    except Exception:
        return "<unprintable>"
    msg = msg.replace("\r", " ").replace("\n", " ")
    if len(msg) > _MAX_MESSAGE_LEN:
        msg = msg[: _MAX_MESSAGE_LEN - 3] + "..."
    try:
        from pyerror.formatting import Formatter
        msg = Formatter.scrub_text(msg)
    except Exception:
        pass
    return msg


def _location(exc: BaseException) -> Optional[str]:
    """Returns 'file:line' for the deepest traceback frame of exc, if any."""
    try:
        tb = getattr(exc, "__traceback__", None)
        last = None
        guard = 0
        while tb is not None and guard < 1000:
            last = tb
            tb = tb.tb_next
            guard += 1
        if last is not None:
            filename = os.path.basename(last.tb_frame.f_code.co_filename)
            return "{}:{}".format(filename, last.tb_lineno)
        # SyntaxError carries its own location even without a traceback
        if isinstance(exc, SyntaxError) and exc.filename and exc.lineno:
            return "{}:{}".format(os.path.basename(exc.filename), exc.lineno)
    except Exception:
        pass
    return None


def format_chain(exc: BaseException, unicode_ok: bool = True) -> str:
    """Renders the cause/context chain of exc as a tree string.

    The outermost exception sits at the top; the deepest origin is marked
    at the bottom. Never raises.
    """
    try:
        chain = get_chain(exc)
        if not chain:
            return _safe_message(exc) if isinstance(exc, BaseException) else str(exc)

        branch = "└─ " if unicode_ok else "`- "       # └─
        pipe = "│" if unicode_ok else "|"                  # │
        origin_mark = "⟵ origin" if unicode_ok else "<- origin"  # ⟵ origin

        lines = []
        for i, (link_exc, kind) in enumerate(chain):
            part = type(link_exc).__name__
            msg = _safe_message(link_exc)
            if msg:
                part += ": {}".format(msg)
            if kind != "head":
                part += " ({})".format(kind)
            loc = _location(link_exc)
            if loc:
                part += " @ {}".format(loc)
            if i == len(chain) - 1 and len(chain) > 1:
                part += " {}".format(origin_mark)

            if i == 0:
                lines.append(part)
            else:
                indent = "   " * (i - 1)
                lines.append(indent + pipe)
                lines.append(indent + branch + part)
        return "\n".join(lines)
    except Exception:
        try:
            return "{}: {}".format(type(exc).__name__, exc)
        except Exception:
            return "<unprintable exception chain>"


def show_chain(exc: BaseException) -> None:
    """Prints the exception chain tree to stderr (rich panel if available)."""
    try:
        text = format_chain(exc)
        try:
            from rich.console import Console
            from rich.panel import Panel
            console = Console(stderr=True)
            console.print(Panel(text, title="⛓️ Exception Chain", title_align="left", border_style="magenta", padding=(1, 2)))
        except Exception:
            sys.stderr.write(text + "\n")
    except Exception:
        pass

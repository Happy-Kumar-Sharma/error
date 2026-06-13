"""
pyerror.fixdiff — concrete fix suggestions rendered as unified diffs.

Where pyerror.fuzzy answers "did you mean ...?", this module goes one step
further: it reads the actual offending source line from the crash site,
applies the most confident rename (NameError / AttributeError / KeyError
typos), and emits a ready-to-apply unified diff:

    --- a/app.py:42
    +++ b/app.py:42
    @@ -1 +1 @@
    -    total = user_cont + items
    +    total = user_count + items

Zero dependencies (stdlib difflib + linecache). Reuses
pyerror.fuzzy.closest_matches as the single source of "what is similar
enough" truth, so fixdiff and fuzzy never disagree about the best candidate.

Design notes:
- We only ever propose a fix when (a) the source line is readable (REPL /
  exec'd code has no file to read), (b) a confident fuzzy match exists, and
  (c) the broken token actually appears on the crash line. Anything less
  returns None — a wrong diff is worse than no diff.
- Like every diagnostics helper in this package, the public functions are
  wrapped defensively and NEVER raise into the host application.
"""

from __future__ import annotations

import builtins
import difflib
import linecache
import re
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

from pyerror.fuzzy import closest_matches

__all__ = ["suggest_fix", "format_fix", "FixSuggestion"]

# Message fallbacks for Python < 3.10 where exc.name / exc.obj are absent.
_NAME_ERROR_RE = re.compile(r"name '([^']+)' is not defined")
_ATTR_ERROR_RE = re.compile(r"(?:object|module) '?([^']*)'? has no attribute '([^']+)'")


@dataclass
class FixSuggestion:
    """A single-line corrective edit, expressed both as text and as a diff."""

    original_line: str
    fixed_line: str
    diff: str
    file: str
    lineno: int
    description: str

    def __str__(self) -> str:
        return "{}\n{}".format(self.description, self.diff)


# ---------------------------------------------------------------------------
# Crash-site helpers
# ---------------------------------------------------------------------------

def _deepest_tb(exc: BaseException):
    """Return the deepest traceback object (the actual crash site)."""
    tb = getattr(exc, "__traceback__", None)
    if tb is None:
        return None
    while tb.tb_next is not None:
        tb = tb.tb_next
    return tb


def _source_line(tb) -> Tuple[Optional[str], str, int]:
    """Read the offending source line. Returns (line_or_None, file, lineno).

    `<stdin>`, `<string>` and friends are unreadable on purpose — we cannot
    diff what we cannot see.
    """
    frame = tb.tb_frame
    filename = frame.f_code.co_filename
    lineno = tb.tb_lineno
    if not filename or filename.startswith("<"):
        return None, filename, lineno
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno)
    if not line.strip():
        return None, filename, lineno
    return line.rstrip("\r\n"), filename, lineno


def _names_in_scope(tb) -> List[str]:
    frame = tb.tb_frame
    names: List[str] = []
    names.extend(frame.f_locals.keys())
    names.extend(frame.f_globals.keys())
    names.extend(dir(builtins))
    return names


# ---------------------------------------------------------------------------
# Per-exception-type rewriters: return (fixed_line, description) or None
# ---------------------------------------------------------------------------

def _fix_name_error(exc: NameError, tb, line: str) -> Optional[Tuple[str, str]]:
    missing = getattr(exc, "name", None)
    if not missing:
        match = _NAME_ERROR_RE.search(str(exc))
        missing = match.group(1) if match else None
    if not missing:
        return None

    matches = closest_matches(missing, _names_in_scope(tb), n=1)
    if not matches:
        return None
    replacement = matches[0]

    pattern = re.compile(r"\b{}\b".format(re.escape(missing)))
    if not pattern.search(line):
        return None  # name not visible on the crash line (e.g. comprehension)
    fixed = pattern.sub(replacement, line)
    description = "Replace undefined name `{}` with `{}`".format(missing, replacement)
    return fixed, description


def _fix_attribute_error(exc: AttributeError, tb, line: str) -> Optional[Tuple[str, str]]:
    missing = getattr(exc, "name", None)
    obj = getattr(exc, "obj", None)
    if not missing:
        match = _ATTR_ERROR_RE.search(str(exc))
        missing = match.group(2) if match else None
    if not missing:
        return None

    candidates: List[str] = []
    if obj is not None:
        try:
            candidates = dir(obj)
        except Exception:
            candidates = []
    if not candidates:
        # Pre-3.10 fallback: find a local object that lacks this attribute
        # but has a close sibling (same heuristic as pyerror.fuzzy).
        for value in list(tb.tb_frame.f_locals.values())[:50]:
            try:
                attrs = dir(value)
            except Exception:
                continue
            if missing not in attrs and closest_matches(missing, attrs, n=1):
                candidates = attrs
                break

    matches = closest_matches(missing, candidates, n=1)
    if not matches:
        return None
    replacement = matches[0]

    pattern = re.compile(r"(?<=\.){}\b".format(re.escape(missing)))
    if not pattern.search(line):
        return None
    fixed = pattern.sub(replacement, line)
    description = "Replace attribute `.{}` with `.{}`".format(missing, replacement)
    return fixed, description


def _fix_key_error(exc: KeyError, tb, line: str) -> Optional[Tuple[str, str]]:
    if not exc.args or not isinstance(exc.args[0], str):
        return None
    missing = exc.args[0]

    replacement: Optional[str] = None
    for value in list(tb.tb_frame.f_locals.values())[:50]:
        keys: List[str] = []
        try:
            if hasattr(value, "keys"):
                keys = [k for k in value.keys() if isinstance(k, str)]
        except Exception:
            continue
        if not keys or missing in keys:
            continue
        matches = closest_matches(missing, keys, n=1)
        if matches:
            replacement = matches[0]
            break
    if replacement is None:
        return None

    # Only rewrite the quoted key literal, preserving the quote style used.
    pattern = re.compile(r"(['\"]){}\1".format(re.escape(missing)))
    if not pattern.search(line):
        return None
    fixed = pattern.sub(lambda m: m.group(1) + replacement + m.group(1), line)
    description = "Replace missing key `'{}'` with `'{}'`".format(missing, replacement)
    return fixed, description


_REWRITERS: Tuple[Tuple[type, Callable[..., Optional[Tuple[str, str]]]], ...] = (
    (NameError, _fix_name_error),
    (AttributeError, _fix_attribute_error),
    (KeyError, _fix_key_error),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def suggest_fix(exc: BaseException) -> Optional[FixSuggestion]:
    """Build a unified-diff fix suggestion for `exc`, or None.

    Supports NameError, AttributeError and KeyError typos. Returns None when
    the source is unreadable, the token is not on the crash line, or no
    confident fuzzy match exists. Never raises.
    """
    try:
        rewriter = None
        for exc_type, candidate in _REWRITERS:
            if isinstance(exc, exc_type):
                rewriter = candidate
                break
        if rewriter is None:
            return None

        tb = _deepest_tb(exc)
        if tb is None:
            return None
        line, filename, lineno = _source_line(tb)
        if line is None:
            return None

        result = rewriter(exc, tb, line)
        if result is None:
            return None
        fixed, description = result
        if fixed == line:
            return None

        diff = "\n".join(difflib.unified_diff(
            [line],
            [fixed],
            fromfile="a/{}:{}".format(filename, lineno),
            tofile="b/{}:{}".format(filename, lineno),
            lineterm="",
        ))
        return FixSuggestion(
            original_line=line,
            fixed_line=fixed,
            diff=diff,
            file=filename,
            lineno=lineno,
            description=description,
        )
    except Exception:
        # Diagnostics must never crash the program they are diagnosing.
        return None


def format_fix(exc: BaseException) -> str:
    """Human-readable rendering of suggest_fix(); empty string when no fix."""
    try:
        fix = suggest_fix(exc)
        if fix is None:
            return ""
        return str(fix)
    except Exception:
        return ""

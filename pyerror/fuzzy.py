"""
pyerror.fuzzy — "Did you mean?" suggestions via fuzzy name matching.

Zero dependencies (stdlib `difflib` only). Works on Python 3.7+.

Public API:
    suggest_names(exc) -> list[str]
        Returns human-readable "Did you mean ...?" suggestions for
        NameError, AttributeError, KeyError, ImportError/ModuleNotFoundError.

Integration point: call this inside your existing `pyerror.suggest()` /
diagnostics pipeline and prepend the results to the suggestion list —
fuzzy matches are almost always the most actionable suggestion.

Design notes:
- On Python 3.10/3.11+ exceptions carry `.name` / `.obj` attributes; we use
  them when present and fall back to regex-parsing the message on 3.7-3.9,
  so behaviour is consistent across all supported versions.
- For NameError/KeyError we need the crash frame to know what names were in
  scope. We walk `exc.__traceback__` to its deepest frame (the crash site).
- Everything is wrapped defensively: a suggestion engine must never raise.
"""

from __future__ import annotations

import builtins
import difflib
import re
from typing import Any, Dict, List, Optional, Sequence

__all__ = ["suggest_names", "closest_matches"]

# Tunables — exposed so pyerror.configure() can override them later.
MAX_SUGGESTIONS = 3
CUTOFF = 0.6           # difflib similarity threshold (0..1)
MAX_CANDIDATES = 5000  # safety cap for pathological scopes

_NAME_ERROR_RE = re.compile(r"name '([^']+)' is not defined")
_ATTR_ERROR_RE = re.compile(r"(?:object|module) '?([^']*)'? has no attribute '([^']+)'")
_IMPORT_ERROR_RE = re.compile(r"No module named '([^']+)'")


def closest_matches(
    target: str,
    candidates: Sequence[str],
    n: int = MAX_SUGGESTIONS,
    cutoff: float = CUTOFF,
) -> List[str]:
    """Rank `candidates` by similarity to `target`.

    Combines difflib ratio with a small bonus for case-insensitive equality
    and prefix matches, so `userId` -> `user_id` and `Pd` -> `pd` rank well.
    """
    if not target or not candidates:
        return []

    pool = list(dict.fromkeys(candidates))[:MAX_CANDIDATES]  # dedupe, cap
    scored = []
    target_lower = target.lower()
    for cand in pool:
        if not isinstance(cand, str) or cand == target:
            continue
        # Skip dunder noise unless the target itself looks dunder-ish.
        if cand.startswith("__") and not target.startswith("_"):
            continue
        ratio = difflib.SequenceMatcher(None, target, cand).ratio()
        if cand.lower() == target_lower:
            ratio = 1.0  # pure case mismatch — almost certainly the fix
        elif cand.lower().startswith(target_lower) or target_lower.startswith(cand.lower()):
            ratio += 0.1
        if ratio >= cutoff:
            scored.append((ratio, cand))

    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [cand for _, cand in scored[:n]]


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------

def _crash_frame(exc: BaseException):
    """Return the deepest frame of the exception's traceback (crash site)."""
    tb = getattr(exc, "__traceback__", None)
    if tb is None:
        return None
    while tb.tb_next is not None:
        tb = tb.tb_next
    return tb.tb_frame


def _names_in_scope(exc: BaseException) -> List[str]:
    frame = _crash_frame(exc)
    names: List[str] = []
    if frame is not None:
        names.extend(frame.f_locals.keys())
        names.extend(frame.f_globals.keys())
    names.extend(dir(builtins))
    return names


# ---------------------------------------------------------------------------
# Per-exception-type handlers
# ---------------------------------------------------------------------------

def _suggest_for_name_error(exc: NameError) -> List[str]:
    # Python 3.10+: exc.name; older: parse the message.
    missing = getattr(exc, "name", None)
    if not missing:
        match = _NAME_ERROR_RE.search(str(exc))
        missing = match.group(1) if match else None
    if not missing:
        return []

    matches = closest_matches(missing, _names_in_scope(exc))
    return [
        "Did you mean `{}` instead of `{}`?".format(m, missing) for m in matches
    ]


def _suggest_for_attribute_error(exc: AttributeError) -> List[str]:
    missing = getattr(exc, "name", None)
    obj = getattr(exc, "obj", None)

    if not missing:
        match = _ATTR_ERROR_RE.search(str(exc))
        missing = match.group(2) if match else None
    if not missing:
        return []

    candidates: List[str] = []
    if obj is not None:
        try:
            candidates = dir(obj)
        except Exception:
            candidates = []
    if not candidates:
        # Pre-3.10 fallback: scan crash-frame locals for an object that is
        # missing this attribute and use the first plausible one.
        frame = _crash_frame(exc)
        if frame is not None:
            for value in list(frame.f_locals.values())[:50]:
                try:
                    attrs = dir(value)
                except Exception:
                    continue
                if missing not in attrs and closest_matches(missing, attrs, n=1):
                    candidates = attrs
                    break

    matches = closest_matches(missing, candidates)
    suggestions = [
        "Did you mean `.{}` instead of `.{}`?".format(m, missing) for m in matches
    ]
    type_name = type(obj).__name__ if obj is not None else None
    if not suggestions and type_name:
        suggestions.append(
            "`{}` objects have no attribute `{}` — run `dir(obj)` to list "
            "what is available.".format(type_name, missing)
        )
    return suggestions


def _suggest_for_key_error(exc: KeyError) -> List[str]:
    if not exc.args or not isinstance(exc.args[0], str):
        return []
    missing = exc.args[0]

    frame = _crash_frame(exc)
    if frame is None:
        return []

    suggestions: List[str] = []
    scope: Dict[str, Any] = dict(frame.f_locals)
    for var_name, value in list(scope.items())[:50]:
        keys: List[str] = []
        try:
            if isinstance(value, dict):
                keys = [k for k in value.keys() if isinstance(k, str)]
            elif hasattr(value, "keys"):  # Mapping-like (e.g. os.environ)
                keys = [k for k in value.keys() if isinstance(k, str)]
        except Exception:
            continue
        if not keys or missing in keys:
            continue
        for match in closest_matches(missing, keys):
            suggestions.append(
                "Did you mean key `'{}'` (found in `{}`) instead of `'{}'`?".format(
                    match, var_name, missing
                )
            )
        if suggestions:
            break  # first matching mapping is almost always the right one

    if not suggestions:
        suggestions_hint = (
            "Key `'{}'` was not found. Use `.get('{}')` for a safe default, "
            "or print the dict's `.keys()` to inspect what exists.".format(
                missing, missing
            )
        )
        suggestions.append(suggestions_hint)
    return suggestions[:MAX_SUGGESTIONS]


def _suggest_for_import_error(exc: ImportError) -> List[str]:
    missing = getattr(exc, "name", None)
    if not missing:
        match = _IMPORT_ERROR_RE.search(str(exc))
        missing = match.group(1) if match else None
    if not missing:
        return []

    top_level = missing.split(".")[0]

    # Common PyPI install-name != import-name traps. Cheap, high-value.
    known_aliases = {
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "sklearn": "scikit-learn",
        "yaml": "PyYAML",
        "bs4": "beautifulsoup4",
        "dotenv": "python-dotenv",
        "dateutil": "python-dateutil",
        "Crypto": "pycryptodome",
        "serial": "pyserial",
        "fitz": "PyMuPDF",
    }
    suggestions: List[str] = []
    if top_level in known_aliases:
        suggestions.append(
            "`{}` is installed via `pip install {}` (the import name differs "
            "from the package name).".format(top_level, known_aliases[top_level])
        )

    # Fuzzy match against modules importable right now (catches typos like
    # `nunpy` -> `numpy`). pkgutil scan is lazy and capped for speed.
    try:
        import pkgutil

        installed = []
        for i, module in enumerate(pkgutil.iter_modules()):
            installed.append(module.name)
            if i > MAX_CANDIDATES:
                break
        for match in closest_matches(top_level, installed, n=2, cutoff=0.75):
            suggestions.append(
                "Did you mean `import {}`? (it is installed)".format(match)
            )
    except Exception:
        pass

    return suggestions[:MAX_SUGGESTIONS]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_HANDLERS = (
    (NameError, _suggest_for_name_error),
    (AttributeError, _suggest_for_attribute_error),
    (KeyError, _suggest_for_key_error),
    (ImportError, _suggest_for_import_error),  # also covers ModuleNotFoundError
)


def suggest_names(exc: BaseException) -> List[str]:
    """Return 'Did you mean ...?' suggestions for a caught exception.

    Never raises; returns [] when no confident match exists.
    """
    try:
        for exc_type, handler in _HANDLERS:
            if isinstance(exc, exc_type):
                return handler(exc)  # type: ignore[arg-type]
    except Exception:
        # A diagnostics helper must never crash the program it is diagnosing.
        return []
    return []

"""
Classroom mode — instructor-configurable gradual hints.

`classroom_mode(level=1)` wraps SuggestionEngine.get_details so each
exception gets a leveled view:

- level 1: translation + a single leading-question hint (the "example"
  field is hidden).
- level 2: translation + why + first two suggestions.
- level 3: full details including the example.

The wrapper is composable with `pyerror.i18n.set_language` — disable
both to restore the original behavior.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from pyerror.suggestions import SuggestionEngine

_LEVEL = 1
_ORIGINAL: Optional[Callable] = None
_LAST_EXC_ID: Optional[int] = None
_OVERRIDES: Dict[str, Dict[int, str]] = {}

_QUESTION_TEMPLATES = {
    "KeyError": "What happens when the key you typed doesn't actually exist in the dictionary?",
    "NameError": "Where do you think this name was supposed to come from — an import, an assignment, or a function parameter?",
    "TypeError": "Are the two values on this line really the same type — and should they be?",
    "ValueError": "What constraints does the function expect for this argument's value?",
    "IndexError": "How big is the list compared to the index you asked for?",
    "AttributeError": "Is this really the object you expect — and does it have that name in `dir()`?",
    "ZeroDivisionError": "What does the divisor equal at the moment of the crash?",
    "ImportError": "Is this package installed in the active Python environment?",
    "FileNotFoundError": "Where exactly is the working directory when this script runs?",
    "IndentationError": "Are spaces and tabs being mixed on the indented lines?",
}


def _gentle_hint(name: str) -> str:
    return _QUESTION_TEMPLATES.get(name,
        "Read the error message slowly: what value or name does Python report as unexpected, and where in your code is it created?")


def set_hint(exc_type_name: str, level: int, text: str) -> None:
    _OVERRIDES.setdefault(exc_type_name, {})[int(level)] = text


def _apply(details: Dict[str, Any]) -> Dict[str, Any]:
    name = details.get("name", "")
    out = dict(details)
    suggestions = list(details.get("suggestions") or [])
    override = _OVERRIDES.get(name, {}).get(_LEVEL)
    if _LEVEL <= 1:
        hint = override or _gentle_hint(name)
        out["suggestions"] = [hint]
        out["why"] = ""
        out["example"] = None
    elif _LEVEL == 2:
        out["suggestions"] = ([override] if override else []) + suggestions[:2]
        out["example"] = None
    else:
        if override:
            out["suggestions"] = [override] + suggestions
    return out


def classroom_mode(level: int = 1, unlock: str = "manual") -> int:
    """Enable classroom mode. Idempotent — call again to change the level."""
    global _LEVEL, _ORIGINAL
    _LEVEL = max(1, min(3, int(level)))
    if _ORIGINAL is None:
        _ORIGINAL = SuggestionEngine.get_details
    original = _ORIGINAL

    def _wrapped(exc):
        global _LAST_EXC_ID
        _LAST_EXC_ID = id(exc)
        return _apply(original(exc))

    SuggestionEngine.get_details = staticmethod(_wrapped)
    return _LEVEL


def reveal_more() -> int:
    global _LEVEL
    _LEVEL = min(3, _LEVEL + 1)
    return _LEVEL


def disable_classroom() -> None:
    global _LEVEL, _ORIGINAL, _LAST_EXC_ID
    _LEVEL = 1
    _LAST_EXC_ID = None
    if _ORIGINAL is not None:
        SuggestionEngine.get_details = staticmethod(_ORIGINAL)
        _ORIGINAL = None

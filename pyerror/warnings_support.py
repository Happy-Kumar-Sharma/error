"""
pyerror.explain_warning() + warning humanization and escalation.
"""
from __future__ import annotations

import warnings
from typing import Any, Dict, Iterable, Optional, Type, Union

_CATALOG: Dict[str, Dict[str, Any]] = {
    "DeprecationWarning": {
        "translation": "You're using something that's being phased out.",
        "why": "The Python developers (or a library author) have marked this API as deprecated. It still works for now but will be removed in a future version.",
        "suggestions": [
            "Check the warning location for the deprecated call.",
            "Look at the library's CHANGELOG for the recommended replacement.",
            "Plan to migrate before the next major version of the library.",
        ],
    },
    "PendingDeprecationWarning": {
        "translation": "This API will be deprecated soon — start migrating now.",
        "why": "The maintainer marked this for future deprecation. It still works today.",
        "suggestions": [
            "Read the library changelog for the recommended replacement.",
            "Update your code to use the new API while you have time.",
        ],
    },
    "FutureWarning": {
        "translation": "The behavior of this code will change in a future release.",
        "why": "A future version of Python or this library will behave differently here.",
        "suggestions": [
            "Read the linked migration notes.",
            "Pin the relevant library version if you cannot migrate immediately.",
        ],
    },
    "RuntimeWarning": {
        "translation": "Suspicious behavior was detected at runtime.",
        "why": "Python ran your code, but something looked off — divide-by-zero in numpy, await never awaited, etc.",
        "suggestions": [
            "Check the warning location for unsafe arithmetic or coroutine misuse.",
            "Enable -W error::RuntimeWarning to convert these into raised exceptions for debugging.",
        ],
    },
    "UserWarning": {
        "translation": "A library issued a generic warning.",
        "why": "A library called warnings.warn() to flag something noteworthy.",
        "suggestions": [
            "Read the warning text — library authors usually explain the action to take.",
            "If safe to silence, use warnings.filterwarnings('ignore', ...) at the specific category.",
        ],
    },
    "ResourceWarning": {
        "translation": "A resource (file, socket, subprocess) was not closed cleanly.",
        "why": "Python collected an object that still held an open resource.",
        "suggestions": [
            "Use `with` statements / context managers for files, sockets, and subprocesses.",
            "Make sure async resources have their `close()` / `aclose()` awaited.",
        ],
    },
    "SyntaxWarning": {
        "translation": "Python compiled the code but spotted suspicious syntax.",
        "why": "A construct like `is` against a literal almost certainly isn't what you meant.",
        "suggestions": [
            "Read the warning location — fix the suspicious comparison or expression.",
        ],
    },
    "BytesWarning": {
        "translation": "Bytes/str were compared in a way that's almost certainly a bug.",
        "why": "Implicit comparison between bytes and str usually points to a forgotten decode/encode.",
        "suggestions": [
            "Decode bytes to str (or vice versa) before comparison.",
        ],
    },
}

_DEFAULT = {
    "translation": "A warning was emitted.",
    "why": "Python or a library emitted a warning during execution.",
    "suggestions": [
        "Read the warning text and the source location it points to.",
        "If the warning is expected, silence it with warnings.filterwarnings().",
    ],
}

_PREV_SHOWWARNING = None


def explain_warning(warning_or_category: Any, message: str = "") -> Dict[str, Any]:
    name: Optional[str] = None
    if isinstance(warning_or_category, type) and issubclass(warning_or_category, Warning):
        name = warning_or_category.__name__
    elif isinstance(warning_or_category, Warning):
        name = type(warning_or_category).__name__
        if not message:
            message = str(warning_or_category)
    elif isinstance(warning_or_category, str):
        name = warning_or_category
    entry = _CATALOG.get(name or "", _DEFAULT)
    return {
        "name": name or "Warning",
        "message": message,
        "translation": entry["translation"],
        "why": entry["why"],
        "suggestions": list(entry["suggestions"]),
    }


def _showwarning(message, category, filename, lineno, file=None, line=None):
    import sys
    details = explain_warning(category, str(message))
    stream = file or sys.stderr
    stream.write("\npyerror warning — {}\n".format(details["name"]))
    stream.write("  {}\n".format(details["translation"]))
    stream.write("  At: {}:{}\n".format(filename, lineno))
    stream.write("  Message: {}\n".format(message))
    for s in details["suggestions"][:2]:
        stream.write("  - {}\n".format(s))


def humanize_warnings(enable: bool = True) -> None:
    global _PREV_SHOWWARNING
    if enable:
        if _PREV_SHOWWARNING is None:
            _PREV_SHOWWARNING = warnings.showwarning
        warnings.showwarning = _showwarning
    else:
        if _PREV_SHOWWARNING is not None:
            warnings.showwarning = _PREV_SHOWWARNING
            _PREV_SHOWWARNING = None


def escalate(categories: Union[Type[Warning], Iterable[Type[Warning]]]) -> None:
    """Turn the given warning categories into errors via filterwarnings."""
    cats = (categories,) if isinstance(categories, type) else tuple(categories)
    for cat in cats:
        warnings.filterwarnings("error", category=cat)

"""
Error encyclopedia — `pyerror.lookup("ZeroDivisionError")` without an
active exception. Also generates a markdown doc from the same data.
"""
from __future__ import annotations

import difflib
from typing import Any, Dict, List, Optional


def _build_synthetic_exception(name: str) -> Optional[BaseException]:
    table = {
        "KeyError": lambda: KeyError("example_key"),
        "ZeroDivisionError": lambda: ZeroDivisionError("division by zero"),
        "TypeError": lambda: TypeError("unsupported operand type(s) for +: 'int' and 'str'"),
        "ValueError": lambda: ValueError("invalid literal for int() with base 10: 'abc'"),
        "IndexError": lambda: IndexError("list index out of range"),
        "AttributeError": lambda: AttributeError("'NoneType' object has no attribute 'x'"),
        "NameError": lambda: NameError("name 'undefined' is not defined"),
        "ImportError": lambda: ImportError("No module named 'unknown_module'"),
        "ModuleNotFoundError": lambda: ModuleNotFoundError("No module named 'unknown_module'"),
        "FileNotFoundError": lambda: FileNotFoundError(2, "No such file or directory", "missing.txt"),
        "FileExistsError": lambda: FileExistsError(17, "File exists", "duplicate.txt"),
        "PermissionError": lambda: PermissionError(13, "Permission denied", "secret"),
        "IndentationError": lambda: IndentationError("unexpected indent"),
        "TabError": lambda: TabError("inconsistent use of tabs and spaces"),
        "UnboundLocalError": lambda: UnboundLocalError("local variable 'x' referenced before assignment"),
        "RecursionError": lambda: RecursionError("maximum recursion depth exceeded"),
        "UnicodeDecodeError": lambda: UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
        "MemoryError": lambda: MemoryError(),
        "OverflowError": lambda: OverflowError("integer overflow"),
        "AssertionError": lambda: AssertionError("expected positive value"),
        "NotImplementedError": lambda: NotImplementedError("subclasses must implement"),
        "RuntimeError": lambda: RuntimeError("dictionary changed size during iteration"),
        "ConnectionRefusedError": lambda: ConnectionRefusedError(111, "Connection refused"),
        "TimeoutError": lambda: TimeoutError(110, "Connection timed out"),
        "StopIteration": lambda: StopIteration(),
        "KeyboardInterrupt": lambda: KeyboardInterrupt(),
        "OSError": lambda: OSError(1, "Operation not permitted"),
        "ArithmeticError": lambda: ArithmeticError("arithmetic problem"),
        "SyntaxError": lambda: SyntaxError("invalid syntax"),
    }
    builder = table.get(name)
    if builder is None:
        return None
    try:
        return builder()
    except Exception:
        return None


_CURATED: Dict[str, Dict[str, Any]] = {
    "KeyError": {
        "common_causes": ["Typo in the key", "Key removed elsewhere by mistake", "Reading config that's missing the entry"],
        "see_also": ["AttributeError", "IndexError"],
    },
    "ZeroDivisionError": {
        "common_causes": ["Dividing by user input without validation", "Forgot to short-circuit when a count is 0"],
        "see_also": ["ArithmeticError"],
    },
    "TypeError": {
        "common_causes": ["Mixing strings and numbers", "Calling a non-callable", "Wrong number of arguments"],
        "see_also": ["ValueError", "AttributeError"],
    },
    "ImportError": {
        "common_causes": ["Module not installed", "Install-name differs from import-name (e.g. PIL/Pillow)", "Virtualenv not activated"],
        "see_also": ["ModuleNotFoundError"],
    },
    "RecursionError": {
        "common_causes": ["Missing base case in recursion", "Mutually-recursive functions"],
        "see_also": ["RuntimeError"],
    },
}


def all_errors() -> List[str]:
    return sorted(set(list(_build_synthetic_exception.__func__ if hasattr(_build_synthetic_exception, "__func__") else _build_synthetic_exception)) if False else _SUPPORTED)


_SUPPORTED: List[str] = []


def _populate_supported():
    if _SUPPORTED:
        return _SUPPORTED
    names = [
        "KeyError", "ZeroDivisionError", "TypeError", "ValueError", "IndexError",
        "AttributeError", "NameError", "ImportError", "ModuleNotFoundError",
        "FileNotFoundError", "FileExistsError", "PermissionError",
        "IndentationError", "TabError", "UnboundLocalError", "RecursionError",
        "UnicodeDecodeError", "MemoryError", "OverflowError", "AssertionError",
        "NotImplementedError", "RuntimeError", "ConnectionRefusedError",
        "TimeoutError", "StopIteration", "KeyboardInterrupt", "OSError",
        "ArithmeticError", "SyntaxError",
    ]
    _SUPPORTED.extend(sorted(names))
    return _SUPPORTED


def all_errors() -> List[str]:  # noqa: F811
    return list(_populate_supported())


def _lookup_one(name: str) -> Optional[Dict[str, Any]]:
    synthetic = _build_synthetic_exception(name)
    if synthetic is None:
        return None
    try:
        from pyerror.suggestions import SuggestionEngine
        details = SuggestionEngine.get_details(synthetic)
    except Exception:
        return None
    entry = dict(details)
    entry["name"] = name
    curated = _CURATED.get(name)
    if curated:
        entry.update(curated)
    return entry


def lookup(name: str) -> Optional[Dict[str, Any]]:
    """Look up an exception by name (case-insensitive). Returns None if unknown."""
    if not name:
        return None
    target = name.strip()
    for known in _populate_supported():
        if known.lower() == target.lower():
            return _lookup_one(known)
    return None


def search(term: str) -> List[str]:
    term = (term or "").lower()
    matches = [n for n in _populate_supported() if term in n.lower()]
    if matches:
        return matches
    return difflib.get_close_matches(term, _populate_supported(), n=5, cutoff=0.4)


def generate_markdown(path: Optional[str] = None) -> str:
    lines = ["# pyerror error encyclopedia", ""]
    for name in _populate_supported():
        entry = _lookup_one(name)
        if entry is None:
            continue
        lines.append("## {}".format(name))
        lines.append("")
        lines.append("**" + (entry.get("translation") or "") + "**")
        lines.append("")
        if entry.get("why"):
            lines.append("Why: " + entry["why"])
            lines.append("")
        if entry.get("common_causes"):
            lines.append("Common causes:")
            for c in entry["common_causes"]:
                lines.append("  - " + c)
            lines.append("")
        if entry.get("suggestions"):
            lines.append("Suggestions:")
            for s in entry["suggestions"]:
                lines.append("  - " + s)
            lines.append("")
        if entry.get("see_also"):
            lines.append("See also: " + ", ".join(entry["see_also"]))
            lines.append("")
    text = "\n".join(lines)
    if path:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        except Exception:
            pass
    return text

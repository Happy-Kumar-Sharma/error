"""
pyerror pytest plugin.

Enable with::

    pytest -p pyerror.pytest_plugin

…or rely on the setup.py `pytest11` entry point which auto-registers it.

When a test fails, the plugin appends a humanized section to the failure
report containing the translation, why-line, and top suggestions from
pyerror's SuggestionEngine. Captured locals from the crash frame are
masked using pyerror's privacy pipeline.
"""
from __future__ import annotations


def pytest_addoption(parser):
    group = parser.getgroup("pyerror")
    group.addoption(
        "--no-pyerror",
        action="store_true",
        default=False,
        help="Disable pyerror's humanized failure section.",
    )


def pytest_exception_interact(node, call, report):
    if getattr(report, "_pyerror_handled", False):
        return
    config = getattr(node, "config", None)
    if config is not None and config.getoption("--no-pyerror", default=False):
        return
    exc_info = getattr(call, "excinfo", None)
    if exc_info is None:
        return
    exc = exc_info.value
    try:
        from pyerror.suggestions import SuggestionEngine
        from pyerror.formatting import Formatter
        from pyerror import core as _core
    except Exception:
        return

    try:
        details = SuggestionEngine.get_details(exc)
    except Exception:
        details = None
    if not details:
        return

    lines = ["pyerror — humanized failure"]
    if details.get("translation"):
        lines.append("  " + details["translation"])
    if details.get("why"):
        lines.append("  Why: " + details["why"])
    suggestions = details.get("suggestions") or []
    if suggestions:
        lines.append("  Suggestions:")
        for s in suggestions[:3]:
            lines.append("    - " + s)
    captured = getattr(exc, "__captured_locals__", None)
    if captured:
        lines.append("  Captured locals:")
        try:
            for fn, vars_ in captured.items():
                masked = Formatter.mask_locals(vars_, _core._mask_secrets, _core._secret_keys)
                for k, v in list(masked.items())[:10]:
                    lines.append("    {}.{} = {}".format(fn, k, v))
        except Exception:
            pass

    try:
        report.sections.append(("pyerror", "\n".join(lines)))
    except Exception:
        pass
    report._pyerror_handled = True

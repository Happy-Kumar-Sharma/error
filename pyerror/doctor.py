"""
pyerror.doctor — environment sanity checker.

Runs a series of quick, non-destructive checks against the current Python
environment and reports anything likely to confuse beginners or break
pyerror itself (stdlib shadowing, hijacked excepthooks, missing optional
integrations, broken console encoding on Windows, ...).

Usage:
    >>> from pyerror.doctor import run_doctor
    >>> results = run_doctor()          # pretty-prints and returns the results
    >>> bad = [r for r in results if r.status == "fail"]

Every individual check is wrapped so that a failure inside the doctor
itself can never raise into the host application.
"""
import os
import sys
import importlib
from dataclasses import dataclass
from typing import List, Optional

try:
    from rich.console import Console
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Stdlib module names that beginners commonly shadow with a local file,
# breaking imports in deeply confusing ways (e.g. a json.py in cwd).
SHADOWABLE_STDLIB = {
    "abc", "calendar", "code", "collections", "copy", "csv", "datetime",
    "email", "enum", "html", "http", "io", "json", "logging", "math",
    "os", "pickle", "platform", "queue", "random", "re", "secrets",
    "select", "signal", "site", "socket", "statistics", "string", "sys",
    "test", "threading", "time", "token", "traceback", "types", "typing",
    "turtle", "uuid",
}

# Optional third-party integrations pyerror can take advantage of.
OPTIONAL_INTEGRATIONS = ["opentelemetry", "flask", "fastapi", "pytest", "prometheus_client", "requests"]


@dataclass
class CheckResult:
    name: str
    status: str  # "ok" | "warn" | "fail"
    detail: str


def _check_python_version() -> CheckResult:
    version = "{}.{}.{}".format(*sys.version_info[:3])
    if sys.version_info < (3, 8):
        return CheckResult("python_version", "warn", f"Python {version} is end-of-life; upgrade to 3.8+ recommended")
    return CheckResult("python_version", "ok", f"Python {version}")


def _check_pyerror() -> CheckResult:
    try:
        import pyerror
        version = getattr(pyerror, "__version__", "unknown")
        path = os.path.dirname(os.path.abspath(pyerror.__file__))
        return CheckResult("pyerror", "ok", f"pyerror {version} imported from {path}")
    except Exception as e:
        return CheckResult("pyerror", "fail", f"pyerror could not be imported: {e}")


def _check_rich() -> CheckResult:
    try:
        import rich  # noqa: F401
        version = "unknown"
        try:
            from importlib import metadata
            version = metadata.version("rich")
        except Exception:
            pass
        return CheckResult("rich", "ok", f"rich {version} available (pretty tracebacks enabled)")
    except ImportError:
        return CheckResult("rich", "warn", "rich not installed; falling back to plain-text output (pip install rich)")


def _check_integrations() -> CheckResult:
    present = []
    missing = []
    for name in OPTIONAL_INTEGRATIONS:
        try:
            spec = importlib.util.find_spec(name)
        except Exception:
            spec = None
        (present if spec is not None else missing).append(name)
    detail = "present: {} | missing: {}".format(
        ", ".join(present) or "none",
        ", ".join(missing) or "none",
    )
    return CheckResult("optional_integrations", "ok", detail)


def _check_excepthook() -> CheckResult:
    hook = sys.excepthook
    try:
        from pyerror import core
        if hook is core._custom_excepthook:
            return CheckResult("excepthook", "ok", "pyerror humanize() is active")
    except Exception:
        pass
    if hook is sys.__excepthook__:
        return CheckResult("excepthook", "ok", "default Python excepthook (pyerror.humanize() not enabled)")
    owner = getattr(hook, "__module__", None) or repr(hook)
    return CheckResult("excepthook", "warn", f"sys.excepthook was replaced by another library: {owner}")


def _check_io_encoding() -> CheckResult:
    if os.name != "nt":
        return CheckResult("io_encoding", "ok", f"stdout encoding: {getattr(sys.stdout, 'encoding', 'unknown')}")
    env_enc = os.environ.get("PYTHONIOENCODING", "")
    stdout_enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    if "utf" in env_enc.lower() or "utf" in stdout_enc:
        return CheckResult("io_encoding", "ok", f"UTF-8 console output (encoding: {stdout_enc or env_enc})")
    return CheckResult(
        "io_encoding", "warn",
        f"console encoding is '{stdout_enc or 'unknown'}'; emojis/box-drawing may break. "
        "Set PYTHONIOENCODING=utf-8 (or use Windows Terminal)"
    )


def _check_virtualenv() -> CheckResult:
    in_venv = (
        getattr(sys, "base_prefix", sys.prefix) != sys.prefix
        or getattr(sys, "real_prefix", None) is not None
        or bool(os.environ.get("VIRTUAL_ENV"))
    )
    if in_venv:
        return CheckResult("virtualenv", "ok", f"virtual environment active: {sys.prefix}")
    return CheckResult("virtualenv", "warn", "no virtual environment active; installs go to the global interpreter")


def _check_stdlib_shadowing(cwd: str) -> CheckResult:
    shadows = []
    try:
        for name in os.listdir(cwd):
            if name.endswith(".py") and name[:-3] in SHADOWABLE_STDLIB:
                shadows.append(name)
    except OSError as e:
        return CheckResult("stdlib_shadowing", "warn", f"could not scan directory: {e}")
    if shadows:
        return CheckResult(
            "stdlib_shadowing", "fail",
            "files in {} shadow standard-library modules: {} -- rename them, they break imports".format(
                cwd, ", ".join(sorted(shadows))
            )
        )
    return CheckResult("stdlib_shadowing", "ok", f"no standard-library shadowing files in {cwd}")


def _check_analytics_writable() -> CheckResult:
    try:
        from pyerror.analytics import _tracker
        filename = os.path.abspath(_tracker.filename)
    except Exception:
        filename = os.path.abspath(".error_analytics.json")
    target = filename if os.path.exists(filename) else (os.path.dirname(filename) or os.getcwd())
    if os.access(target, os.W_OK):
        return CheckResult("analytics_file", "ok", f"analytics file is writable: {filename}")
    return CheckResult("analytics_file", "warn", f"analytics file is not writable: {filename}")


def run_doctor(print_output: bool = True, cwd: Optional[str] = None) -> List[CheckResult]:
    """
    Runs all environment checks and returns a list of CheckResult.
    Pretty-prints a report (rich when available) unless print_output=False.
    `cwd` overrides the directory scanned for stdlib shadowing (defaults to os.getcwd()).
    """
    if cwd is None:
        cwd = os.getcwd()

    checks = [
        _check_python_version,
        _check_pyerror,
        _check_rich,
        _check_integrations,
        _check_excepthook,
        _check_io_encoding,
        _check_virtualenv,
        lambda: _check_stdlib_shadowing(cwd),
        _check_analytics_writable,
    ]

    results: List[CheckResult] = []
    for check in checks:
        try:
            results.append(check())
        except Exception as e:
            results.append(CheckResult(getattr(check, "__name__", "check"), "fail", f"check crashed: {e}"))

    if print_output:
        try:
            _print_results(results)
        except Exception:
            pass
    return results


def _print_results(results: List[CheckResult]) -> None:
    if RICH_AVAILABLE:
        console = Console()
        table = Table(title="pyerror doctor", title_style="bold cyan", header_style="bold magenta")
        table.add_column("Status", justify="center")
        table.add_column("Check", style="white")
        table.add_column("Detail", style="dim")
        styles = {"ok": "[bold green]OK[/bold green]", "warn": "[bold yellow]WARN[/bold yellow]", "fail": "[bold red]FAIL[/bold red]"}
        for r in results:
            table.add_row(styles.get(r.status, r.status), r.name, r.detail)
        console.print(table)
    else:
        print("=== pyerror doctor ===")
        for r in results:
            print(f"[{r.status.upper():4}] {r.name}: {r.detail}")
    fails = sum(1 for r in results if r.status == "fail")
    warns = sum(1 for r in results if r.status == "warn")
    summary = f"{len(results)} checks: {len(results) - fails - warns} ok, {warns} warnings, {fails} failures"
    if RICH_AVAILABLE:
        Console().print(f"[dim]{summary}[/dim]")
    else:
        print(summary)

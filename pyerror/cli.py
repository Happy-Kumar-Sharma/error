"""
pyerror.cli — `pyerror` command-line entry point.

Subcommands:
    run script.py [args...]     Run a script with humanized errors enabled.
    report last                  Show the last saved error report.
    analytics [--clear]          Show / clear recurring-error analytics.
    doctor                       Environment sanity check.
    watch script.py              Re-run script on save (poll-based, stdlib only).
    serve [--host --port]        Tiny self-hosted Flask dashboard.
    lookup <ExceptionName>       Open the error encyclopedia.
    shellhook --shell <name>     Print a profile snippet that wraps invocations.

Stdlib argparse only — no click dependency.
"""
from __future__ import annotations

import argparse
import json
import os
import runpy
import sys
import time
import traceback
from typing import List, Optional

LAST_ERROR_DIR = os.path.join(os.path.expanduser("~"), ".pyerror")
LAST_ERROR_FILE = os.path.join(LAST_ERROR_DIR, "last_error.json")


def _ensure_dir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass


def _save_last_error(exc: BaseException) -> None:
    try:
        import pyerror
        _ensure_dir(LAST_ERROR_DIR)
        with open(LAST_ERROR_FILE, "w", encoding="utf-8") as fh:
            fh.write(pyerror.to_json(exc))
    except Exception:
        pass


def cmd_run(args: argparse.Namespace) -> int:
    import pyerror
    if args.mode:
        pyerror.configure(traceback_mode=args.mode)
    if args.theme:
        pyerror.configure(theme=args.theme)
    pyerror.humanize(True)

    script = args.script
    if not os.path.exists(script):
        sys.stderr.write("pyerror: script not found: {}\n".format(script))
        return 2

    sys.argv = [script] + list(args.script_args or [])
    try:
        runpy.run_path(script, run_name="__main__")
        return 0
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except BaseException as exc:
        try:
            from pyerror.formatting import Formatter
            from pyerror import core as _core
            sys.stderr.write(Formatter.format_cli(
                exc, mode=_core._traceback_mode,
                mask_secrets=_core._mask_secrets,
                secret_keys=_core._secret_keys,
            ))
        except Exception:
            traceback.print_exception(type(exc), exc, exc.__traceback__)
        _save_last_error(exc)
        return 1


def cmd_report(args: argparse.Namespace) -> int:
    if args.target != "last":
        sys.stderr.write("pyerror report: only 'last' is supported.\n")
        return 2
    if not os.path.exists(LAST_ERROR_FILE):
        sys.stderr.write("pyerror: no saved error report at {}\n".format(LAST_ERROR_FILE))
        return 1
    try:
        with open(LAST_ERROR_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        sys.stderr.write("pyerror: could not read report ({}).\n".format(exc))
        return 1
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.json import JSON
        Console().print(Panel(JSON.from_data(data), title="pyerror — last error", border_style="red"))
    except Exception:
        print(json.dumps(data, indent=2))
    return 0


def cmd_analytics(args: argparse.Namespace) -> int:
    import pyerror
    if args.clear:
        pyerror.clear_analytics()
        print("pyerror: analytics cleared.")
        return 0
    pyerror.get_analytics().show()
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        from pyerror.doctor import run_doctor
        results = run_doctor(print_output=True)
        failed = sum(1 for r in results if getattr(r, "status", "") == "fail")
        return 1 if failed else 0
    except Exception as exc:
        sys.stderr.write("pyerror doctor: {}\n".format(exc))
        return 1


def cmd_watch(args: argparse.Namespace) -> int:
    import subprocess
    script = os.path.abspath(args.script)
    if not os.path.exists(script):
        sys.stderr.write("pyerror watch: script not found: {}\n".format(script))
        return 2

    watch_dir = os.path.dirname(script) or "."

    def _mtimes() -> dict:
        out = {}
        try:
            for name in os.listdir(watch_dir):
                if name.endswith(".py"):
                    try:
                        out[name] = os.stat(os.path.join(watch_dir, name)).st_mtime
                    except OSError:
                        pass
        except OSError:
            pass
        return out

    print("pyerror watch: watching {} (Ctrl+C to quit)".format(watch_dir))
    last = {}
    while True:
        current = _mtimes()
        if current != last:
            print("\n--- running {} ---".format(os.path.basename(script)))
            cmd = [sys.executable, "-m", "pyerror", "run", script] + list(args.script_args or [])
            try:
                proc = subprocess.run(cmd)
                print("--- last run: {} ---".format("OK" if proc.returncode == 0 else "ERROR (exit {})".format(proc.returncode)))
            except Exception as exc:
                print("--- watch error: {} ---".format(exc))
            last = current
        try:
            time.sleep(0.5)
        except KeyboardInterrupt:
            print("\npyerror watch: stopped.")
            return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        from pyerror.dashboard import serve
    except ImportError as exc:
        sys.stderr.write("pyerror serve: dashboard module requires `pip install pyerror-intel[dashboard]` ({})\n".format(exc))
        return 1
    try:
        serve(host=args.host, port=args.port)
        return 0
    except Exception as exc:
        sys.stderr.write("pyerror serve: {}\n".format(exc))
        return 1


def cmd_lookup(args: argparse.Namespace) -> int:
    try:
        from pyerror.encyclopedia import lookup, search
    except ImportError as exc:
        sys.stderr.write("pyerror lookup: encyclopedia unavailable ({})\n".format(exc))
        return 1
    entry = lookup(args.name)
    if not entry:
        alts = search(args.name)
        if alts:
            sys.stderr.write("pyerror lookup: unknown '{}'. Did you mean: {}\n".format(args.name, ", ".join(alts[:5])))
        else:
            sys.stderr.write("pyerror lookup: unknown '{}'.\n".format(args.name))
        return 1
    print("== {} ==".format(entry.get("name", args.name)))
    print("\n" + (entry.get("translation") or ""))
    if entry.get("why"):
        print("\nWhy:\n  " + entry["why"])
    if entry.get("suggestions"):
        print("\nSuggestions:")
        for s in entry["suggestions"]:
            print("  - " + s)
    if entry.get("common_causes"):
        print("\nCommon causes:")
        for c in entry["common_causes"]:
            print("  - " + c)
    if entry.get("example"):
        print("\nExample:\n" + entry["example"])
    return 0


def cmd_shellhook(args: argparse.Namespace) -> int:
    try:
        from pyerror.shellhook import print_shell_hook
        print_shell_hook(shell=args.shell)
        return 0
    except Exception as exc:
        sys.stderr.write("pyerror shellhook: {}\n".format(exc))
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyerror", description="Python error intelligence CLI.")
    sub = parser.add_subparsers(dest="command")
    sub.required = False

    p_run = sub.add_parser("run", help="Run a script with humanized errors.")
    p_run.add_argument("script")
    p_run.add_argument("script_args", nargs=argparse.REMAINDER)
    p_run.add_argument("--mode", choices=("beginner", "compact", "full", "production"), default=None)
    p_run.add_argument("--theme", choices=("dark", "light", "nord", "monochrome"), default=None)
    p_run.set_defaults(func=cmd_run)

    p_report = sub.add_parser("report", help="Show a saved error report.")
    p_report.add_argument("target", choices=("last",))
    p_report.set_defaults(func=cmd_report)

    p_an = sub.add_parser("analytics", help="Show recurring-error analytics.")
    p_an.add_argument("--clear", action="store_true")
    p_an.set_defaults(func=cmd_analytics)

    p_doc = sub.add_parser("doctor", help="Environment sanity check.")
    p_doc.set_defaults(func=cmd_doctor)

    p_watch = sub.add_parser("watch", help="Re-run a script on file save.")
    p_watch.add_argument("script")
    p_watch.add_argument("script_args", nargs=argparse.REMAINDER)
    p_watch.set_defaults(func=cmd_watch)

    p_serve = sub.add_parser("serve", help="Tiny self-hosted dashboard.")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.set_defaults(func=cmd_serve)

    p_look = sub.add_parser("lookup", help="Look up an exception in the encyclopedia.")
    p_look.add_argument("name")
    p_look.set_defaults(func=cmd_lookup)

    p_hook = sub.add_parser("shellhook", help="Print a shell-profile snippet.")
    p_hook.add_argument("--shell", choices=("powershell", "bash", "zsh"), default="bash")
    p_hook.set_defaults(func=cmd_shellhook)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

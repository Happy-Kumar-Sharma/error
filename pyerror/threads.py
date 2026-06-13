"""
Thread / multiprocessing exception capture.

`install_thread_hooks()` sets `threading.excepthook` and `sys.unraisablehook`
to humanize exceptions escaping threads. `@capture_subprocess_errors`
serializes the failure of a worker function so the parent gets a
`RemoteError` carrying the full text traceback and metadata.
"""
from __future__ import annotations

import functools
import sys
import threading
import traceback
from typing import Any, Callable, Optional


class RemoteError(RuntimeError):
    """Exception raised in a parent after a worker function failed."""

    def __init__(self, message: str, *, remote_type: str, remote_traceback: str,
                 captured_locals: Optional[dict] = None):
        super().__init__(message)
        self.remote_type = remote_type
        self.__remote_traceback__ = remote_traceback
        self.__captured_locals__ = captured_locals or {}


_prev_thread_hook: Optional[Callable] = None
_prev_unraisable_hook: Optional[Callable] = None
_INSTALLED = False


def _humanize_and_log(exc: BaseException) -> None:
    try:
        from pyerror.analytics import log_error
        log_error(exc)
    except Exception:
        pass
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


def _thread_hook(args) -> None:
    if args.exc_type is SystemExit:
        return
    exc = args.exc_value
    if exc is not None and exc.__traceback__ is None:
        try:
            exc.__traceback__ = args.exc_traceback
        except Exception:
            pass
    if exc is not None:
        _humanize_and_log(exc)


def _unraisable_hook(args) -> None:
    exc = args.exc_value
    if exc is not None:
        _humanize_and_log(exc)


def install_thread_hooks() -> bool:
    """Install humanized threading.excepthook + sys.unraisablehook."""
    global _prev_thread_hook, _prev_unraisable_hook, _INSTALLED
    if _INSTALLED:
        return True
    if hasattr(threading, "excepthook"):
        _prev_thread_hook = threading.excepthook
        threading.excepthook = _thread_hook
    if hasattr(sys, "unraisablehook"):
        _prev_unraisable_hook = sys.unraisablehook
        sys.unraisablehook = _unraisable_hook
    _INSTALLED = True
    return True


def uninstall_thread_hooks() -> None:
    global _prev_thread_hook, _prev_unraisable_hook, _INSTALLED
    if _prev_thread_hook is not None and hasattr(threading, "excepthook"):
        threading.excepthook = _prev_thread_hook
    if _prev_unraisable_hook is not None and hasattr(sys, "unraisablehook"):
        sys.unraisablehook = _prev_unraisable_hook
    _prev_thread_hook = None
    _prev_unraisable_hook = None
    _INSTALLED = False


def capture_subprocess_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap `func` so worker exceptions surface as `RemoteError` in the parent."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except BaseException as exc:
            tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            captured: dict = {}
            tb = exc.__traceback__
            while tb is not None:
                if tb.tb_frame.f_code == func.__code__:
                    for k, v in tb.tb_frame.f_locals.items():
                        try:
                            captured[k] = repr(v)
                        except Exception:
                            captured[k] = "<unrepresentable>"
                    break
                tb = tb.tb_next
            raise RemoteError(
                "{}: {}".format(type(exc).__qualname__, exc),
                remote_type=type(exc).__qualname__,
                remote_traceback=tb_text,
                captured_locals={func.__name__: captured} if captured else {},
            )

    return wrapper

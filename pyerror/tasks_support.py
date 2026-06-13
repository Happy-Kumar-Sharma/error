"""
Task-queue failure hooks for Celery, RQ, and Dramatiq.

Each integration attaches a ``__task_context__`` dict to the failing
exception so downstream formatters/notifiers can show task metadata.
"""
from __future__ import annotations

import sys
from typing import Any, Callable, Dict, Optional


def _humanize(exc: BaseException, task_context: Dict[str, Any]) -> None:
    try:
        from pyerror.formatting import Formatter
        from pyerror import core as _core
        from pyerror.analytics import log_error
        scrubbed = {k: Formatter.scrub_text(str(v)) for k, v in task_context.items()}
        try:
            exc.__task_context__ = scrubbed
        except Exception:
            pass
        log_error(exc)
        sys.stderr.write(Formatter.format_cli(
            exc, mode=_core._traceback_mode,
            mask_secrets=_core._mask_secrets,
            secret_keys=_core._secret_keys,
        ))
        sys.stderr.write("  Task context: {}\n".format(scrubbed))
    except Exception:
        pass


def celery_task_failure_handler(sender=None, task_id=None, exception=None,
                                args=None, kwargs=None, traceback=None, einfo=None, **_):
    if exception is None:
        return
    _humanize(exception, {
        "task_id": str(task_id) if task_id else "",
        "task_name": getattr(sender, "name", "") if sender is not None else "",
        "args": repr(args),
        "kwargs": repr(kwargs),
    })


def install_celery_hooks(app: Any = None) -> bool:
    try:
        from celery import signals  # type: ignore
    except ImportError:
        raise ImportError("install_celery_hooks requires `pip install celery`.")
    signals.task_failure.connect(celery_task_failure_handler, weak=False)
    return True


def rq_exception_handler(job, exc_type, exc_value, tb):
    if exc_value is None:
        return True
    _humanize(exc_value, {
        "job_id": getattr(job, "id", ""),
        "func_name": getattr(job, "func_name", ""),
        "args": repr(getattr(job, "args", None)),
        "kwargs": repr(getattr(job, "kwargs", None)),
    })
    return True


def DramatiqMiddleware():
    """Factory returning a dramatiq.Middleware subclass (lazy import)."""
    try:
        import dramatiq  # type: ignore
    except ImportError:
        raise ImportError("DramatiqMiddleware requires `pip install dramatiq`.")

    class _PyerrorDramatiq(dramatiq.Middleware):
        def after_process_message(self, broker, message, *, result=None, exception=None):
            if exception is None:
                return
            _humanize(exception, {
                "actor_name": message.actor_name,
                "message_id": message.message_id,
                "args": repr(message.args),
                "kwargs": repr(message.kwargs),
            })

    return _PyerrorDramatiq

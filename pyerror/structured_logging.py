"""
Structured logging adapter.

`log_exception(exc)` emits a JSON-line event via structlog when
available, else via the stdlib logging module. `structlog_processor`
can be inserted into a structlog pipeline to enrich existing
log records that already carry an exception.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional


def _build_event(exc: BaseException, level: str = "error") -> Dict[str, Any]:
    from pyerror.formatting import Formatter
    from pyerror.suggestions import SuggestionEngine
    try:
        details = SuggestionEngine.get_details(exc) or {}
    except Exception:
        details = {}
    fp = ""
    try:
        from pyerror.otel import fingerprint
        fp = fingerprint(exc)
    except Exception:
        pass
    rel = None
    try:
        from pyerror import analytics
        rel = analytics._RELEASE
    except Exception:
        pass
    location = "unknown"
    tb = getattr(exc, "__traceback__", None)
    if tb is not None:
        while tb.tb_next is not None:
            tb = tb.tb_next
        location = "{}:{}".format(tb.tb_frame.f_code.co_filename, tb.tb_lineno)
    return {
        "timestamp": time.time(),
        "level": level,
        "event": "exception",
        "error_type": type(exc).__name__,
        "message": Formatter.scrub_text(str(exc)),
        "fingerprint": fp,
        "release": rel,
        "translation": details.get("translation"),
        "suggestions": (details.get("suggestions") or [])[:3],
        "location": location,
    }


def log_exception(exc: BaseException, logger: Any = None, level: str = "error") -> Dict[str, Any]:
    event = _build_event(exc, level)
    try:
        import structlog  # type: ignore
        log = logger or structlog.get_logger("pyerror")
        getattr(log, level, log.error)(**event)
        return event
    except Exception:
        pass
    log = logger or logging.getLogger("pyerror")
    getattr(log, level, log.error)(json.dumps(event, default=str))
    return event


def structlog_processor(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """structlog processor enriching events that already carry an exception."""
    exc = event_dict.get("exc_info") or event_dict.get("exception")
    if isinstance(exc, BaseException):
        try:
            event_dict.update({k: v for k, v in _build_event(exc).items() if k not in event_dict})
        except Exception:
            pass
    return event_dict


class _JsonHandler(logging.Handler):
    def emit(self, record):
        try:
            payload = {
                "timestamp": record.created,
                "level": record.levelname.lower(),
                "logger": record.name,
                "message": record.getMessage(),
            }
            self.stream.write(json.dumps(payload) + "\n")
            self.stream.flush()
        except Exception:
            pass

    def __init__(self, stream):
        super().__init__()
        self.stream = stream


def attach_json_handler(stream=None) -> logging.Handler:
    import sys
    handler = _JsonHandler(stream or sys.stderr)
    logging.getLogger("pyerror").addHandler(handler)
    return handler

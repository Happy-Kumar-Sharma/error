"""
AWS Lambda / serverless handler wrapper for pyerror.

`@lambda_handler` wraps a function handler(event, context); on
exception it emits a single JSON line to stdout (CloudWatch-friendly)
and either re-raises (default) or returns a configured response.
"""
from __future__ import annotations

import functools
import json
import sys
import time
import traceback
from typing import Any, Callable, Dict, Optional


def _build_record(exc: BaseException, context: Any, include_locals: bool = False) -> Dict[str, Any]:
    from pyerror.formatting import Formatter
    from pyerror import core as _core
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
    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    record = {
        "level": "ERROR",
        "ts": time.time(),
        "error_type": type(exc).__name__,
        "message": Formatter.scrub_text(str(exc)),
        "translation": details.get("translation", ""),
        "suggestions": (details.get("suggestions") or [])[:3],
        "fingerprint": fp,
        "aws_request_id": getattr(context, "aws_request_id", None),
        "function_name": getattr(context, "function_name", None),
        "traceback": Formatter.scrub_text(tb_text),
    }
    if include_locals:
        captured = getattr(exc, "__captured_locals__", None)
        if captured:
            try:
                masked = {fn: Formatter.mask_locals(vars_, _core._mask_secrets, _core._secret_keys)
                          for fn, vars_ in captured.items()}
                record["captured_locals"] = masked
            except Exception:
                pass
    return record


def lambda_handler(_func: Optional[Callable] = None, *,
                   reraise: bool = True,
                   response: Optional[Dict[str, Any]] = None,
                   include_locals: bool = False):
    """Decorator factory.

    Usage::

        @pyerror.lambda_handler
        def handler(event, context): ...

        @pyerror.lambda_handler(reraise=False, response={"statusCode": 500, "body": "error"})
        def handler(event, context): ...
    """
    def _decorate(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(event, context):
            try:
                return func(event, context)
            except BaseException as exc:
                try:
                    record = _build_record(exc, context, include_locals=include_locals)
                    sys.stdout.write(json.dumps(record, default=str) + "\n")
                    sys.stdout.flush()
                except Exception:
                    traceback.print_exception(type(exc), exc, exc.__traceback__)
                if reraise:
                    raise
                return response or {"statusCode": 500, "body": json.dumps({"error": "internal error"})}
        return wrapper

    if _func is not None and callable(_func):
        return _decorate(_func)
    return _decorate

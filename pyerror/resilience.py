"""
Resilience helpers — timeout, bulkhead, dead-letter, rate-limit-aware
retry, and hedged requests.

These are sync-only and platform-portable (no SIGALRM). Async variants
live in :mod:`pyerror.aio`.
"""
from __future__ import annotations

import functools
import json
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

DEAD_LETTER_DIR = os.path.join(os.path.expanduser("~"), ".pyerror")
DEAD_LETTER_FILE = os.path.join(DEAD_LETTER_DIR, "dead_letters.jsonl")


_BuiltinTimeoutError = TimeoutError


class TimeoutError(_BuiltinTimeoutError):  # type: ignore[no-redef]
    """Humanized TimeoutError carrying pyerror translation/why/suggestions."""
    __translation__ = "The operation did not finish within the allowed time."
    __why__ = "A `@pyerror.timeout` decorator interrupted the call after its budget elapsed."
    __suggestions__ = [
        "Increase the timeout if the work legitimately needs more time.",
        "Profile the function to find slow steps (consider pyerror.frame_timing).",
        "Add retries with backoff for transient slowness via @pyerror.retry.",
    ]


class BulkheadFullError(RuntimeError):
    __translation__ = "Too many concurrent calls — the bulkhead refused this one."
    __why__ = "A `@pyerror.bulkhead` limits concurrent execution; the limit is currently full."
    __suggestions__ = [
        "Increase the bulkhead's `max_concurrent` if your system can handle more parallelism.",
        "Add a retry with backoff for callers that can tolerate waiting.",
        "Inspect bulkhead status with `pyerror.bulkheads()`.",
    ]


_BULKHEADS: Dict[str, Dict[str, Any]] = {}


def timeout(seconds: float, exception: Type[BaseException] = TimeoutError):
    """Run the wrapped function in a daemon worker thread with a join deadline.

    Caveat: on timeout the worker thread is *not* killed — Python has no
    safe primitive for that. Long-running blocked operations may keep
    running in the background.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            result: List[Any] = []
            error: List[BaseException] = []

            def _runner():
                try:
                    result.append(func(*args, **kwargs))
                except BaseException as exc:
                    error.append(exc)

            thread = threading.Thread(target=_runner, name="pyerror.timeout", daemon=True)
            thread.start()
            thread.join(seconds)
            if thread.is_alive():
                raise exception(
                    "{} exceeded its {}s timeout (worker thread may still be running).".format(
                        getattr(func, "__qualname__", "function"), seconds
                    )
                )
            if error:
                raise error[0]
            return result[0] if result else None

        return wrapper
    return decorator


def bulkhead(max_concurrent: int, max_waiting: Optional[int] = None, name: Optional[str] = None):
    """Limit concurrent execution; reject excess waiters when max_waiting set."""
    sem = threading.BoundedSemaphore(max_concurrent)
    lock = threading.Lock()
    state = {"name": name or "bulkhead", "active": 0, "waiting": 0,
             "max_concurrent": max_concurrent, "max_waiting": max_waiting}

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        key = name or func.__qualname__
        state["name"] = key
        _BULKHEADS[key] = state

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            with lock:
                if max_waiting is not None and state["waiting"] >= max_waiting and state["active"] >= max_concurrent:
                    raise BulkheadFullError(
                        "bulkhead '{}' is full (active={}, waiting={}).".format(
                            key, state["active"], state["waiting"]
                        )
                    )
                state["waiting"] += 1
            try:
                acquired = sem.acquire()
                with lock:
                    state["waiting"] -= 1
                    state["active"] += 1
            except Exception:
                with lock:
                    state["waiting"] -= 1
                raise
            try:
                return func(*args, **kwargs)
            finally:
                with lock:
                    state["active"] -= 1
                sem.release()

        return wrapper
    return decorator


def bulkheads() -> Dict[str, Dict[str, Any]]:
    return {k: dict(v) for k, v in _BULKHEADS.items()}


def _ensure_dead_letter_dir(path: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass


def _json_safe(value: Any) -> Tuple[Any, bool]:
    try:
        json.dumps(value)
        return value, True
    except Exception:
        try:
            return repr(value), False
        except Exception:
            return "<unrepresentable>", False


def dead_letter(path: Optional[str] = None):
    """Persist (and re-raise) failed function calls to a JSONL file."""
    out_path = path or DEAD_LETTER_FILE

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except BaseException as exc:
                try:
                    from pyerror.otel import fingerprint
                    fp = fingerprint(exc)
                except Exception:
                    fp = ""
                safe_args: List[Any] = []
                safe_kwargs: Dict[str, Any] = {}
                replayable = True
                for a in args:
                    val, ok = _json_safe(a)
                    safe_args.append(val)
                    if not ok:
                        replayable = False
                for k, v in kwargs.items():
                    val, ok = _json_safe(v)
                    safe_kwargs[k] = val
                    if not ok:
                        replayable = False
                record = {
                    "ts": time.time(),
                    "func_module": getattr(func, "__module__", ""),
                    "func_qualname": getattr(func, "__qualname__", getattr(func, "__name__", "")),
                    "args": safe_args,
                    "kwargs": safe_kwargs,
                    "exc_type": type(exc).__qualname__,
                    "exc_msg": str(exc),
                    "fingerprint": fp,
                    "replayable": replayable,
                }
                _ensure_dead_letter_dir(out_path)
                try:
                    with open(out_path, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(record, default=str) + "\n")
                except Exception:
                    pass
                raise

        return wrapper
    return decorator


def list_dead_letters(path: Optional[str] = None) -> List[Dict[str, Any]]:
    out_path = path or DEAD_LETTER_FILE
    if not os.path.exists(out_path):
        return []
    records: List[Dict[str, Any]] = []
    try:
        with open(out_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return records


def clear_dead_letters(path: Optional[str] = None) -> None:
    out_path = path or DEAD_LETTER_FILE
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except Exception:
        pass


def replay(path: Optional[str] = None,
           handler: Optional[Callable[[Dict[str, Any]], Any]] = None) -> List[Dict[str, Any]]:
    """Return the dead-letter records, optionally invoking `handler(record)`."""
    records = list_dead_letters(path)
    if handler is None:
        return records
    for record in records:
        try:
            handler(record)
        except Exception:
            pass
    return records


def replay_failed(func: Callable[..., Any], path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Best-effort re-invocation of replayable records matching ``func``."""
    qualname = getattr(func, "__qualname__", getattr(func, "__name__", ""))
    outcomes: List[Dict[str, Any]] = []
    for record in list_dead_letters(path):
        if record.get("func_qualname") != qualname or not record.get("replayable"):
            outcomes.append({"record": record, "status": "skipped"})
            continue
        try:
            func(*record.get("args", []), **record.get("kwargs", {}))
            outcomes.append({"record": record, "status": "ok"})
        except BaseException as exc:
            outcomes.append({"record": record, "status": "failed", "error": str(exc)})
    return outcomes


def _parse_retry_after(exc: BaseException) -> Optional[float]:
    hint = getattr(exc, "retry_after", None)
    if hint is None:
        response = getattr(exc, "response", None)
        if response is not None:
            headers = getattr(response, "headers", None)
            if headers is not None:
                try:
                    hint = headers.get("Retry-After") or headers.get("retry-after")
                except Exception:
                    pass
    if hint is None:
        msg = str(exc)
        import re
        m = re.search(r"retry[_\- ]after[^\d]*([\d.]+)", msg, re.IGNORECASE)
        if m:
            hint = m.group(1)
    if hint is None:
        return None
    try:
        return float(hint)
    except (TypeError, ValueError):
        try:
            dt = parsedate_to_datetime(str(hint))
            return max(0.0, (dt.timestamp() - time.time()))
        except Exception:
            return None


def retry_rate_limited(
    tries: int = 5,
    max_wait: float = 120.0,
    base_delay: float = 0.5,
    backoff: float = 2.0,
    exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = (Exception,),
):
    """Retry on failure, honoring Retry-After hints when present."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempt = 1
            current = base_delay
            while attempt <= tries:
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == tries:
                        raise
                    hint = _parse_retry_after(exc)
                    sleep_s = min(hint if hint is not None else current, max_wait)
                    time.sleep(max(0.0, sleep_s))
                    current *= backoff
                    attempt += 1
            return None
        return wrapper
    return decorator


def hedge(delay: float, max_hedges: int = 1):
    """Fire ``max_hedges`` backup calls if the primary takes longer than ``delay``.

    Only safe for idempotent operations — losers continue running and
    any side effects they have will still happen.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            with ThreadPoolExecutor(max_workers=max_hedges + 1) as pool:
                first_exception: Optional[BaseException] = None
                futures = [pool.submit(func, *args, **kwargs)]
                attempts = 1
                while attempts <= max_hedges:
                    done, _ = wait(futures, timeout=delay, return_when=FIRST_COMPLETED)
                    if done:
                        for fut in done:
                            try:
                                return fut.result()
                            except BaseException as exc:
                                if first_exception is None:
                                    first_exception = exc
                                futures.remove(fut)
                        if not futures:
                            break
                    futures.append(pool.submit(func, *args, **kwargs))
                    attempts += 1
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for fut in done:
                    try:
                        return fut.result()
                    except BaseException as exc:
                        if first_exception is None:
                            first_exception = exc
                if first_exception is not None:
                    raise first_exception
                return None

        return wrapper
    return decorator

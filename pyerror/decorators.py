import time
import functools
import sys
import random
from typing import Callable, Any, Tuple, Type, Union

def _snapshot_func_locals(func: Callable, exc: BaseException) -> dict:
    snap = {}
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code is func.__code__:
            for k, v in tb.tb_frame.f_locals.items():
                try:
                    snap[k] = repr(v)
                except Exception:
                    snap[k] = "<unrepresentable>"
            break
        tb = tb.tb_next
    return snap


def _diff_locals(before: dict, after: dict) -> dict:
    added = {k: after[k] for k in after if k not in before}
    removed = {k: before[k] for k in before if k not in after}
    changed = {k: {"from": before[k], "to": after[k]}
               for k in before if k in after and before[k] != after[k]}
    return {"added": added, "removed": removed, "changed": changed}


def retry(
    tries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    jitter: bool = False,
    exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = (Exception,),
    diff_locals: bool = False,
):
    """
    Decorator that retries a function call if it raises specified exceptions.
    Uses exponential backoff by default, with optional full jitter.

    When ``diff_locals=True``, each failed attempt's frame locals are
    captured; if all retries are exhausted the raised exception gains
    ``exc.__retry_attempts__`` (per-attempt snapshots) and
    ``exc.__retry_diffs__`` (per-transition diffs) and a compact summary
    is printed to stderr.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempt = 1
            current_delay = delay
            attempts: list = []
            while attempt <= tries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if diff_locals:
                        snap = _snapshot_func_locals(func, e)
                        attempts.append({
                            "attempt": attempt,
                            "exception": "{}: {}".format(type(e).__name__, e),
                            "locals": snap,
                        })
                    if attempt == tries:
                        if diff_locals and attempts:
                            diffs = []
                            for i in range(1, len(attempts)):
                                diffs.append({
                                    "attempt_from": attempts[i - 1]["attempt"],
                                    "attempt_to": attempts[i]["attempt"],
                                    **_diff_locals(attempts[i - 1]["locals"], attempts[i]["locals"]),
                                })
                            try:
                                e.__retry_attempts__ = attempts
                                e.__retry_diffs__ = diffs
                            except Exception:
                                pass
                            if diffs:
                                sys.stderr.write(
                                    "⚠️ [pyerror.retry] locals changed across attempts: {}\n".format(
                                        ", ".join(
                                            "{}: {} -> {}".format(k, v["from"], v["to"])
                                            for d in diffs for k, v in d["changed"].items()
                                        ) or "no value changes"
                                    )
                                )
                                sys.stderr.flush()
                        raise e

                    sleep_time = random.uniform(0, current_delay) if jitter else current_delay
                    sys.stderr.write(
                        f"⚠️ [pyerror.retry] Attempt {attempt}/{tries} failed: {type(e).__name__}({e}). "
                        f"Retrying in {sleep_time:.2f}s...\n"
                    )
                    sys.stderr.flush()

                    time.sleep(sleep_time)
                    current_delay *= backoff
                    attempt += 1
            return None
        return wrapper
    return decorator

def capture_locals(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator that captures local variables of the decorated function
    when an exception is raised, attaching them to the exception object.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except BaseException as exc:
            # Capture local variables in the function frame
            tb = exc.__traceback__
            captured = {}
            while tb:
                frame = tb.tb_frame
                if frame.f_code == func.__code__:
                    # Capture f_locals
                    for k, v in frame.f_locals.items():
                        try:
                            captured[k] = repr(v)
                        except Exception as e:
                            captured[k] = f"<Unrepresentable: {type(e).__name__}>"
                    break
                tb = tb.tb_next
            
            if captured:
                if not hasattr(exc, "__captured_locals__"):
                    exc.__captured_locals__ = {}
                exc.__captured_locals__[func.__name__] = captured
            raise exc
    return wrapper

def fallback(
    default: Any = None, 
    exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = (Exception,)
):
    """
    Decorator that catches specified exceptions and returns a default value instead.
    
    Can be used with or without arguments:
    @fallback
    def f(): ...
    
    @fallback(default=[])
    def f(): ...
    """
    # If used as direct decorator: @fallback
    if callable(default) and not isinstance(default, (type, Exception, tuple)):
        func = default
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except exceptions:
                return None
        return wrapper

    # If used with arguments: @fallback(default=[])
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except exceptions:
                return default
        return wrapper
    return decorator

def self_healing(
    handler: Callable[[BaseException], Any],
    exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = (Exception,)
):
    """
    Decorator that intercepts targeted exceptions, runs an auto-recovery handler,
    and retries the operation exactly once.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                sys.stderr.write(
                    f"⚠️ [pyerror.self_healing] Intercepted {type(e).__name__}. Running recovery handler...\n"
                )
                sys.stderr.flush()
                try:
                    handler(e)
                except Exception as recovery_err:
                    sys.stderr.write(
                        f"⚠️ [pyerror.self_healing] Recovery handler raised an error: {recovery_err}. Aborting retry.\n"
                    )
                    sys.stderr.flush()
                    raise e
                
                # Retry once
                sys.stderr.write("⚠️ [pyerror.self_healing] Retrying execution...\n")
                sys.stderr.flush()
                return func(*args, **kwargs)
        return wrapper
    return decorator


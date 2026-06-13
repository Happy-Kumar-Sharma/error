"""
Async variants of pyerror's resilience decorators.

`aretry`, `afallback`, `atimeout`, `acircuit_breaker`, `abulkhead`.
Each rejects non-coroutine functions at decoration time with a clear
``TypeError``. ``acircuit_breaker`` shares the same registry as the
sync :func:`pyerror.circuit_breaker` so :func:`pyerror.breakers` lists
both.
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import random
import sys
import time
from typing import Any, Callable, Tuple, Type, Union

from pyerror.circuit_breaker import CircuitOpenError, _BreakerState, _REGISTRY
from pyerror.resilience import TimeoutError as _HumanTimeoutError


def _require_coroutine(func: Callable[..., Any]) -> None:
    if not inspect.iscoroutinefunction(func):
        raise TypeError(
            "{} must be an async def function for use with pyerror.aio decorators".format(
                getattr(func, "__qualname__", "function")
            )
        )


def aretry(
    tries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    jitter: bool = False,
    exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = (Exception,),
):
    def decorator(func):
        _require_coroutine(func)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            attempt = 1
            current = delay
            while attempt <= tries:
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == tries:
                        raise
                    sleep_s = random.uniform(0, current) if jitter else current
                    sys.stderr.write(
                        "⚠️ [pyerror.aretry] Attempt {}/{} failed: {}({}). Retrying in {:.2f}s...\n".format(
                            attempt, tries, type(exc).__name__, exc, sleep_s
                        )
                    )
                    sys.stderr.flush()
                    await asyncio.sleep(sleep_s)
                    current *= backoff
                    attempt += 1
            return None

        return wrapper
    return decorator


def afallback(default: Any = None,
              exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = (Exception,)):
    def decorator(func):
        _require_coroutine(func)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except exceptions:
                return default

        return wrapper
    return decorator


def atimeout(seconds: float):
    def decorator(func):
        _require_coroutine(func)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), seconds)
            except asyncio.TimeoutError:
                raise _HumanTimeoutError(
                    "{} exceeded its {}s timeout.".format(
                        getattr(func, "__qualname__", "function"), seconds
                    )
                )

        return wrapper
    return decorator


def acircuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = (Exception,),
    name: str = None,
):
    def decorator(func):
        _require_coroutine(func)
        key = name or func.__qualname__
        bs = _BreakerState(key, failure_threshold, recovery_timeout)
        _REGISTRY[key] = bs

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            now = time.time()
            if bs.state == "OPEN":
                if now - bs.last_failure_time >= bs.recovery_timeout:
                    bs.state = "HALF-OPEN"
                else:
                    raise CircuitOpenError(
                        "Circuit for '{}' is OPEN.".format(getattr(func, "__name__", key))
                    )
            try:
                result = await func(*args, **kwargs)
            except exceptions as exc:
                bs.failures += 1
                bs.last_failure_time = time.time()
                if bs.state == "HALF-OPEN":
                    bs.state = "OPEN"
                elif bs.failures >= bs.failure_threshold:
                    bs.state = "OPEN"
                raise exc
            else:
                if bs.state in ("HALF-OPEN", "OPEN"):
                    bs.state = "CLOSED"
                    bs.failures = 0
                return result

        wrapper.__circuit_state__ = lambda: bs.state
        wrapper.__circuit_failures__ = lambda: bs.failures
        wrapper.__breaker_name__ = key
        return wrapper

    return decorator


def abulkhead(max_concurrent: int):
    sem = asyncio.Semaphore(max_concurrent)

    def decorator(func):
        _require_coroutine(func)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            async with sem:
                return await func(*args, **kwargs)

        return wrapper
    return decorator

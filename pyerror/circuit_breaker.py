"""
Circuit breaker with optional persistence and global registry.

The original decorator API is preserved exactly. New optional kwargs:

- name=     explicit registry key (defaults to func.__qualname__).
- persist=  path to a JSON state file (atomic writes), or "redis://..."
            to use the optional redis backend; state survives restarts.

Inspect with :func:`breakers` / :func:`show_breakers`.
"""
from __future__ import annotations

import functools
import json
import os
import time
from typing import Any, Callable, Dict, Optional, Tuple, Type, Union


class CircuitOpenError(Exception):
    """Exception raised when the circuit breaker is open."""


_REGISTRY: Dict[str, "_BreakerState"] = {}


class _BreakerState:
    __slots__ = ("name", "state", "failures", "last_failure_time",
                 "failure_threshold", "recovery_timeout", "_persist_path", "_redis", "_redis_key")

    def __init__(self, name: str, failure_threshold: int, recovery_timeout: float):
        self.name = name
        self.state = "CLOSED"
        self.failures = 0
        self.last_failure_time = 0.0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._persist_path: Optional[str] = None
        self._redis = None
        self._redis_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "failures": self.failures,
            "last_failure_time": self.last_failure_time,
        }

    def load_from(self, persist: str) -> None:
        if persist.startswith("redis://"):
            try:
                import redis  # type: ignore
            except ImportError:
                raise ImportError(
                    "circuit_breaker(persist='redis://...') requires the `redis` package."
                )
            self._redis = redis.Redis.from_url(persist)
            self._redis_key = "pyerror:breaker:{}".format(self.name)
            try:
                raw = self._redis.get(self._redis_key)
                if raw:
                    data = json.loads(raw)
                    self.state = data.get("state", "CLOSED")
                    self.failures = data.get("failures", 0)
                    self.last_failure_time = data.get("last_failure_time", 0.0)
            except Exception:
                pass
            return

        self._persist_path = persist
        try:
            if os.path.exists(persist):
                with open(persist, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self.state = data.get("state", "CLOSED")
                self.failures = data.get("failures", 0)
                self.last_failure_time = data.get("last_failure_time", 0.0)
        except Exception:
            pass

    def save(self) -> None:
        if self._redis is not None and self._redis_key is not None:
            try:
                self._redis.set(self._redis_key, json.dumps(self.to_dict()))
            except Exception:
                pass
            return
        if self._persist_path is None:
            return
        try:
            tmp = self._persist_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.to_dict(), fh)
            os.replace(tmp, self._persist_path)
        except Exception:
            pass


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = (Exception,),
    name: Optional[str] = None,
    persist: Optional[str] = None,
):
    """Circuit breaker decorator.

    Adds an optional global registry entry under ``name`` (default: function
    qualname) and optional JSON or Redis persistence.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        key = name or func.__qualname__
        bs = _BreakerState(key, failure_threshold, recovery_timeout)
        if persist:
            bs.load_from(persist)
        _REGISTRY[key] = bs

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            now = time.time()
            if bs.state == "OPEN":
                if now - bs.last_failure_time >= bs.recovery_timeout:
                    bs.state = "HALF-OPEN"
                    bs.save()
                else:
                    raise CircuitOpenError(
                        "Circuit for '{}' is OPEN. Cooldown remaining: {:.1f}s.".format(
                            func.__name__, bs.recovery_timeout - (now - bs.last_failure_time)
                        )
                    )
            try:
                result = func(*args, **kwargs)
            except exceptions as exc:
                bs.failures += 1
                bs.last_failure_time = time.time()
                if bs.state == "HALF-OPEN":
                    bs.state = "OPEN"
                elif bs.failures >= bs.failure_threshold:
                    bs.state = "OPEN"
                bs.save()
                raise exc
            else:
                if bs.state in ("HALF-OPEN", "OPEN"):
                    bs.state = "CLOSED"
                    bs.failures = 0
                    bs.save()
                return result

        wrapper.__circuit_state__ = lambda: bs.state
        wrapper.__circuit_failures__ = lambda: bs.failures
        wrapper.__breaker_name__ = key
        return wrapper

    return decorator


def breakers() -> Dict[str, Dict[str, Any]]:
    """Return a snapshot of all registered breakers."""
    return {k: v.to_dict() for k, v in _REGISTRY.items()}


def show_breakers() -> None:
    snap = breakers()
    if not snap:
        print("pyerror breakers: no breakers registered.")
        return
    try:
        from rich.console import Console
        from rich.table import Table
        table = Table(title="pyerror — circuit breakers")
        for col in ("name", "state", "failures", "last_failure"):
            table.add_column(col)
        for info in snap.values():
            last = info["last_failure_time"]
            last_str = time.strftime("%H:%M:%S", time.localtime(last)) if last else "-"
            table.add_row(info["name"], info["state"], str(info["failures"]), last_str)
        Console().print(table)
    except Exception:
        for info in snap.values():
            print("  {:30}  {:10}  failures={}".format(info["name"], info["state"], info["failures"]))

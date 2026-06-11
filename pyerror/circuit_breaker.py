import time
import functools
from typing import Callable, Any, Tuple, Type, Union

class CircuitOpenError(Exception):
    """Exception raised when the circuit breaker is open."""
    pass

def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = (Exception,)
):
    """
    Decorator implementing the Circuit Breaker pattern.
    If the decorated function fails failure_threshold times consecutively,
    the circuit opens and all subsequent calls instantly raise CircuitOpenError.
    After recovery_timeout seconds, the circuit becomes half-open, allowing
    one trial call to check if the function can succeed.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        state = "CLOSED"
        failures = 0
        last_failure_time = 0.0

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            nonlocal state, failures, last_failure_time
            now = time.time()

            # If the circuit is open, check if the cooldown timeout has expired
            if state == "OPEN":
                if now - last_failure_time >= recovery_timeout:
                    state = "HALF-OPEN"
                else:
                    raise CircuitOpenError(
                        f"Circuit for '{func.__name__}' is OPEN. "
                        f"Cooldown remaining: {recovery_timeout - (now - last_failure_time):.1f}s."
                    )

            try:
                result = func(*args, **kwargs)
                # Success: reset state
                if state in ("HALF-OPEN", "OPEN"):
                    state = "CLOSED"
                    failures = 0
                return result
            except exceptions as e:
                # Capture failure details
                failures += 1
                last_failure_time = time.time()
                
                # If we are in HALF-OPEN and fail, go back to OPEN immediately
                if state == "HALF-OPEN":
                    state = "OPEN"
                elif failures >= failure_threshold:
                    state = "OPEN"
                    
                raise e

        # Expose state inspect helper for testing/debugging
        wrapper.__circuit_state__ = lambda: state
        wrapper.__circuit_failures__ = lambda: failures
        
        return wrapper
    return decorator

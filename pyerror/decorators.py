import time
import functools
import sys
import random
from typing import Callable, Any, Tuple, Type, Union

def retry(
    tries: int = 3, 
    delay: float = 1.0, 
    backoff: float = 2.0, 
    jitter: bool = False,
    exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = (Exception,)
):
    """
    Decorator that retries a function call if it raises specified exceptions.
    Uses exponential backoff by default, with optional full jitter.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempt = 1
            current_delay = delay
            while attempt <= tries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == tries:
                        # Re-raise the final exception
                        raise e
                    
                    # Calculate sleep time with optional full jitter
                    sleep_time = random.uniform(0, current_delay) if jitter else current_delay
                    
                    # Log or display warning to stderr
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

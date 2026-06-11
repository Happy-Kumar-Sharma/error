import sys
from contextlib import contextmanager
from typing import Union, Tuple, Type

@contextmanager
def ignore(*exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]]):
    """
    Context manager that swallows specified exceptions.
    
    Usage:
        with pyerror.ignore(FileNotFoundError):
            os.remove("nonexistent.txt")
            
        # If no exceptions are specified, it ignores all standard Exceptions
        with pyerror.ignore():
            1 / 0
    """
    # If no arguments provided, default to ignoring all Exception subclasses
    if not exceptions:
        target_exceptions = (Exception,)
    else:
        # Flatten and normalize arguments
        resolved = []
        for exc in exceptions:
            if isinstance(exc, tuple):
                resolved.extend(exc)
            else:
                resolved.append(exc)
        target_exceptions = tuple(resolved)

    try:
        yield
    except target_exceptions:
        # Suppress the exception
        pass

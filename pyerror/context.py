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

class capture_scope:
    """
    Context manager that captures all local variables of a block of code 
    upon exception. Automatically scrubs credentials and sensitive variables.
    
    Usage:
        try:
            with pyerror.capture_scope() as scope:
                secret_password = "my-password-123"
                value = 10 / 0
        except ZeroDivisionError:
            print(scope.locals) # {'secret_password': '********', 'value': ...}
    """
    def __init__(self):
        self.locals = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if exc_value is not None:
            tb = exc_traceback
            captured = {}
            from pyerror.formatting import Formatter
            
            # Walk traceback frames to collect local variables of the block
            while tb:
                frame = tb.tb_frame
                for k, v in frame.f_locals.items():
                    if k.startswith("__") or k == "self":
                        continue
                    try:
                        captured[k] = Formatter.scrub_text(repr(v))
                    except Exception:
                        try:
                            captured[k] = str(v)
                        except Exception:
                            captured[k] = "<Unrepresentable>"
                tb = tb.tb_next
                
            # Perform additional key-based secret masking on captured variables
            masked_captured = Formatter.mask_locals(captured, mask_secrets=True)
            self.locals = masked_captured
            
            # Attach to exception object
            if not hasattr(exc_value, "__captured_locals__"):
                exc_value.__captured_locals__ = {}
            exc_value.__captured_locals__["<capture_scope>"] = masked_captured
            
        return False  # Do not suppress the exception


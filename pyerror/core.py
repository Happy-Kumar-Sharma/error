import sys
from typing import Dict, Any, List, Optional

# Import formatter and suggestions
from pyerror.formatting import Formatter, JupyterHtmlWrapper
from pyerror.suggestions import SuggestionEngine

# Global configuration state
_enabled = False
_traceback_mode = "full"  # beginner, compact, full, production
_mask_secrets = True
_secret_keys = Formatter.DEFAULT_SECRETS.copy()
_hide_packages = []
_original_excepthook = sys.excepthook

class DiagnosticsResult:
    """Wrapper that displays beautifully in both Terminal and Jupyter."""
    def __init__(self, exc: BaseException, traceback_mode: str = "full"):
        self.exc = exc
        self.traceback_mode = traceback_mode
        self.details = SuggestionEngine.get_details(exc)

    def __str__(self) -> str:
        lines = [
            f"Error: {self.details['name']} - {self.details['message']}",
            f"Explanation: {self.details['translation']}",
            f"Why it happened: {self.details['why']}",
            "Suggestions:"
        ]
        for s in self.details["suggestions"]:
            lines.append(f"  - {s}")
        if self.details["example"]:
            lines.append("\nExample:")
            lines.append(self.details["example"])
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.__str__()

    def _repr_html_(self) -> str:
        """Jupyter representation."""
        return Formatter.format_jupyter_html(self.exc, _mask_secrets, _secret_keys)

    def show(self):
        """Outputs the premium Rich formatted output to stderr."""
        sys.stderr.write(Formatter.format_cli(
            self.exc, 
            mode=self.traceback_mode, 
            mask_secrets=_mask_secrets, 
            secret_keys=_secret_keys
        ))

def configure(
    traceback_mode: Optional[str] = None,
    mask_secrets: Optional[bool] = None,
    secret_keys: Optional[List[str]] = None,
    hide_packages: Optional[List[str]] = None,
):
    """Configures global error library settings."""
    global _traceback_mode, _mask_secrets, _secret_keys, _hide_packages
    if traceback_mode is not None:
        if traceback_mode not in ("beginner", "compact", "full", "production"):
            raise ValueError("traceback_mode must be one of: 'beginner', 'compact', 'full', 'production'")
        _traceback_mode = traceback_mode
    if mask_secrets is not None:
        _mask_secrets = mask_secrets
    if secret_keys is not None:
        _secret_keys = list(secret_keys)
    if hide_packages is not None:
        _hide_packages = list(hide_packages)

def add_privacy_rule(pattern: str):
    """Adds a custom string key to the list of secret keys to mask."""
    global _secret_keys
    if pattern not in _secret_keys:
        _secret_keys.append(pattern)

def to_json(exc: BaseException) -> str:
    """Serializes the exception details to a JSON string."""
    return Formatter.format_json(exc, _mask_secrets, _secret_keys)

def _custom_excepthook(exc_type, exc_value, exc_traceback):
    """sys.excepthook replacement for standard terminal exceptions."""
    if not _enabled or exc_type is KeyboardInterrupt:
        _original_excepthook(exc_type, exc_value, exc_traceback)
        return

    # Record to analytics automatically
    try:
        from pyerror.analytics import log_error
        log_error(exc_value)
    except Exception:
        pass

    try:
        # In production mode, print JSON to stderr
        if _traceback_mode == "production":
            sys.stderr.write(Formatter.format_json(exc_value, _mask_secrets, _secret_keys) + "\n")
        else:
            # Print beautiful Rich traceback
            sys.stderr.write(Formatter.format_cli(
                exc_value, 
                mode=_traceback_mode, 
                mask_secrets=_mask_secrets, 
                secret_keys=_secret_keys
            ))
        sys.stderr.flush()
    except Exception as e:
        # Fallback to original traceback if anything fails in formatting
        sys.stderr.write(f"⚠️ error: internal formatting error occurred: {e}\n")
        _original_excepthook(exc_type, exc_value, exc_traceback)

def _register_ipython_handler():
    """Tries to register custom exception handler in Jupyter/IPython environment."""
    try:
        from IPython import get_ipython
        ip = get_ipython()
        if ip is not None:
            def ipython_handler(self, etype, evalue, tb, tb_offset=None):
                if not _enabled:
                    # Fallback to standard IPython handler
                    return self.showtraceback((etype, evalue, tb), tb_offset=tb_offset)
                
                # Record to analytics automatically
                try:
                    from pyerror.analytics import log_error
                    log_error(evalue)
                except Exception:
                    pass

                try:
                    if _traceback_mode == "production":
                        # Output JSON string
                        print(Formatter.format_json(evalue, _mask_secrets, _secret_keys))
                    else:
                        # Output Jupyter HTML
                        from IPython.display import display, HTML
                        html_content = Formatter.format_jupyter_html(evalue, _mask_secrets, _secret_keys)
                        display(HTML(html_content))
                except Exception as e:
                    print(f"⚠️ error: internal formatting error in Jupyter: {e}")
                    self.showtraceback((etype, evalue, tb), tb_offset=tb_offset)

            # Register custom handler for all exception types
            ip.set_custom_exc((BaseException,), ipython_handler)
    except (ImportError, NameError):
        pass

def humanize(enable: bool = True):
    """Enables or disables the customized excepthook."""
    global _enabled
    _enabled = enable
    if enable:
        sys.excepthook = _custom_excepthook
        _register_ipython_handler()
    else:
        sys.excepthook = _original_excepthook

def beginner_mode(enable: bool = True):
    """Enables humanize and sets traceback mode to beginner (minimalist stack trace)."""
    global _traceback_mode
    if enable:
        configure(traceback_mode="beginner")
        humanize(True)
    else:
        configure(traceback_mode="full")

# Diagnostic helpers

def explain(exc: BaseException) -> DiagnosticsResult:
    """Explains a caught exception in a friendly, detailed way."""
    return DiagnosticsResult(exc, traceback_mode=_traceback_mode)

def diagnose(exc: BaseException) -> DiagnosticsResult:
    """Diagnoses a caught exception with stack, variables, and suggestions."""
    return DiagnosticsResult(exc, traceback_mode=_traceback_mode)

def suggest(exc: BaseException) -> List[str]:
    """Returns the list of actionable suggestions for a caught exception."""
    details = SuggestionEngine.get_details(exc)
    return details["suggestions"]

def inspect_last_error():
    """
    Inspects the last active exception in the interactive session (sys.last_value)
    and displays its humanized diagnostics report.
    """
    exc_type = getattr(sys, "last_type", None)
    exc_value = getattr(sys, "last_value", None)
    exc_tb = getattr(sys, "last_traceback", None)
    
    if exc_value is None:
        # Try retrieving from sys.exc_info() just in case we are in an except block
        exc_type, exc_value, exc_tb = sys.exc_info()
        
    if exc_value is None:
        sys.stderr.write("No active or previous exception found in this session.\n")
        return
        
    # Bind traceback if not present on exc_value
    if exc_tb and not getattr(exc_value, "__traceback__", None):
        exc_value.__traceback__ = exc_tb
        
    explain(exc_value).show()

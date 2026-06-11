from typing import List, Optional
from pyerror.suggestions import SuggestionEngine
from pyerror.formatting import Formatter

def assert_readable(exc: BaseException, min_suggestions: int = 1):
    """
    Asserts that an exception carries a highly readable explanation,
    reasons, and a minimum number of actionable recommendations.
    
    Suitable for unittest or pytest assertion flows.
    """
    details = SuggestionEngine.get_details(exc)
    
    # 1. Check explanation translation is custom/humanized
    assert details["translation"] != "An unexpected error occurred.", \
        f"AssertionError: Exception '{details['name']}' has only default/fallback translation."
        
    # 2. Check why reason is present
    assert details["why"] and details["why"] != f"Python encountered a {details['name']} while executing your code.", \
        f"AssertionError: Exception '{details['name']}' lacks customized 'why' reason details."
        
    # 3. Check minimum recommendations
    sug_count = len(details["suggestions"])
    assert sug_count >= min_suggestions, \
        f"AssertionError: Expected >= {min_suggestions} suggestions, got {sug_count} ({details['suggestions']})."

def assert_not_exposed(exc: BaseException, custom_secrets: Optional[List[str]] = None):
    """
    Asserts that the captured locals attached to the exception do not
    contain any plaintext secrets.
    """
    if not hasattr(exc, "__captured_locals__"):
        # No variables captured, so no exposure
        return
        
    keys_to_match = custom_secrets if custom_secrets is not None else Formatter.DEFAULT_SECRETS
    
    for scope_name, variables in exc.__captured_locals__.items():
        for var_name, var_value in variables.items():
            var_name_lower = var_name.lower()
            if any(secret in var_name_lower for secret in keys_to_match):
                # If it matches, the value must be masked!
                assert var_value == "********", \
                    f"AssertionError: Plaintext secret leaked in scope '{scope_name}': variable '{var_name}' has value '{var_value}'"

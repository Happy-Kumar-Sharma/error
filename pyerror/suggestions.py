import re
import sys
import traceback
from typing import Dict, Any, List, Optional

class SuggestionEngine:
    @staticmethod
    def get_details(exc: BaseException) -> Dict[str, Any]:
        """
        Analyze an exception and return plain-English explanations,
        reasons, suggestions, and correct usage examples.
        """
        exc_type = type(exc)
        exc_name = exc_type.__name__
        exc_msg = str(exc)

        # Base response template
        result = {
            "name": exc_name,
            "message": exc_msg,
            "translation": "An unexpected error occurred.",
            "why": f"Python encountered a {exc_name} while executing your code.",
            "suggestions": [
                "Review the traceback to locate where the error occurred.",
                "Check the values of variables involved in the failing line."
            ],
            "example": None
        }

        # Check for custom exceptions that carry suggestions
        if hasattr(exc, "__suggestions__") and exc.__suggestions__:
            result["suggestions"] = exc.__suggestions__
        if hasattr(exc, "__translation__") and exc.__translation__:
            result["translation"] = exc.__translation__
        if hasattr(exc, "__why__") and exc.__why__:
            result["why"] = exc.__why__

        # 1. KeyError
        if isinstance(exc, KeyError):
            key_repr = exc_msg
            # Strip extra quotes around the key repr if they exist
            if (key_repr.startswith("'") and key_repr.endswith("'")) or \
               (key_repr.startswith('"') and key_repr.endswith('"')):
                key_name = key_repr[1:-1]
            else:
                key_name = key_repr

            result["translation"] = "You tried to access a key in a dictionary that doesn't exist."
            result["why"] = f"The key '{key_name}' was not found in the dictionary you queried."
            result["suggestions"] = [
                f"Double-check the spelling of the key '{key_name}'.",
                f"Use '.get({key_repr})' instead of '[{key_repr}]' to return a default value (like None) if the key is missing.",
                "Verify the dictionary contents using print() or logging before accessing it.",
                f"Add the key first: my_dict[{key_repr}] = value"
            ]
            result["example"] = f"""# ❌ Incorrect:
my_dict = {{"name": "Alice"}}
print(my_dict[{key_repr}])  # Raises KeyError

#  Correct:
my_dict = {{"name": "Alice"}}
# Option A: Use .get() with a default value
print(my_dict.get({key_repr}, "Default Value"))

# Option B: Check if key exists
if {key_repr} in my_dict:
    print(my_dict[{key_repr}])"""

        # 2. TypeError
        elif isinstance(exc, TypeError):
            result["translation"] = "An operation was performed on incompatible data types."
            
            # Common TypeError: unsupported operand type(s)
            match_ops = re.search(r"unsupported operand type\(s\) for (.+): '(.+)' and '(.+)'", exc_msg)
            match_subscript = re.search(r"'(.+)' object is not subscriptable", exc_msg)
            match_call = re.search(r"'(.+)' object is not callable", exc_msg)
            match_args = re.search(r"takes (\d+) positional argument but (\d+) was given", exc_msg)

            if match_ops:
                op, t1, t2 = match_ops.groups()
                result["why"] = f"You tried to use the '{op}' operator between a '{t1}' and a '{t2}', which Python cannot do automatically."
                result["suggestions"] = [
                    f"Convert the '{t2}' to '{t1}' or vice versa before performing the '{op}' operation.",
                    f"If you want to concatenate, convert the non-string to a string using 'str(value)'.",
                    f"If you want to perform math, convert the string to a number using 'int(value)' or 'float(value)'."
                ]
                result["example"] = """# ❌ Incorrect:
result = 5 + "10"

#  Correct:
result = 5 + int("10")  # Yields 15
# Or:
result = str(5) + "10"  # Yields "510" """
            elif match_subscript:
                t = match_subscript.group(1)
                result["why"] = f"You tried to access an item using brackets [index] or [key] on an object of type '{t}', which is not a container (like list or dict)."
                result["suggestions"] = [
                    "Verify if the variable is None or a primitive type (like int or float) before using brackets.",
                    "Check if the variable should have been initialized as a list or a dictionary.",
                    "Make sure you did not accidentally overwrite your container variable with a non-container value."
                ]
                result["example"] = """# ❌ Incorrect:
value = None
print(value[0])  # Raises TypeError

#  Correct:
value = [10, 20, 30]
print(value[0])  # Yields 10"""
            elif match_call:
                t = match_call.group(1)
                result["why"] = f"You tried to call a '{t}' object as if it were a function (e.g., by adding parentheses () after it)."
                result["suggestions"] = [
                    f"Check if you accidentally named a variable the same as a built-in function (e.g. len = 5) and then tried to call it.",
                    "Check if you forgot to access an attribute and instead called the object directly.",
                    "Verify if you are missing a method name (e.g. calling 'object()' instead of 'object.method()')."
                ]
                result["example"] = """# ❌ Incorrect:
my_list = [1, 2]
len = len(my_list)
# Later in code:
length = len(my_list)  # Raises TypeError because len is now an integer (integer is not callable)

#  Correct:
# Do not use built-in function names like 'len', 'max', 'min', 'str', 'int' as variable names."""
            elif match_args:
                expected, given = match_args.groups()
                result["why"] = f"You passed {given} arguments to a function that only accepts {expected} arguments."
                result["suggestions"] = [
                    "Check the function definition to see what parameters it expects.",
                    "Ensure you are calling the correct function and not one with a similar name.",
                    "If this is an instance method, make sure the class is instantiated and 'self' is handled correctly."
                ]

        # 3. IndexError
        elif isinstance(exc, IndexError):
            result["translation"] = "You tried to access a element from a sequence (like a list) using an index that is out of range."
            result["why"] = "The index you requested is either too large or too small for the sequence's current length."
            result["suggestions"] = [
                "Remember that Python lists are 0-indexed. The first item is index 0, and the last item is len(sequence) - 1.",
                "Verify the length of your list using 'len(your_list)' before accessing specific indices.",
                "Use list slicing (e.g., 'your_list[:5]') which safely returns items without raising an IndexError.",
                "Use a try-except block to handle cases where the list might be shorter than expected."
            ]
            result["example"] = """# ❌ Incorrect:
items = ["apple", "banana"]
print(items[2])  # Raises IndexError (indices are 0 and 1)

#  Correct:
items = ["apple", "banana"]
if len(items) > 2:
    print(items[2])
else:
    print("Item not found")"""

        # 4. AttributeError
        elif isinstance(exc, AttributeError):
            result["translation"] = "You tried to access a property (attribute) or call a method that does not exist on this object."
            match_attr = re.search(r"object has no attribute '(.+)'", exc_msg)
            attr_name = match_attr.group(1) if match_attr else "requested attribute"
            
            if "'NoneType'" in exc_msg:
                result["why"] = f"You tried to access '{attr_name}' on an object that is None. This usually means a prior function returned None instead of a valid object."
                result["suggestions"] = [
                    "Verify why the object is None. Did a function call fail or return None under some conditions?",
                    "Check if you forgot to return a value in one of your functions.",
                    "Use a check 'if object is not None:' before accessing attributes."
                ]
                result["example"] = """# ❌ Incorrect:
def get_user(user_id):
    if user_id == 1:
        return {"name": "Alice"}
    # returns None implicitly for other IDs

user = get_user(2)
print(user.name)  # Raises AttributeError: 'NoneType' object has no attribute 'name'

#  Correct:
user = get_user(2)
if user is not None:
    print(user.name)
else:
    print("User not found")"""
            else:
                result["why"] = f"The object does not have the attribute or method named '{attr_name}'."
                suggestions = [
                    f"Check the spelling of the attribute '{attr_name}'.",
                    "List the available attributes of this object using 'dir(object)' to see what is valid.",
                    "Confirm that the object is of the type you expect (print its type using 'type(object)')."
                ]
                
                # Check spelling suggestions via difflib if obj is available on the error (Python 3.10+)
                obj = getattr(exc, "obj", None)
                name = getattr(exc, "name", None) or attr_name
                if obj is not None:
                    import difflib
                    close_matches = difflib.get_close_matches(name, dir(obj), n=2)
                    for match in close_matches:
                        suggestions.insert(0, f"💡 Did you mean to use attribute/method '{match}'?")
                result["suggestions"] = suggestions

        # 5. NameError
        elif isinstance(exc, NameError):
            result["translation"] = "You used a variable, function, or module name that has not been defined yet."
            match_name = re.search(r"name '(.+)' is not defined", exc_msg)
            var_name = match_name.group(1) if match_name else "variable"
            
            result["why"] = f"Python searched for the name '{var_name}' in your code but couldn't find any definition for it."
            
            suggestions = [
                f"Check for spelling mistakes or typos in the name '{var_name}'.",
                "Ensure that you have defined the variable/function BEFORE trying to use it.",
                "Check the scope of the variable. Variables defined inside a function cannot be accessed outside of it."
            ]
            
            # Check standard library suggestion
            common_libs = {
                "cos": "math", "sin": "math", "tan": "math", "sqrt": "math", "pi": "math",
                "pathname": "os.path", "join": "os.path", "exists": "os.path",
                "argv": "sys", "exit": "sys", "path": "sys",
                "dumps": "json", "loads": "json",
                "sleep": "time", "time": "time",
                "search": "re", "match": "re", "sub": "re",
                "utcnow": "datetime.datetime", "now": "datetime.datetime",
            }
            if var_name in common_libs:
                suggestions.insert(0, f"💡 Did you mean to import '{var_name}' from the '{common_libs[var_name]}' library? Try adding 'import {common_libs[var_name]}' or 'from {common_libs[var_name]} import {var_name}'.")
            
            # Check close spelling matches in current frame
            import difflib
            possibilities = list(__builtins__.keys()) if isinstance(__builtins__, dict) else dir(__builtins__)
            tb = exc.__traceback__
            if tb:
                # Walk to the last frame
                curr_tb = tb
                while curr_tb.tb_next:
                    curr_tb = curr_tb.tb_next
                possibilities.extend(curr_tb.tb_frame.f_globals.keys())
                possibilities.extend(curr_tb.tb_frame.f_locals.keys())
            
            # Filter out current var name
            possibilities = [p for p in possibilities if p != var_name]
            close_matches = difflib.get_close_matches(var_name, possibilities, n=2)
            for match in close_matches:
                suggestions.insert(0, f"💡 Did you mean the defined variable '{match}'?")
                
            result["suggestions"] = suggestions
            result["example"] = """# ❌ Incorrect:
print(message)  # Raises NameError: name 'message' is not defined
message = "Hello"

#  Correct:
message = "Hello"
print(message)"""

        # 6. ValueError
        elif isinstance(exc, ValueError):
            result["translation"] = "A function received an argument of the correct type, but the value itself is invalid or unacceptable."
            result["why"] = f"The value you passed could not be processed by the function (e.g., trying to convert a word into a number: int('hello'))."
            result["suggestions"] = [
                "Verify that the format/value of the variable matches the function's requirements.",
                "Add a check to validate inputs before passing them to the function.",
                "Use a try-except block to handle invalid inputs gracefully."
            ]
            result["example"] = """# ❌ Incorrect:
number = int("hello")  # Raises ValueError

#  Correct:
user_input = "hello"
if user_input.isdigit():
    number = int(user_input)
else:
    number = 0  # Fallback"""

        # 7. FileNotFoundError
        elif isinstance(exc, FileNotFoundError):
            result["translation"] = "The file or directory you are trying to open or access could not be found."
            result["why"] = f"Python could not locate any file or folder at the path specified in your code."
            result["suggestions"] = [
                "Double-check the spelling of the file path and filename.",
                "Verify if the file is in the current working directory. You can check the current directory using 'os.getcwd()'.",
                "Use absolute paths (e.g. 'C:/project/data.txt') instead of relative paths ('data.txt') to avoid confusion.",
                "Use 'os.path.exists(path)' to check if the file exists before attempting to open it."
            ]
            result["example"] = """# ❌ Incorrect:
with open("non_existent_file.txt", "r") as f:
    content = f.read()

#  Correct:
import os
path = "non_existent_file.txt"
if os.path.exists(path):
    with open(path, "r") as f:
        content = f.read()
else:
    print(f"File {path} not found!")"""

        # 8. ModuleNotFoundError
        elif isinstance(exc, ModuleNotFoundError):
            match_mod = re.search(r"No module named '(.+)'", exc_msg)
            mod_name = match_mod.group(1) if match_mod else "requested module"
            result["translation"] = "Python was unable to import a library/module because it isn't installed or found."
            result["why"] = f"The module '{mod_name}' is not available in the current Python environment."
            result["suggestions"] = [
                f"Install the module using pip in your terminal: pip install {mod_name}",
                "Verify you are running Python inside the correct virtual environment where the package is installed.",
                f"Check for spelling mistakes in the import statement: import {mod_name}"
            ]
            result["example"] = """# ❌ Incorrect:
import request  # Raises ModuleNotFoundError: No module named 'request'

#  Correct:
# Make sure to run 'pip install requests' in terminal first, then:
import requests"""

        # 9. ZeroDivisionError
        elif isinstance(exc, ZeroDivisionError):
            result["translation"] = "You tried to divide a number by zero, which is mathematically undefined."
            result["why"] = "A division (/) or modulo (%) operation was performed with a denominator of 0."
            result["suggestions"] = [
                "Check the variable acting as the denominator. Why did it become zero?",
                "Add a conditional check to verify the denominator is not zero before performing division.",
                "Provide a fallback value if division by zero would occur."
            ]
            result["example"] = """# ❌ Incorrect:
ratio = total_score / count  # Raises ZeroDivisionError if count is 0

#  Correct:
ratio = total_score / count if count != 0 else 0.0"""

        # 10. SyntaxError / IndentationError / TabError
        elif isinstance(exc, SyntaxError):
            result["translation"] = "Python encountered a line of code that violates Python's writing rules (syntax)."
            
            # Extract line contents if possible
            bad_line = exc.text.strip() if exc.text else ""
            line_str = f" line {exc.lineno}" if exc.lineno else ""
            
            # Check subclass
            if isinstance(exc, TabError):
                result["translation"] = "Spaces and tabs were mixed for indenting the code."
                result["why"] = f"Python does not allow mixing tab characters and spaces for indentation{line_str}."
                if bad_line:
                    result["why"] += f" The problematic line is: '{bad_line}'."
                result["suggestions"] = [
                    "Configure your editor to automatically convert tabs to spaces (4 spaces is the Python standard).",
                    "Replace all tab characters in your file with 4 spaces.",
                    "Check your editor settings to enable showing invisible/whitespace characters to spot mixed tabs and spaces."
                ]
                result["example"] = """# ❌ Incorrect (mixed tabs and spaces):
def greet():
\tprint("Hello")  # Tab character used
    print("World")  # Spaces used

#  Correct (spaces only):
def greet():
    print("Hello")
    print("World")"""
            elif isinstance(exc, IndentationError):
                result["translation"] = "The indentation of your code is incorrect."
                result["why"] = f"A line of code{line_str} is not aligned with the correct indentation level, or you forgot to indent the code block after a colon (:)."
                if bad_line:
                    result["why"] += f" The problematic line is: '{bad_line}'."
                result["suggestions"] = [
                    "Make sure all code lines inside a function, loop, condition (if/elif/else), or try/except block are aligned to the same indentation level.",
                    "Verify that the line immediately preceding the indented block ends with a colon (:).",
                    "Avoid mixing different amounts of spaces (e.g. some lines with 3 spaces and some with 4 spaces)."
                ]
                result["example"] = """# ❌ Incorrect:
def greet():
print("Hello")  # Raises IndentationError: expected an indented block

#  Correct:
def greet():
    print("Hello")  # Indented with 4 spaces"""
            else:
                # General SyntaxError
                result["why"] = f"A statement or expression was written incorrectly{line_str}."
                if bad_line:
                    result["why"] += f" The problematic line is: '{bad_line}'."
                
                # Check common syntax error types
                if "was never closed" in exc_msg or "unexpected EOF" in exc_msg:
                    result["why"] += " This is usually due to a missing closing parenthesis ')', bracket ']', or curly brace '}'."
                    result["suggestions"] = [
                        "Check the code for any unclosed parentheses '(', brackets '[', or braces '{'.",
                        "Ensure that all quotes (single, double, triple) are correctly opened and closed on the same line."
                    ]
                elif "expected ':'" in exc_msg:
                    result["why"] += " You forgot to put a colon ':' at the end of a block header (like 'if', 'for', 'while', 'def', 'class', or 'try')."
                    result["suggestions"] = [
                        "Add a colon ':' to the end of the line preceding the indented block.",
                        "Check for typos on the line preceding the block start."
                    ]
                else:
                    result["suggestions"] = [
                        "Check the line for missing colons ':', parentheses, brackets, or unmatched quotes.",
                        "Ensure that Python keywords (like 'for', 'in', 'if', 'import') are spelled correctly and used in the right order.",
                        "If typing multi-line statements in the REPL, make sure you don't start a new statement before closing the previous block."
                    ]
                
                result["example"] = """# ❌ Incorrect:
if name == "Alice"  # Missing colon
    print("Hello")

#  Correct:
if name == "Alice":
    print("Hello")"""

        # 11. OSError (PermissionError, ConnectionRefusedError, ConnectionResetError, AddressInUse)
        elif isinstance(exc, OSError):
            import errno
            err = exc.errno
            
            if isinstance(exc, PermissionError) or err == errno.EACCES:
                result["translation"] = "Python was denied access to read or write to a file or folder."
                result["why"] = f"The file path '{getattr(exc, 'filename', '') or ''}' requires administrator/root privileges, or the file is currently locked by another program."
                result["suggestions"] = [
                    "Check if the file is currently open in another application and close it.",
                    "Ensure your user account has write/read permissions for this directory.",
                    "Try running the terminal command prompt as administrator (or using 'sudo' on Linux/macOS)."
                ]
            elif isinstance(exc, ConnectionRefusedError) or err == errno.ECONNREFUSED:
                result["translation"] = "The connection was actively refused by the target server."
                result["why"] = "No service is listening on the specified port on the target host, or a firewall is blocking access."
                result["suggestions"] = [
                    "Verify that the target server process is running and healthy.",
                    "Double-check the hostname/IP address and port number configuration.",
                    "Check local and remote firewall rules to ensure they allow traffic on this port."
                ]
            elif isinstance(exc, ConnectionResetError) or err == errno.ECONNRESET:
                result["translation"] = "The socket connection was forcibly closed by the remote server."
                result["why"] = "The remote host crashed, shut down, or reset the connection unexpectedly."
                result["suggestions"] = [
                    "Check the remote server log files for any unhandled exceptions or crash reports.",
                    "Implement a retry strategy (e.g., using `@pyerror.retry`) to re-establish the connection.",
                    "Verify if network connectivity or a proxy timeout killed the connection."
                ]
            elif err == getattr(errno, "EADDRINUSE", 98):
                result["translation"] = "The network port or address is already in use by another process."
                result["why"] = "Another program on your system is already running and listening on this exact port."
                result["suggestions"] = [
                    "Find the process utilizing this port and terminate it (e.g., netstat -ano on Windows, lsof -i :PORT on Unix).",
                    "Change the port configuration of your application to listen on a different unused port.",
                    "Wait a few seconds for the operating system to release the socket after closing a previous process."
                ]

        # Fuzzy "Did you mean?" matches go first — when available they are
        # almost always the most actionable suggestion.
        try:
            from pyerror.fuzzy import suggest_names
            fuzzy_matches = suggest_names(exc)
            if fuzzy_matches:
                result["suggestions"] = fuzzy_matches + [
                    s for s in result["suggestions"] if s not in fuzzy_matches
                ]
        except Exception:
            pass

        return result

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
                result["suggestions"] = [
                    f"Check the spelling of the attribute '{attr_name}'.",
                    "List the available attributes of this object using 'dir(object)' to see what is valid.",
                    "Confirm that the object is of the type you expect (print its type using 'type(object)')."
                ]

        # 5. NameError
        elif isinstance(exc, NameError):
            result["translation"] = "You used a variable, function, or module name that has not been defined yet."
            match_name = re.search(r"name '(.+)' is not defined", exc_msg)
            var_name = match_name.group(1) if match_name else "variable"
            
            result["why"] = f"Python searched for the name '{var_name}' in your code but couldn't find any definition for it."
            result["suggestions"] = [
                f"Check for spelling mistakes or typos in the name '{var_name}'.",
                "Ensure that you have defined the variable/function BEFORE trying to use it.",
                f"If '{var_name}' is from an external library, make sure you have imported it (e.g. 'import {var_name}' or 'from library import {var_name}').",
                "Check the scope of the variable. Variables defined inside a function cannot be accessed outside of it."
            ]
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

        return result

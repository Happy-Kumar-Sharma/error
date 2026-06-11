# error 🧠

[![PyPI Version](https://img.shields.io/pypi/v/error.svg)](https://pypi.org/project/error/)
[![Python Version](https://img.shields.io/pypi/pyversions/error.svg)](https://pypi.org/project/error/)
[![License](https://img.shields.io/github/license/Happy-Kumar-Sharma/error.svg)](https://github.com/Happy-Kumar-Sharma/error/blob/main/LICENSE)

> **Because common sense is not so common. Now it is — in Python!**
> A Python error intelligence library for learners, developers, and production systems.

Most traceback libraries just pretty-print logs. `error` understands your errors, translates them into plain English, suggests exact fixes, captures local scope details, and recovers gracefully when needed. 

It works in **two modes**:
*   **Beginner Mode**: Formatted specifically for students. Hides intimidating internal library frames, translates jargon to plain English, and explains the concepts.
*   **Power Mode**: Built for developers and production apps. Captures snapshots of local variables at the moment of failure (while masking secrets), filters tracebacks, aggregates error analytics, and formats logs into structured JSON.

---

## 🚀 Key Features

*   **Human-Readable Tracebacks**: Translates complex traceback outputs into friendly, clear, plain-English explanations.
*   **Actionable Fix Suggestions**: Generates exact, context-aware suggestions for standard Python exceptions (KeyError, TypeError, AttributeError, ValueError, and more).
*   **Decorators for Resiliency**: Includes `@retry` with exponential backoff, `@capture_locals` to snapshot scope at failure, and `@fallback` for graceful degradation.
*   **Safety Net Contexts**: Clean exception suppressing with `with ignore(...)`.
*   **Dynamic Custom Exception Factory**: Create rich, professional custom exception classes in one line with built-in templates and suggestions.
*   **Error Diff Comparison**: Visualize and explain type/value differences using `error.compare(expected, got)`.
*   **Error Analytics**: Automatically groups and counts repeated exceptions across project runs.
*   **Environment Adapting Display**: Renders beautifully colorized panels in the Terminal, interactive HTML accordion containers in **Jupyter Notebooks**, and clean JSON in **Production Logs**.

---

## 📦 Installation

Install the package via `pip`:

```bash
pip install error
```

*(Note: The package is imported as `error` in your scripts)*

---

## 🎮 Quick Start

### For Beginners (Students)
Turn on `beginner_mode` at the top of your script. Any uncaught exceptions will be output as friendly explanations.

```python
import error
error.beginner_mode(True)

# Let's trigger a NameError:
print(unknown_variable)
```

**Output in Terminal:**
```text
=== [ERROR] NameError: name 'unknown_variable' is not defined ===

💡 Error Explanation:
You used a variable, function, or module name that has not been defined yet.
Python searched for the name 'unknown_variable' in your code but couldn't find any definition for it.

🔍 Traceback (Filtered):
  File "quickstart.py", line 5 in <module>
    print(unknown_variable)

🛠️ Suggestions:
  * Check for spelling mistakes or typos in the name 'unknown_variable'.
  * Ensure that you have defined the variable/function BEFORE trying to use it.
  * If 'unknown_variable' is from an external library, make sure you have imported it.
```

---

### For Developers (Power Mode)

Enable customized error formatting with `humanize()` and configure traceback styles:

```python
import error

# Enable formatting and log tracking
error.humanize(True)
error.configure(traceback_mode="compact") # compact, full, beginner, or production
```

#### 1. Scope Variable Snapshot (`@capture_locals`)
Snapshot local variables immediately when a function fails. Secrets like tokens and passwords are automatically masked!

```python
@error.capture_locals
def calculate_ratio(total, count, api_key="secret-token-123"):
    fraction = total / count
    return fraction

calculate_ratio(10, 0)
```

#### 2. Graceful Decorators (`@retry` & `@fallback`)
Add resiliency and default values to unstable functions:

```python
# Retry calling 3 times with exponential backoff and full jitter on ConnectionError
@error.retry(tries=3, delay=1.0, backoff=2.0, jitter=True, exceptions=(ConnectionError,))
def fetch_user_data():
    # your api call logic
    pass

# Fallback gracefully instead of crashing
@error.fallback(default=[])
def load_cached_items():
    raise FileNotFoundError("Cache file missing")
    
print(load_cached_items()) # Outputs: []
```

#### 3. Safety Net Context Managers (`ignore`)
Safely ignore specific errors when executing cleanup operations:

```python
import os

# Safely ignore if file doesn't exist
with error.ignore(FileNotFoundError):
    os.remove("temporary_log.txt")
```

---

## 🛠️ Diagnostics & Utilities

### Exception Explanation (`error.explain` & `error.suggest`)
Explain caught exceptions on demand:

```python
try:
    my_dict = {"id": 1}
    val = my_dict["name"]
except KeyError as exc:
    # Get direct suggestions
    print(error.suggest(exc))
    
    # Or get details & display them (Renders beautiful HTML in Jupyter Notebooks!)
    error.explain(exc).show()
```

### Type and Value Comparison (`error.compare`)
Compare types or values and output a readable description and suggested cast:

```python
# Type mismatch comparison
error.compare(expected=int, got=str, value="42").show()
```

### Rich Custom Exception Factory (`error.create`)
Create highly informative custom exceptions instantly:

```python
UserNotFound = error.create(
    "UserNotFound",
    message="User profile with ID {user_id} was not found in database.",
    suggestions=[
        "Confirm the user ID exists in the admin dashboard.",
        "Check if the database connection is healthy.",
        "Verify caching headers."
    ]
)

raise UserNotFound(user_id=8923)
```

---

## 📊 Error Analytics & Grouping
`error` automatically logs and groups exception counts across project executions into `.error_analytics.json`. You can print this breakdown at the end of an execution, or build reports:

```python
# Fetch error analytics report
report = error.get_analytics()

# Display beautiful summary table
report.show()

# Or clear stats
error.clear_analytics()
```

---

## 🔌 Webhooks & Integrations
Notify Slack, Sentry, or send emails automatically when failures occur.

```python
# Configure credentials
error.configure_integrations(
    slack_webhook="https://hooks.slack.com/services/...",
    sentry_dsn="https://...",
    email_config={
        "host": "smtp.mailtrap.io",
        "port": 2525,
        "sender": "alerts@myproject.com",
        "recipient": "dev-ops@myproject.com",
        "username": "smtp-username",
        "password": "smtp-password"
    }
)

try:
    # Trigger an issue
    1 / 0
except ZeroDivisionError as exc:
    # Post rich details to Slack Webhook blocks
    error.notify_slack(exc)
    
    # Forward exception to Sentry
    error.notify_sentry(exc)
    
    # Send HTML diagnostic email
    error.send_email(exc)
```

---

## 🔒 Advanced Privacy Filter
In addition to local variable masking, `error` scrubs passwords, Basic Auth tokens, API keys, and Credit Card details directly from exception messages, tracebacks, and source lines.

You can register custom secrets to match:
```python
# Any local variable or text matching "auth_token" will be masked
error.add_privacy_rule("auth_token")
```

---

## 🔗 Self-Contained Sharing Links
Compresses exception data using `zlib` and `base64` to generate sharing links. Excellent for sharing diagnostic reports with other developers:

```python
try:
    my_function()
except Exception as exc:
    link = error.generate_share_link(exc)
    # Outputs: https://happy-kumar-sharma.github.io/error/viewer.html?data=eJxtz0kO...
```

---

## 📝 Markdown Report Generation
Create standard Markdown diagnostics logs for archiving or attaching to GitHub Issues/Triage tickets:

```python
try:
    load_database()
except ConnectionError as exc:
    # Save a detailed report to a markdown file
    error.generate_markdown_report(exc, file_path="logs/database_failure.md")
```

---

## 🧪 Unit Test Helpers
Assert that your custom exceptions match human-readability standards and do not leak plain-text credentials:

```python
import unittest
import error

class TestMyCode(unittest.TestCase):
    def test_custom_exception(self):
        try:
            # Code that raises UserNotFound
            raise UserNotFound(user_id=10)
        except Exception as exc:
            # 1. Assert exception has clear explanation, why description, and >= 2 suggestions
            error.assert_readable(exc, min_suggestions=2)
            
            # 2. Assert local scopes do not leak any passwords, keys, or secret keys
            error.assert_not_exposed(exc)
```

---

## ⚙️ Configuration Options

Customize behavior with `error.configure(...)`:

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `traceback_mode` | `str` | `"full"` | Traceback level: `"beginner"`, `"compact"`, `"full"`, or `"production"` (outputs JSON). |
| `mask_secrets` | `bool` | `True` | Automatically mask password/token variables in local snapshots. |
| `secret_keys` | `list` | `[...]` | Custom variable names to mask (case-insensitive substring match). |

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

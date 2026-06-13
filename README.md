# pyerror 🧠

[![PyPI Version](https://img.shields.io/pypi/v/pyerror-intel.svg)](https://pypi.org/project/pyerror-intel/)
[![Python Version](https://img.shields.io/pypi/pyversions/pyerror-intel.svg)](https://pypi.org/project/pyerror-intel/)
[![License](https://img.shields.io/github/license/Happy-Kumar-Sharma/error.svg)](https://github.com/Happy-Kumar-Sharma/error/blob/main/LICENSE)

> **Because common sense is not so common. Now it is — in Python!**
> A Python error intelligence library for learners, developers, and production systems.

`pyerror` is a complete diagnostics ecosystem that translates tracebacks, suggests fixes, captures local scope details safely, and recovers gracefully when needed. It works in the Terminal, Jupyter Notebooks, and Production environments.

---

## 📦 Installation

Install the package via `pip`:
```bash
pip install pyerror-intel
```
*(Note: Always import the library as `pyerror` in your scripts)*

---

## 🎮 Complete Functionality Reference

Below is a detailed guide on all **28 public APIs** and configurations provided by `pyerror`, categorized by feature area.

---

### 1. Core Interface

#### `pyerror.beginner_mode(enable: bool)`
Enables or disables beginner mode. Sets the traceback output to a minimalist visual panel (hiding library internals) and translates exceptions into friendly explanation blocks. Ideal for classrooms or coding bootcamps.
```python
import pyerror
pyerror.beginner_mode(True) # Turns on beginner mode

# Triggering an error:
print(x) # Raises NameError and prints simple explanation panel
```

#### `pyerror.humanize(enable: bool)`
Overrides the default `sys.excepthook` with the `pyerror` formatting console handler. Uncaught exceptions will automatically print the detailed explanation panels.
```python
import pyerror
pyerror.humanize(True) # Activates humanized excepthooks
```

#### `pyerror.configure(...)`
Configures global library parameters:
*   `traceback_mode`: `"beginner"`, `"compact"`, `"full"`, or `"production"` (JSON output).
*   `mask_secrets`: `True` / `False` to enable local variable masking.
*   `secret_keys`: list of keys to mask.
*   `hide_packages`: list of package names (e.g. `["requests"]`) to filter out of traceback stacks.
*   `git_blame`: `True` / `False` to enable git blame author attribution on user traceback frames.
```python
pyerror.configure(
    traceback_mode="compact",
    mask_secrets=True,
    secret_keys=["db_password", "auth_token"],
    hide_packages=["numpy", "pandas"]
)
```

#### `pyerror.inspect_last_error()`
A post-mortem utility for interactive REPL or Python console sessions. Inspects `sys.last_value` from the most recent crash and prints its formatted report.
```python
>>> import pyerror
>>> print(x)
NameError: name 'x' is not defined
>>> pyerror.inspect_last_error() # Prints humanized report panel for NameError
```

#### `pyerror.debug_wizard()`
Launches an interactive, text-based CLI debug wizard in your REPL/console session to troubleshoot the last active or thrown exception. It prompts you with options to translate the error, inspect captured local variables, generate sharing links, write markdown reports, or launch `pdb` for post-mortem debugging.
```python
>>> import pyerror
>>> raise ValueError("Invalid config")
>>> pyerror.debug_wizard()
# Launches interactive triage menu console
```

---

### 2. Diagnostics & On-Demand Analysis

#### `pyerror.explain(exc: BaseException)`
Returns a `DiagnosticsResult` wrapper containing translation, reason, suggestions, and source lines. Support rendering as a string or rich print.
```python
try:
    1 / 0
except ZeroDivisionError as exc:
    # Prints premium diagnostic panels (Terminal colorized)
    pyerror.explain(exc).show()
```

#### `pyerror.diagnose(exc: BaseException)`
Similar to `explain`, retrieves detailed diagnostic data and returns a `DiagnosticsResult` object. In Jupyter Notebooks, it renders interactive HTML accordion widgets automatically.
```python
# In Jupyter Notebook cell:
try:
    my_list = [1, 2]
    val = my_list[5]
except IndexError as exc:
    pyerror.diagnose(exc) # Renders responsive HTML widget in Jupyter output
```

#### `pyerror.suggest(exc: BaseException)`
Returns a Python list of strings containing actionable steps to resolve the caught exception.
```python
try:
    import invalid_library
except ModuleNotFoundError as exc:
    suggestions = pyerror.suggest(exc)
    print(suggestions)
    # Output: ["Install the module using pip...", "Verify you are running...", ...]
```

#### `pyerror.compare(expected: Any, got: Any, value: Any = None)`
Compares types or values and returns a `ComparisonResult` detailing the difference and offering code suggestions for casting or validation.
```python
# Value mismatch check
pyerror.compare(expected=int, got=str, value="100").show()
```

---

### 3. Resiliency Decorators

#### `@pyerror.capture_locals`
Decorates a function so that if it crashes, a snapshot of all local variables is captured inside the exception object (as `exc.__captured_locals__`). Secrets and keys are automatically masked.
```python
@pyerror.capture_locals
def process_data(user_id, token="secret_token"):
    result = user_id + "100" # Raises TypeError
    return result

try:
    process_data(42)
except TypeError as exc:
    print(exc.__captured_locals__)
    # Output: {'process_data': {'user_id': '42', 'token': '********'}}
```

#### `@pyerror.retry(...)`
Retries calling the decorated function on failure.
*   `tries`: Number of attempts.
*   `delay`: Wait time in seconds between retries.
*   `backoff`: Multiplier to increase delay exponentially.
*   `jitter`: `True` / `False` to randomize delay intervals (prevents thundering herds).
*   `exceptions`: Tuple of exception types to trigger retries.
```python
@pyerror.retry(tries=3, delay=1.0, backoff=2.0, jitter=True, exceptions=(ConnectionError,))
def connect_to_server():
    # Attempt network connection
    raise ConnectionError("Timeout")
```

#### `@pyerror.fallback(default, exceptions=Exception)`
Catches specified exceptions inside the decorated function and returns the provided default fallback value instead of crashing.
```python
@pyerror.fallback(default={}, exceptions=(FileNotFoundError, ValueError))
def load_config():
    raise FileNotFoundError("Config missing")

print(load_config()) # Returns: {}
```

#### `@pyerror.circuit_breaker(failure_threshold=5, recovery_timeout=60.0, exceptions=Exception)`
A decorator implementing the Circuit Breaker pattern. It tracks consecutive failures raised by the decorated function.
*   `failure_threshold`: Number of consecutive failures before the circuit opens.
*   `recovery_timeout`: Cooldown period in seconds before transitioning to half-open.
*   `exceptions`: Tuple of exception types that trigger failure tracking.
Once opened, subsequent calls instantly raise `pyerror.CircuitOpenError` without running the function. After the recovery timeout, it transitions to half-open, running a canary call to check health.
```python
@pyerror.circuit_breaker(failure_threshold=3, recovery_timeout=30.0, exceptions=(ValueError,))
def call_unstable_api():
    raise ValueError("API is down")

# After 3 failed calls, the circuit opens:
try:
    call_unstable_api()
except pyerror.CircuitOpenError as exc:
    print("Circuit is currently open, call was blocked.")

#### `@pyerror.self_healing(handler, exceptions=Exception)`
Decorates a function to catch specified exceptions, invoke a custom recovery handler, and retry the function call exactly once.
```python
def recovery_handler(exc):
    print("OAuth token expired, refreshing...")
    refresh_oauth_token()

@pyerror.self_healing(handler=recovery_handler, exceptions=(ExpiredTokenError,))
def call_protected_api():
    # triggers ExpiredTokenError on first try
    pass
```
```

---

### 4. Context Managers

#### `pyerror.ignore(*exceptions)`
Safely silences specified exceptions during code execution.
```python
import os
# Ignores FileNotFoundError if file is already deleted
with pyerror.ignore(FileNotFoundError):
    os.remove("nonexistent.txt")
```

#### `pyerror.capture_scope()`
A block-level context manager that captures all local variables initialized or modified inside a code block if an exception is raised. Variables matching secret names (like passwords, keys) are automatically masked. The captured dictionary is stored in `scope.locals` and attached to `exc.__captured_locals__`.
```python
try:
    with pyerror.capture_scope() as scope:
        db_user = "admin"
        db_password = "my-secret-password"
        result = 10 / 0
except ZeroDivisionError as exc:
    print(scope.locals)
    # Output: {'db_user': "'admin'", 'db_password': '********', 'result': ...}
```

---

### 5. Custom Exceptions

#### `pyerror.create(name: str, message: str, suggestions: list)`
Dynamically creates a custom Exception class. Supports string format parameters (`message.format(**kwargs)`) and embeds recommendations directly into the exception object.
```python
DatabaseFailure = pyerror.create(
    "DatabaseFailure",
    message="Connection lost to host: {host}",
    suggestions=["Verify network interface", "Ping database hostname"]
)

# Raise custom exception
raise DatabaseFailure(host="db.local")
```

---

### 6. Logging & Exporting Reports

#### `pyerror.integrate_logging(max_tail_lines: int = 20)`
Attaches a memory-bounded log aggregator handler (`pyerrorLogHandler`) to the Python root logger. It holds the last $N$ logs and embeds them automatically inside markdown reports, JSON tracebacks, and Jupyter HTML outputs when an exception occurs.
```python
import logging
import pyerror

pyerror.integrate_logging(max_tail_lines=15)
logging.getLogger().info("User started computation")
# Any crash after this point will include this log in JSON/HTML/Markdown outputs!
```

#### `pyerror.to_json(exc: BaseException) -> str`
Serializes the exception type, message, translation, reasons, suggestions, and traceback frames (with scrubbed variables) into a structured JSON string.
```python
try:
    1 / 0
except ZeroDivisionError as exc:
    json_log = pyerror.to_json(exc)
    print(json_log)
```

#### `pyerror.generate_markdown_report(exc: BaseException, file_path: str = None) -> str`
Generates a detailed markdown diagnostic report. If `file_path` is specified, writes the report directly to that file.
```python
try:
    db_query()
except Exception as exc:
    pyerror.generate_markdown_report(exc, file_path="triage_report.md")
```

#### `pyerror.generate_share_link(exc: BaseException) -> str`
Compresses exception data and creates a self-contained, base64-encoded URL sharing link pointing to the static exception viewer client.
```python
try:
    raise ValueError("Invalid credentials configuration")
except Exception as exc:
    link = pyerror.generate_share_link(exc)
    print("Send this link to developer chat:", link)
    # Output: https://happy-kumar-sharma.github.io/error/viewer.html?data=eJyN...
```

---

### 7. System & Analytics Tracking

#### `pyerror.get_system_info() -> dict`
Returns system specs (OS version, architecture, CPU count, memory usage) and environment variables scrubbed of passwords/keys.
```python
stats = pyerror.get_system_info()
print(stats["os_platform"]) # E.g., Windows
print(stats["memory_usage_percent"]) # E.g., 45.2
```

#### `pyerror.get_analytics()`
Retrieves the logged analytics data. Identifies recurring errors across runs, showing frequency metrics and timestamps.
```python
report = pyerror.get_analytics()
report.show() # Prints recurring exception summary table
```

#### `pyerror.clear_analytics()`
Clears all recorded exception analytics records.
```python
pyerror.clear_analytics()
```

---

### 8. Web Framework Integrations

#### `pyerror.register_flask_error_handler(app)`
Registers a global handler on a Flask application instance to catch all unhandled route exceptions and return structured JSON diagnostic responses.
```python
from flask import Flask
import pyerror

app = Flask(__name__)
pyerror.register_flask_error_handler(app)

@app.route("/")
def index():
    return 1 / 0 # Automatically caught and formatted as JSON with 500 code
```

#### `pyerror.FastAPIErrorMiddleware`
ASGI middleware class for FastAPI / Starlette applications to catch routing exceptions and return humanized JSON responses.
```python
from fastapi import FastAPI
import pyerror

app = FastAPI()
app.add_middleware(pyerror.FastAPIErrorMiddleware)
```

---

### 9. Slack, Sentry, & Email Alerts

#### `pyerror.configure_integrations(slack_webhook=None, sentry_dsn=None, email_config=None, rate_limit_seconds=None)`
Sets up notification destinations for error routing.
*   `rate_limit_seconds`: window in seconds to suppress and debounce duplicate alerts. Aggregated counts are sent automatically when the rate limit window closes.
```python
pyerror.configure_integrations(
    slack_webhook="https://hooks.slack.com/services/...",
    sentry_dsn="https://...",
    email_config={
        "host": "smtp.example.com",
        "port": 587,
        "sender": "alerts@myproject.com",
        "recipient": "admin@myproject.com",
        "username": "smtp-user",
        "password": "smtp-password"
    },
    rate_limit_seconds=300 # Debounce alerts for 5 minutes
)
```

#### `pyerror.notify_slack(exc: BaseException)`
Posts exception diagnostics to the configured Slack Webhook using Block Kit layout.
```python
try:
    1 / 0
except Exception as exc:
    pyerror.notify_slack(exc)
```

#### `pyerror.notify_sentry(exc: BaseException)`
Captures and sends the exception details to the configured Sentry DSN endpoint.
```python
try:
    1 / 0
except Exception as exc:
    pyerror.notify_sentry(exc)
```

#### `pyerror.send_email(exc: BaseException)`
Compiles and sends a structured HTML report email containing the exception's diagnostics and traceback.
```python
try:
    1 / 0
except Exception as exc:
    pyerror.send_email(exc)
```

---

### 10. Privacy & Security

#### `pyerror.add_privacy_rule(pattern: str)`
Registers a case-insensitive variable/text pattern. If any variable name in local snapshots or text in tracebacks matches the rule, it is replaced with `********`.
```python
pyerror.add_privacy_rule("session_token")
```

#### `pyerror.add_scrub_pattern(pattern: str, replacement: str = "********")`
Adds a custom regular expression and replacement string to scrub sensitive data (like SSNs, credit cards, or internal user names) from tracebacks.
```python
pyerror.add_scrub_pattern(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN-MASKED]")
```

#### `pyerror.add_scrub_callback(callback: Callable[[str], str])`
Registers a custom sanitization function that takes a text block and returns the cleaned text block.
```python
pyerror.add_scrub_callback(lambda text: text.replace("DUMMY_SECRET", "CLEAN"))
```

---

### 11. Unit Test Helpers

#### `pyerror.assert_readable(exc: BaseException, min_suggestions: int = 1)`
Asserts that an exception has a registered translation, why reason, and a minimum number of suggestions. Excellent for validating custom exceptions.
```python
import unittest
import pyerror

class TestCustomErrors(unittest.TestCase):
    def test_readability(self):
        exc = MyException()
        pyerror.assert_readable(exc, min_suggestions=1)
```

#### `pyerror.assert_not_exposed(exc: BaseException)`
Asserts that the exception's local snapshots (if captured) do not contain unmasked secret key values (like passwords, keys, tokens).
```python
import unittest
import pyerror

class TestSecurity(unittest.TestCase):
    def test_secrets_masked(self):
        try:
            # function with @capture_locals
            sensitive_function() 
        except Exception as exc:
            pyerror.assert_not_exposed(exc)
```

---

### 12. Fuzzy "Did you mean?" Suggestions

Typo-aware suggestions for `NameError`, `AttributeError`, `KeyError`, and `ImportError` are built into every output path (`suggest()`, `explain()`, humanized tracebacks, JSON). They match the failing name against everything actually in scope at the crash site — no configuration needed.

```python
config = {"db_host": "localhost", "db_port": 5432}
config["db_hots"]
# Suggestion: Did you mean key 'db_host' (found in `config`) instead of 'db_hots'?

import PIL
# Suggestion: `PIL` is installed via `pip install Pillow` (the import name differs from the package name).
```

You can also call the engine directly:
```python
suggestions = pyerror.suggest_names(exc)  # list[str], never raises
```

---

### 13. OpenTelemetry Integration

Attach pyerror's humanized diagnostics (translation, suggestions, scrubbed locals, fingerprint) to the active OTel span — visible in Jaeger, Tempo, Datadog, Honeycomb, etc. Requires the optional extra:

```bash
pip install pyerror-intel[otel]
```

```python
import pyerror

pyerror.otel.instrument()  # once at startup

@pyerror.otel.traced()
def charge_card(order_id):
    ...
```

The excepthook, Flask handler, and FastAPI middleware automatically enrich the current span when an exception is recorded — no extra wiring needed. Every call degrades to a silent no-op when OpenTelemetry is not installed.

#### `pyerror.fingerprint(exc) -> str`
Stable 16-char grouping hash built from exception type + normalized message (hex addresses, IDs, UUIDs, and paths stripped) + crash location. Two crashes of the same bug with different user IDs fingerprint identically — use it to cluster recurrences.

---

### 14. AI-Powered Explanations (`pyerror.ai_explain`)

Optional LLM-powered explanation and fix suggestion. Strictly opt-in: nothing is ever sent anywhere unless you call it yourself with a key (or run a local model via Ollama). All context passes through pyerror's scrubbing pipeline first, and captured locals are excluded unless you pass `include_locals=True`.

```python
try:
    risky()
except Exception as exc:
    result = pyerror.ai_explain(exc)                                # uses ANTHROPIC_API_KEY
    result = pyerror.ai_explain(exc, provider="openai")             # uses OPENAI_API_KEY
    result = pyerror.ai_explain(exc, provider="ollama", model="llama3.2")  # fully local
    result.show()
    print(result.fix_code)
```

Returns a structured `AIExplanation` (`explanation`, `root_cause`, `fix_code`, `suggestions`, `confidence`). Raises `pyerror.AIProviderError` on failure so you can fall back to the built-in rule-based `pyerror.explain()`. Zero new dependencies — stdlib `urllib` only.

---

## 🚀 v0.2.0 — The 50-Feature Release

### CLI (`pyerror …`)

```bash
pyerror run script.py [args...]    # humanized errors, persists last_error.json
pyerror report last                 # show the saved last error
pyerror analytics [--clear]         # recurring-error table
pyerror watch script.py             # re-run on file save
pyerror doctor                      # environment sanity check
pyerror lookup ZeroDivisionError    # offline error encyclopedia
pyerror serve --port 8765           # tiny Flask dashboard
pyerror shellhook --shell powershell
```

### Intelligence

- **`pyerror.suggest_fix(exc)`** — unified diffs proposing the corrected line.
- **`pyerror.cluster_errors()`** — fingerprint-grouped analytics clusters.
- **`pyerror.learn(exc, note=...)` / `recall(exc)`** — local knowledge base.
- **`pyerror.search_links(exc)`** — pre-filled Stack Overflow / GitHub search URLs.
- **`pyerror.analyze_chain(exc)`** — confidence-ranked root cause for `raise … from …` chains.
- **`pyerror.format_chain(exc)`** — render exception chains as a tree.
- **`pyerror.smart_repr(value)`** — DataFrame/tensor-aware repr (shape + dtype, not value dumps).

### Diagnostics depth

- **`pyerror.flatten_async_tb(exc)`** + **`install_async_handler()`** — humanize asyncio task failures.
- **`pyerror.install_thread_hooks()`** + **`@capture_subprocess_errors`** — recover worker exceptions.
- **`with pyerror.timed_frames(): …`** — annotate exceptions with per-frame elapsed time.
- **`pyerror.snapshot_top()` / `enable()`** — `tracemalloc` top allocations on `MemoryError`.
- **`pyerror.humanize_warnings()` / `escalate([DeprecationWarning])`** — same treatment for warnings.

### Resiliency

```python
@pyerror.timeout(seconds=5)
def slow(): ...

@pyerror.bulkhead(max_concurrent=4)
def io_bound(): ...

@pyerror.dead_letter()             # append failed calls to ~/.pyerror/dead_letters.jsonl
def charge_card(order_id): ...

@pyerror.retry_rate_limited(tries=5, max_wait=120)
def call_api(): ...

@pyerror.hedge(delay=0.1, max_hedges=1)
def idempotent_read(): ...

pyerror.show_breakers()            # status table of all registered breakers

# Async variants — table stakes for FastAPI:
import pyerror
@pyerror.aretry(tries=3)
async def fetch(): ...
@pyerror.atimeout(seconds=2)
async def slow(): ...
@pyerror.acircuit_breaker(failure_threshold=3)
async def upstream(): ...

# Retry with locals diffing — see what changed between attempt 1 and 3:
@pyerror.retry(tries=3, diff_locals=True)
def flaky(): ...
```

### Observability & production

```python
from pyerror import metrics, structured_logging, budgets
metrics.instrument_analytics(); metrics.start_metrics_server(9464)
structured_logging.log_exception(exc)           # JSON-lines event
pyerror.set_budget(errors_per_hour=10)          # alert on breach
pyerror.set_sampling(rate=10, threshold=20)     # 1-in-10 over 20 occurrences
pyerror.set_release()                           # auto-detect via git short SHA
pyerror.configure_integrations(
    discord_webhook="https://...",
    teams_webhook="https://...",
    webhook_url="https://internal/...",
    pagerduty_routing_key="...",
    opsgenie_api_key="...",
)
pyerror.dashboard.serve(port=8765)              # self-hosted dashboard
```

### Framework integrations

```python
# Django (settings.py)
MIDDLEWARE = ["pyerror.django_support.PyErrorMiddleware", ...]

# Celery
from pyerror.tasks_support import install_celery_hooks
install_celery_hooks()

# AWS Lambda
@pyerror.lambda_handler
def handler(event, context): ...

# Click / argparse
@pyerror.humanize_cli
def main(): ...

# SQLAlchemy / psycopg
pyerror.explain_db_error(exc)    # rule-based DB error translator
```

### Education

```python
import pyerror
pyerror.set_language("hi")                  # KeyError -> Hindi translation
entry = pyerror.lookup("ZeroDivisionError") # offline encyclopedia, no active exc
pyerror.classroom_mode(level=1)             # gradual hints, leading questions
pyerror.quiz()                              # multiple-choice cause quiz
pyerror.configure_community(endpoint="https://your-server", enabled=True)
pyerror.share_fix(exc, "fixed by upgrading numpy")
pyerror.fetch_fixes(exc)                    # crowdsourced fix notes
```

Hindi sample for a `KeyError`:

```
व्याख्या: आपने डिक्शनरी में एक ऐसी कुंजी (key) तक पहुँचने की कोशिश की जो मौजूद नहीं है।
कारण:   जिस डिक्शनरी को आपने एक्सेस किया, उसमें यह कुंजी नहीं मिली।
सुझाव:  नीचे सुझाव देखें — तकनीकी विवरण अंग्रेज़ी में सुरक्षित रखे गए हैं।
```

### Pytest plugin & IPython magics

```bash
pytest                              # plugin auto-loads via entry point, adds a humanized section
```

```python
%load_ext pyerror.magics
%pyerror on        # turn humanize on for this session
%explain           # explain the last cell error
```

### Install extras

```bash
pip install pyerror-intel[otel,metrics,dashboard,structlog]
pip install pyerror-intel[all]
```

---

## ⚙️ Configuration Table

Configure settings anytime using `pyerror.configure(...)`.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `traceback_mode` | `str` | `"full"` | Traceback level: `"beginner"`, `"compact"`, `"full"`, or `"production"`. |
| `mask_secrets` | `bool` | `True` | Automatically mask password/token variables in local snapshots. |
| `secret_keys` | `list` | `[...]` | Custom variable names to mask (case-insensitive substring match). |
| `hide_packages` | `list` | `[]` | List of package names to filter out of traceback stacks. |
| `git_blame` | `bool` | `False` | Run git blame on user traceback frames to identify author, commit, and date details. |

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

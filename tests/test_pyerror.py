import unittest
import sys
import os
import json
import time
from unittest.mock import MagicMock, patch

# Add project root to sys.path so we can import pyerror package without installing it
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pyerror
from pyerror.suggestions import SuggestionEngine
from pyerror.formatting import Formatter
from pyerror.analytics import _tracker

class TestSuggestions(unittest.TestCase):
    def test_key_error_explanation(self):
        try:
            d = {"name": "Alice"}
            _ = d["age"]
        except KeyError as exc:
            details = SuggestionEngine.get_details(exc)
            self.assertEqual(details["name"], "KeyError")
            self.assertIn("key in a dictionary that doesn't exist", details["translation"])
            self.assertTrue(any("age" in s for s in details["suggestions"]))

    def test_type_error_explanation(self):
        try:
            _ = 5 + "10"
        except TypeError as exc:
            details = SuggestionEngine.get_details(exc)
            self.assertEqual(details["name"], "TypeError")
            self.assertIn("incompatible data types", details["translation"])

    def test_attribute_error_explanation(self):
        try:
            x = None
            _ = x.some_method()
        except AttributeError as exc:
            details = SuggestionEngine.get_details(exc)
            self.assertEqual(details["name"], "AttributeError")
            self.assertIn("object that is None", details["why"])

    def test_syntax_error_explanation(self):
        exc = SyntaxError("invalid syntax", ("test.py", 5, 10, "if x = 5:"))
        details = SuggestionEngine.get_details(exc)
        self.assertEqual(details["name"], "SyntaxError")
        self.assertIn("violates Python's writing rules", details["translation"])
        self.assertIn("line 5", details["why"])
        self.assertIn("if x = 5:", details["why"])

    def test_indentation_error_explanation(self):
        exc = IndentationError("expected an indented block", ("test.py", 3, 1, "print('hello')"))
        details = SuggestionEngine.get_details(exc)
        self.assertEqual(details["name"], "IndentationError")
        self.assertIn("indentation of your code is incorrect", details["translation"])
        self.assertIn("print('hello')", details["why"])

class TestDecorators(unittest.TestCase):
    def test_fallback(self):
        @pyerror.fallback(default="fallback_value", exceptions=(ValueError,))
        def failing_val_error():
            raise ValueError("bad value")
            
        @pyerror.fallback(default="fallback_value", exceptions=(ValueError,))
        def failing_type_error():
            raise TypeError("bad type")

        self.assertEqual(failing_val_error(), "fallback_value")
        with self.assertRaises(TypeError):
            failing_type_error()

    def test_retry(self):
        calls = 0
        @pyerror.retry(tries=3, delay=0.01, backoff=1.5, exceptions=(ValueError,))
        def retry_func():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ValueError("temporary error")
            return "success"

        res = retry_func()
        self.assertEqual(res, "success")
        self.assertEqual(calls, 3)

    def test_retry_with_jitter(self):
        calls = 0
        @pyerror.retry(tries=3, delay=0.01, backoff=1.5, jitter=True, exceptions=(ValueError,))
        def retry_func_jitter():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ValueError("temporary error")
            return "success"

        res = retry_func_jitter()
        self.assertEqual(res, "success")
        self.assertEqual(calls, 3)

    def test_capture_locals(self):
        @pyerror.capture_locals
        def calc(a, b):
            secret_key = "my-secret"
            division = a / b
            return division

        try:
            calc(10, 0)
        except ZeroDivisionError as exc:
            self.assertTrue(hasattr(exc, "__captured_locals__"))
            self.assertIn("calc", exc.__captured_locals__)
            locals_dict = exc.__captured_locals__["calc"]
            self.assertEqual(locals_dict["a"], "10")
            self.assertEqual(locals_dict["b"], "0")
            self.assertEqual(locals_dict["secret_key"], "'my-secret'")

class TestContextManagers(unittest.TestCase):
    def test_ignore(self):
        with pyerror.ignore(ZeroDivisionError):
            _ = 1 / 0
            
        # Standard exceptions should not be ignored if specified otherwise
        with self.assertRaises(ZeroDivisionError):
            with pyerror.ignore(ValueError):
                _ = 1 / 0

class TestFactory(unittest.TestCase):
    def test_custom_exception(self):
        MyException = pyerror.create(
            "MyException",
            message="Item {item_id} is invalid",
            suggestions=["Fix the item", "Reload details"]
        )
        
        try:
            raise MyException(item_id=42)
        except MyException as exc:
            self.assertEqual(str(exc), "Item 42 is invalid")
            self.assertEqual(exc.item_id, 42)
            self.assertEqual(exc.__suggestions__, ["Fix the item", "Reload details"])

class TestComparison(unittest.TestCase):
    def test_compare_types(self):
        comp = pyerror.compare(int, str)
        self.assertEqual(comp.expected_type, int)
        self.assertEqual(comp.got_type, str)
        self.assertIn("int(value)", comp.suggestion)

    def test_compare_values(self):
        comp = pyerror.compare(int, "42")
        self.assertEqual(comp.expected_type, int)
        self.assertEqual(comp.got_type, str)
        self.assertIn('int("42")', comp.suggestion)

class TestAnalytics(unittest.TestCase):
    def setUp(self):
        _tracker.clear()

    def test_recording(self):
        try:
            d = {}
            _ = d["missing"]
        except KeyError as exc:
            _tracker.record_exception(exc)

        report = pyerror.get_analytics()
        self.assertTrue(len(report.data) > 0)
        
        # Verify the key
        sig = list(report.data.keys())[0]
        self.assertIn("KeyError", sig)
        self.assertEqual(report.data[sig]["count"], 1)

class TestNewFeatures(unittest.TestCase):
    def test_json_export(self):
        try:
            1 / 0
        except ZeroDivisionError as exc:
            json_str = pyerror.to_json(exc)
            self.assertTrue(len(json_str) > 0)
            payload = json.loads(json_str)
            self.assertEqual(payload["exception"]["type"], "ZeroDivisionError")

    def test_privacy_scrub(self):
        # Default key scrubbing
        raw_msg = "api_key=secret-token-123"
        scrubbed = Formatter.scrub_text(raw_msg)
        self.assertIn("api_key=********", scrubbed)
        self.assertNotIn("secret-token-123", scrubbed)

        # Basic Auth URL scrubbing
        url = "http://admin:secretPass@localhost:8080"
        scrubbed_url = Formatter.scrub_text(url)
        self.assertIn("http://admin:********@localhost:8080", scrubbed_url)
        self.assertNotIn("secretPass", scrubbed_url)

    def test_share_link(self):
        try:
            1 / 0
        except ZeroDivisionError as exc:
            link = pyerror.generate_share_link(exc)
            self.assertTrue(link.startswith("https://happy-kumar-sharma.github.io/error/viewer.html?data="))

    def test_markdown_report(self):
        try:
            1 / 0
        except ZeroDivisionError as exc:
            report = pyerror.generate_markdown_report(exc)
            self.assertIn("# 🚨 Error intelligence Report:", report)
            self.assertIn("ZeroDivisionError", report)

    def test_testing_helpers(self):
        try:
            1 / 0
        except ZeroDivisionError as exc:
            # Should pass without assertions
            pyerror.assert_readable(exc)

        # Mocking unmasked secret variable exposure
        class MockException(Exception):
            __captured_locals__ = {"test_scope": {"password": "unmasked_password"}}

        with self.assertRaises(AssertionError):
            pyerror.assert_not_exposed(MockException())

        # Mocking masked secret variable
        class MockExceptionSafe(Exception):
            __captured_locals__ = {"test_scope": {"password": "********"}}
            
        # Should pass
        pyerror.assert_not_exposed(MockExceptionSafe())

    def test_system_info(self):
        # Inject sensitive env variables to verify scrubbing
        os.environ["DATABASE_PASSWORD"] = "extremely_secret_password_123"
        os.environ["API_KEY"] = "my_api_key_abc"
        
        info = pyerror.get_system_info()
        self.assertIn("os_platform", info)
        self.assertIn("python_version", info)
        self.assertIn("cpu_count", info)
        self.assertIn("memory_usage_percent", info)
        
        env = info["environment"]
        self.assertEqual(env.get("DATABASE_PASSWORD"), "********")
        self.assertEqual(env.get("API_KEY"), "********")
        
        # Clean up environment variables
        del os.environ["DATABASE_PASSWORD"]
        del os.environ["API_KEY"]

    def test_traceback_hide_packages(self):
        # Configure package to hide
        pyerror.configure(hide_packages=["pyerror"])
        
        # Checking formatted paths with that package
        test_path = os.path.abspath("pyerror/core.py")
        is_user = Formatter.is_user_frame(test_path)
        self.assertFalse(is_user)
        
        # Reset hide_packages configuration
        pyerror.configure(hide_packages=[])
        is_user_reset = Formatter.is_user_frame(test_path)
        # It's in the workspace, so it should be true now
        self.assertTrue(is_user_reset)

    def test_inspect_last_error(self):
        test_exc = ValueError("mock last error")
        sys.last_type = type(test_exc)
        sys.last_value = test_exc
        sys.last_traceback = None
        
        with patch("sys.stderr.write") as mock_stderr:
            pyerror.inspect_last_error()
            self.assertTrue(mock_stderr.called)
            
        # Clean up
        if hasattr(sys, "last_type"):
            del sys.last_type
        if hasattr(sys, "last_value"):
            del sys.last_value
        if hasattr(sys, "last_traceback"):
            del sys.last_traceback

    def test_web_framework_flask_mock(self):
        mock_app = MagicMock()
        with patch.dict("sys.modules", {"flask": MagicMock()}):
            pyerror.register_flask_error_handler(mock_app)
        # Assert errorhandler decorator was called for Exception
        mock_app.errorhandler.assert_called_once_with(Exception)

    def test_capture_scope(self):
        try:
            with pyerror.capture_scope() as scope:
                x_val = 500
                y_val = 0
                res = x_val / y_val
        except ZeroDivisionError as exc:
            self.assertEqual(scope.locals.get("x_val"), "500")
            self.assertEqual(scope.locals.get("y_val"), "0")
            self.assertTrue(hasattr(exc, "__captured_locals__"))
            self.assertIn("<capture_scope>", exc.__captured_locals__)
            self.assertEqual(exc.__captured_locals__["<capture_scope>"]["x_val"], "500")

    def test_circuit_breaker(self):
        calls = 0
        @pyerror.circuit_breaker(failure_threshold=3, recovery_timeout=0.1, exceptions=(ValueError,))
        def unstable_func():
            nonlocal calls
            calls += 1
            raise ValueError("bad call")

        # First 3 calls fail normally with ValueError
        for _ in range(3):
            with self.assertRaises(ValueError):
                unstable_func()

        self.assertEqual(unstable_func.__circuit_state__(), "OPEN")
        self.assertEqual(unstable_func.__circuit_failures__(), 3)

        # 4th call immediately raises CircuitOpenError without executing the function
        with self.assertRaises(pyerror.CircuitOpenError):
            unstable_func()
        self.assertEqual(calls, 3) # Function call counter should still be 3

        # Wait for recovery timeout
        time.sleep(0.15)
        self.assertEqual(unstable_func.__circuit_state__(), "OPEN") # Still OPEN until next call attempts recovery

        # Mock success path for recovery
        @pyerror.circuit_breaker(failure_threshold=2, recovery_timeout=0.1, exceptions=(ValueError,))
        def recovery_func(should_fail):
            if should_fail:
                raise ValueError("fail")
            return "ok"

        # Fail twice to open circuit
        for _ in range(2):
            with self.assertRaises(ValueError):
                recovery_func(should_fail=True)

        # Wait for timeout
        time.sleep(0.15)

        # Successful call clears circuit
        res = recovery_func(should_fail=False)
        self.assertEqual(res, "ok")
        self.assertEqual(recovery_func.__circuit_state__(), "CLOSED")

    def test_spelling_suggestions(self):
        # Trigger spelling match on missing import
        exc = NameError("name 'cos' is not defined")
        details = SuggestionEngine.get_details(exc)
        self.assertTrue(any("math" in s for s in details["suggestions"]))

        # Trigger spelling match on a defined local variable
        def dummy_scope():
            my_spelling_variable = 100
            # Simulating a NameError referencing it incorrectly
            tb_frame = sys._getframe()
            raise NameError("name 'my_spelling_var' is not defined")

        try:
            dummy_scope()
        except NameError as exc:
            details = SuggestionEngine.get_details(exc)
            self.assertTrue(any("my_spelling_variable" in s for s in details["suggestions"]))

    def test_os_error_translations(self):
        # Permission Error test
        exc = PermissionError(13, "Permission denied", "test_file.txt")
        details = SuggestionEngine.get_details(exc)
        self.assertIn("denied access", details["translation"])
        self.assertIn("administrator", details["suggestions"][-1])

        # Connection Refused test
        exc2 = ConnectionRefusedError(111, "Connection refused")
        details2 = SuggestionEngine.get_details(exc2)
        self.assertIn("actively refused", details2["translation"])

    def test_debug_wizard(self):
        test_exc = ValueError("mock last error")
        sys.last_type = type(test_exc)
        sys.last_value = test_exc
        sys.last_traceback = None
        
        # Test choice 6 (Exit)
        with patch("builtins.input", return_value="6"), patch("sys.stdout.write") as mock_stdout:
            pyerror.debug_wizard()
            
        # Clean up
        if hasattr(sys, "last_type"):
            del sys.last_type
        if hasattr(sys, "last_value"):
            del sys.last_value

    def test_themes_configuration(self):
        try:
            pyerror.configure(theme="nord")
            exc = ValueError("test theme")
            # Should render using Nord colors if Rich is used
            rendered = Formatter.format_cli(exc)
            self.assertTrue(len(rendered) > 0)
        finally:
            pyerror.configure(theme="dark")

class TestCoverageExpansion(unittest.TestCase):
    def test_core_configure_validation(self):
        with self.assertRaises(ValueError):
            pyerror.configure(traceback_mode="invalid_mode")
        with self.assertRaises(ValueError):
            pyerror.configure(theme="invalid_theme")

    def test_custom_excepthook_disabled(self):
        pyerror.humanize(False)
        mock_orig = MagicMock()
        with patch("pyerror.core._original_excepthook", mock_orig):
            pyerror.core._custom_excepthook(ValueError, ValueError("test"), None)
            mock_orig.assert_called_once()
            
    def test_custom_excepthook_enabled_production(self):
        pyerror.humanize(True)
        pyerror.configure(traceback_mode="production")
        with patch("sys.stderr.write") as mock_stderr:
            pyerror.core._custom_excepthook(ValueError, ValueError("test"), None)
            written = "".join(call[0][0] for call in mock_stderr.call_args_list)
            self.assertIn("ValueError", written)
            self.assertIn("test", written)
        pyerror.configure(traceback_mode="full") # restore

    def test_suggestions_branch_coverage(self):
        # TypeError subscriptable
        exc1 = TypeError("'int' object is not subscriptable")
        det1 = SuggestionEngine.get_details(exc1)
        self.assertIn("not a container", det1["why"])

        # TypeError callable
        exc2 = TypeError("'str' object is not callable")
        det2 = SuggestionEngine.get_details(exc2)
        self.assertIn("as if it were a function", det2["why"])

        # FileNotFoundError
        exc3 = FileNotFoundError("No such file: config.json")
        det3 = SuggestionEngine.get_details(exc3)
        self.assertIn("could not be found", det3["translation"])

        # ModuleNotFoundError
        exc4 = ModuleNotFoundError("No module named 'requests'")
        det4 = SuggestionEngine.get_details(exc4)
        self.assertIn("requests", det4["why"])

        # TabError
        exc5 = TabError("inconsistent use of tabs and spaces", ("file.py", 1, 1, "\tprint('err')"))
        det5 = SuggestionEngine.get_details(exc5)
        self.assertIn("mixed for indenting", det5["translation"])

    def test_plain_text_formatting(self):
        exc = ValueError("plain test error")
        with patch("pyerror.formatting.RICH_AVAILABLE", False):
            rendered = Formatter.format_cli(exc)
            self.assertIn("plain test error", rendered)
            self.assertIn("ValueError", rendered)

    def test_html_traceback_generation(self):
        exc = ValueError("html test error")
        html = Formatter.format_jupyter_html(exc)
        self.assertIn("html test error", html)
        self.assertIn("Actionable Suggestions", html)

    def test_debug_wizard_full_flow(self):
        try:
            raise ValueError("test wizard")
        except ValueError as e:
            test_exc = e
        test_exc.__captured_locals__ = {"scope1": {"password": "********", "var1": "100"}}
        sys.last_value = test_exc
        
        # Test choice 1, then 6 (Exit)
        with patch("builtins.input", side_effect=["1", "6"]), patch("sys.stdout.write"):
            pyerror.debug_wizard()

        # Test choice 2, then 6
        with patch("builtins.input", side_effect=["2", "6"]), patch("sys.stdout.write"):
            pyerror.debug_wizard()

        # Test choice 3, then 6
        with patch("builtins.input", side_effect=["3", "6"]), patch("sys.stdout.write"):
            pyerror.debug_wizard()

        # Test choice 4, then 6
        with patch("builtins.input", side_effect=["4", "test_report.md", "6"]), \
             patch("sys.stdout.write"), \
             patch("pyerror.wizard.generate_markdown_report") as mock_report:
            pyerror.debug_wizard()
            mock_report.assert_called_once()

        # Test choice 5, then 6
        with patch("builtins.input", side_effect=["5", "6"]), \
             patch("sys.stdout.write"), \
             patch("pdb.post_mortem") as mock_pdb:
            pyerror.debug_wizard()
            self.assertTrue(mock_pdb.called)

        # Test choice invalid option, then choice 6
        with patch("builtins.input", side_effect=["99", "6"]), patch("sys.stdout.write"):
            pyerror.debug_wizard()

        if hasattr(sys, "last_value"):
            del sys.last_value

    def test_flask_middleware_execution(self):
        mock_app = MagicMock()
        handler_callback = None
        def mock_errorhandler(exc_class):
            def decorator(func):
                nonlocal handler_callback
                handler_callback = func
                return func
            return decorator
        mock_app.errorhandler = mock_errorhandler
        
        mock_flask = MagicMock()
        mock_flask.jsonify = MagicMock(side_effect=lambda x: (x, 500))
        
        with patch.dict("sys.modules", {"flask": mock_flask}):
            pyerror.register_flask_error_handler(mock_app)
            
            self.assertIsNotNone(handler_callback)
            mock_exc = ValueError("flask route failure")
            with patch("pyerror.formatting.Formatter.format_json", return_value="{}"):
                resp, code = handler_callback(mock_exc)
                self.assertEqual(code, 500)

    def test_fastapi_middleware_execution(self):
        import importlib
        mock_base = MagicMock()
        class MockBaseHTTPMiddleware:
            def __init__(self, app, dispatch=None):
                self.app = app
                self.dispatch_func = dispatch
        mock_base.BaseHTTPMiddleware = MockBaseHTTPMiddleware
        mock_responses = MagicMock()
        
        class MockJSONResponse:
            def __init__(self, status_code, content):
                self.status_code = status_code
                self.content = content
                
        mock_responses.JSONResponse = MockJSONResponse
        
        with patch.dict("sys.modules", {
            "starlette": MagicMock(),
            "starlette.middleware": MagicMock(),
            "starlette.middleware.base": mock_base,
            "starlette.responses": mock_responses
        }):
            import pyerror.frameworks
            importlib.reload(pyerror.frameworks)
            
            mock_app = MagicMock()
            middleware = pyerror.frameworks.FastAPIErrorMiddleware(mock_app)
            
            async def mock_call_next(req):
                raise ValueError("fastapi route failure")
                
            with patch("pyerror.formatting.Formatter.format_json", return_value="{}"):
                import asyncio
                loop = asyncio.get_event_loop()
                response = loop.run_until_complete(middleware.dispatch(MagicMock(), mock_call_next))
                self.assertEqual(response.status_code, 500)
                
            # Reload again to restore default stub state
            importlib.reload(pyerror.frameworks)

    def test_integrations_alert_triggers(self):
        from pyerror import integrations
        integrations._rate_limit_seconds = None
        integrations._alert_history.clear()
        integrations._alert_suppressed_counts.clear()
        pyerror.configure_integrations(
            slack_webhook="https://hooks.slack.com/services/test",
            sentry_dsn="https://test@sentry.io/1",
            email_config={
                "host": "localhost",
                "port": 25,
                "sender": "sender@test.com",
                "recipient": "rec@test.com"
            }
        )
        
        mock_exc = ValueError("alerts test")
        mock_sentry_sdk = MagicMock()
        mock_sentry_sdk.Hub.current.client = None
        
        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch.dict("sys.modules", {"sentry_sdk": mock_sentry_sdk}), \
             patch("smtplib.SMTP") as mock_smtp:
            
            pyerror.notify_slack(mock_exc)
            pyerror.notify_sentry(mock_exc)
            pyerror.send_email(mock_exc)
            
            self.assertTrue(mock_urlopen.called)
            self.assertTrue(mock_sentry_sdk.capture_exception.called)
            self.assertTrue(mock_smtp.called)

class TestAdvancedFeatures(unittest.TestCase):
    def test_alert_rate_limiting_slack(self):
        from pyerror import integrations
        pyerror.configure_integrations(
            slack_webhook="https://hooks.slack.com/services/test",
            rate_limit_seconds=10
        )
        
        # Reset rate limit states manually to ensure clean test
        integrations._alert_history.clear()
        integrations._alert_suppressed_counts.clear()

        try:
            raise ValueError("test rate limit")
        except ValueError as e:
            exc = e

        with patch("urllib.request.urlopen") as mock_urlopen:
            # First call: triggers webhook
            mock_urlopen.return_value.__enter__.return_value.status = 200
            res1 = pyerror.notify_slack(exc)
            self.assertTrue(res1)
            self.assertEqual(mock_urlopen.call_count, 1)

            # Second call (immediate duplicate): gets suppressed
            res2 = pyerror.notify_slack(exc)
            self.assertFalse(res2)
            self.assertEqual(mock_urlopen.call_count, 1)
            
            # Fast-forward time manually by modifying history timestamp
            sig = integrations._get_exception_signature(exc)
            integrations._alert_history[sig] -= 15

            # Third call: triggers webhook and includes duplicate message
            res3 = pyerror.notify_slack(exc)
            self.assertTrue(res3)
            self.assertEqual(mock_urlopen.call_count, 2)
            
            # Verify body payload passed to urllib request includes the suppressed warning
            call_args = mock_urlopen.call_args[0][0]
            payload_data = json.loads(call_args.data.decode("utf-8"))
            self.assertIn("was suppressed 1 times", payload_data["blocks"][1]["text"]["text"])

        # Reset rate limit seconds
        pyerror.configure_integrations(rate_limit_seconds=None)

    def test_git_blame_attribution(self):
        pyerror.configure(git_blame=True)
        
        # Mock git blame porcelain output
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = (
            "a1b2c3d4 1 1 1\n"
            "author Test Author\n"
            "author-mail <test@author.com>\n"
            "author-time 1776268800\n"
        )
        
        try:
            raise ValueError("test blame")
        except ValueError as e:
            exc = e

        with patch("subprocess.run", return_value=mock_proc):
            rendered = Formatter.format_cli(exc)
            self.assertIn("Test Author", rendered)
            self.assertIn("test@author.com", rendered)
            self.assertIn("a1b2c3d4", rendered)

            plain_rendered = Formatter._format_cli_plain(exc, SuggestionEngine.get_details(exc), Formatter.extract_frames(exc), "full", True, [])
            self.assertIn("[Git Blame]: Test Author (<test@author.com>) | Commit: a1b2c3d4", plain_rendered)

        pyerror.configure(git_blame=False)

    def test_contextual_log_aggregation(self):
        import logging
        from pyerror.logging_handler import get_recent_logs
        
        from pyerror import logging_handler
        pyerror.integrate_logging(max_tail_lines=5)
        
        # Clear log history for clean state
        if logging_handler._global_handler:
            logging_handler._global_handler.clear()

        test_logger = logging.getLogger("test_pyerror_logger")
        test_logger.warning("Confidential test event message")

        recent = get_recent_logs()
        self.assertTrue(any("Confidential test event message" in log for log in recent))

        try:
            raise ValueError("test logs serialize")
        except ValueError as e:
            exc = e

        # Test JSON serialization contains logs
        serialized_json = pyerror.to_json(exc)
        self.assertIn("Confidential test event message", serialized_json)

        # Test HTML representation contains logs
        html = Formatter.format_jupyter_html(exc)
        self.assertIn("Confidential test event message", html)
        self.assertIn("Recent Application Logs", html)

        # Clean up
        if logging_handler._global_handler:
            logging_handler._global_handler.clear()

    def test_custom_pii_sanitization(self):
        pyerror.add_scrub_pattern(r"MY_SECRET_KEY_\d+", "[SCRUBBED_KEY]")
        pyerror.add_scrub_callback(lambda text: text.replace("UNSAFE_VALUE", "SAFE_VALUE"))

        res = Formatter.scrub_text("This is MY_SECRET_KEY_123 and UNSAFE_VALUE")
        self.assertEqual(res, "This is [SCRUBBED_KEY] and SAFE_VALUE")

    def test_self_healing_decorator(self):
        recovery_runs = 0
        def my_recovery(exc):
            nonlocal recovery_runs
            recovery_runs += 1

        calls = 0
        @pyerror.self_healing(handler=my_recovery, exceptions=(ValueError,))
        def unstable_action():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("transient error")
            return "ok"

        with patch("sys.stderr.write"):
            result = unstable_action()
            self.assertEqual(result, "ok")
            self.assertEqual(calls, 2)
            self.assertEqual(recovery_runs, 1)

        # Healing handler raises exception: retry is aborted
        def failing_recovery(exc):
            raise RuntimeError("recovery failed")

        calls_fail = 0
        @pyerror.self_healing(handler=failing_recovery, exceptions=(ValueError,))
        def action_fail():
            nonlocal calls_fail
            calls_fail += 1
            raise ValueError("bad error")

        with patch("sys.stderr.write"), self.assertRaises(ValueError):
            action_fail()

if __name__ == "__main__":
    unittest.main()

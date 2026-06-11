import unittest
import sys
import os
import json
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
        pyerror.register_flask_error_handler(mock_app)
        # Assert errorhandler decorator was called for Exception
        mock_app.errorhandler.assert_called_once_with(Exception)

if __name__ == "__main__":
    unittest.main()

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

if __name__ == "__main__":
    unittest.main()

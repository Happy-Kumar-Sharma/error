"""Tests for the intelligence features: fuzzy matching, OTel integration, ai_explain."""
import os
import sys
import unittest

# Add project root to sys.path so we can import pyerror package without installing it
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pyerror
from pyerror import ai, fuzzy, otel
from pyerror.suggestions import SuggestionEngine

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    HAS_OTEL_SDK = True
except ImportError:
    HAS_OTEL_SDK = False


class TestFuzzySuggestions(unittest.TestCase):
    def assert_suggested(self, suggestions, must_contain):
        joined = " | ".join(suggestions)
        self.assertIn(must_contain, joined, f"got {suggestions!r}")

    def test_name_error_local_typo(self):
        def case():
            user_count = 42
            total_items = 10
            return user_cont + total_items  # noqa: F821
        try:
            case()
        except NameError as exc:
            self.assert_suggested(fuzzy.suggest_names(exc), "user_count")

    def test_name_error_case_mismatch(self):
        def case():
            MyValue = 1
            return myvalue  # noqa: F821
        try:
            case()
        except NameError as exc:
            self.assert_suggested(fuzzy.suggest_names(exc), "MyValue")

    def test_attribute_error_builtin_type(self):
        try:
            "hello".uper()
        except AttributeError as exc:
            self.assert_suggested(fuzzy.suggest_names(exc), ".upper")

    def test_attribute_error_custom_object(self):
        class Order:
            def __init__(self):
                self.total_amount = 99
                self.customer_id = 7
        try:
            Order().total_ammount
        except AttributeError as exc:
            self.assert_suggested(fuzzy.suggest_names(exc), "total_amount")

    def test_key_error_dict_in_scope(self):
        def case():
            config = {"db_host": "x", "db_port": 5432, "timeout_seconds": 30}
            return config["db_hots"]
        try:
            case()
        except KeyError as exc:
            suggestions = fuzzy.suggest_names(exc)
            self.assert_suggested(suggestions, "db_host")
            # Should also name which mapping the key was found in
            self.assert_suggested(suggestions, "config")

    def test_import_error_install_alias(self):
        try:
            import sklearn  # noqa: F401
        except ImportError as exc:
            self.assert_suggested(fuzzy.suggest_names(exc), "scikit-learn")
        else:
            self.skipTest("sklearn is installed in this environment")

    def test_never_raises_on_odd_input(self):
        class Weird(Exception):
            pass
        self.assertEqual(fuzzy.suggest_names(Weird("x")), [])
        # Non-string KeyError must not crash
        fuzzy.suggest_names(KeyError(123))
        # Exception with no traceback must not crash
        fuzzy.suggest_names(NameError("name 'foo' is not defined"))

    def test_integrated_into_suggestion_engine(self):
        """Fuzzy matches should be prepended by SuggestionEngine.get_details."""
        def case():
            settings = {"db_host": "x", "db_port": 5432}
            return settings["db_hots"]
        try:
            case()
        except KeyError as exc:
            details = SuggestionEngine.get_details(exc)
            self.assertIn("db_host", details["suggestions"][0])
            # pyerror.suggest() goes through the same path
            self.assertIn("db_host", pyerror.suggest(exc)[0])


class TestOtelIntegration(unittest.TestCase):
    def test_fingerprint_stability(self):
        """Same bug with different volatile ids must fingerprint identically."""
        def boom(uid):
            raise ValueError("user {} not found at 0xDEADBEEF".format(uid))
        fps = []
        for uid in (1234567, 9876543):
            try:
                boom(uid)
            except ValueError as exc:
                fps.append(otel.fingerprint(exc))
        self.assertEqual(fps[0], fps[1])
        self.assertEqual(len(fps[0]), 16)

    def test_fingerprint_differs_for_different_errors(self):
        try:
            raise ValueError("bad value")
        except ValueError as exc1:
            fp1 = otel.fingerprint(exc1)
        try:
            raise TypeError("bad type")
        except TypeError as exc2:
            fp2 = otel.fingerprint(exc2)
        self.assertNotEqual(fp1, fp2)

    def test_record_exception_noop_without_span(self):
        try:
            raise RuntimeError("outside any span")
        except RuntimeError as exc:
            # Must not raise; returns False when no span is recording
            result = otel.record_exception(exc)
        self.assertFalse(result)

    @unittest.skipUnless(HAS_OTEL_SDK, "opentelemetry-sdk not installed")
    def test_traced_decorator_enriches_span(self):
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        self.assertTrue(otel.OTEL_AVAILABLE)
        otel.instrument()

        @otel.traced()
        def checkout(order_id):
            items = {"sku_1": 2}
            return items["sku_2"]

        with self.assertRaises(KeyError):
            checkout(101)

        spans = exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.status.status_code.name, "ERROR")
        events = [e for e in span.events if e.name == "exception"]
        self.assertTrue(events, "no exception event recorded")
        attrs = dict(events[0].attributes)
        self.assertIn("pyerror.fingerprint", attrs)
        self.assertEqual(len(attrs["pyerror.fingerprint"]), 16)
        self.assertGreaterEqual(attrs["pyerror.exception_chain_depth"], 1)
        self.assertIn("pyerror.suggestions", attrs)


class TestAIExplain(unittest.TestCase):
    def test_missing_api_key_raises_provider_error(self):
        try:
            raise TypeError("can only concatenate str (not 'int') to str")
        except TypeError as exc:
            with self.assertRaises(ai.AIProviderError):
                ai.ai_explain(exc, provider="anthropic", api_key="")

    def test_unknown_provider_raises(self):
        with self.assertRaises(ai.AIProviderError):
            ai.ai_explain(ValueError("x"), provider="grok")

    def test_context_builder_includes_type_and_traceback(self):
        try:
            raise TypeError("can only concatenate str (not 'int') to str")
        except TypeError as exc:
            ctx = ai._build_context(exc, include_locals=False)
        self.assertIn("TypeError", ctx)
        self.assertIn("Traceback", ctx)

    def test_context_is_scrubbed(self):
        """Secrets in the exception message must be masked before leaving the process."""
        try:
            raise ValueError("connection failed with password=hunter2")
        except ValueError as exc:
            ctx = ai._build_context(exc, include_locals=False)
        self.assertNotIn("hunter2", ctx)
        self.assertIn("********", ctx)

    def test_locals_excluded_by_default(self):
        @pyerror.capture_locals
        def case():
            card_number = "4111111111111111"
            raise ValueError("boom")
        try:
            case()
        except ValueError as exc:
            ctx_default = ai._build_context(exc, include_locals=False)
            ctx_opted_in = ai._build_context(exc, include_locals=True)
        self.assertNotIn("card_number", ctx_default)
        self.assertIn("card_number", ctx_opted_in)


if __name__ == "__main__":
    unittest.main()

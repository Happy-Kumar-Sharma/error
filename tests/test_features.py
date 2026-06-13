"""End-to-end test suite for the v0.2.0 feature set.

Each TestCase exercises a feature group; everything that touches the
filesystem uses tempfile, and any network call is mocked.
"""
import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pyerror
from pyerror.analytics import AnalyticsTracker


# ---------------------------------------------------------------------------
# Intelligence
# ---------------------------------------------------------------------------

class TestFixDiff(unittest.TestCase):
    def test_returns_none_when_no_source(self):
        # `exec` from a string has no real source file; suggest_fix should not crash
        try:
            exec("undefined_name")
        except NameError as exc:
            result = pyerror.suggest_fix(exc)
        self.assertTrue(result is None or hasattr(result, "diff"))


class TestClustering(unittest.TestCase):
    def test_clusters_normalize_volatile_ids(self):
        with tempfile.TemporaryDirectory() as td:
            t = AnalyticsTracker(filename=os.path.join(td, ".a.json"))
            for uid in (1234567, 9876543):
                try:
                    raise ValueError("user {} not found at 0xDEADBEEF".format(uid))
                except ValueError as exc:
                    t.record_exception(exc)
            clusters = pyerror.cluster_errors(t.data)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].count, 2)


class TestKnowledgeBase(unittest.TestCase):
    def test_learn_recall_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            kb = os.path.join(td, "kb.json")
            try:
                raise ValueError("boom")
            except ValueError as exc:
                pyerror.learn(exc, note="fixed by upgrading numpy", kb_path=kb)
                notes = pyerror.recall(exc, kb_path=kb)
            self.assertTrue(any("upgrading numpy" in n.get("note", "") for n in notes))


class TestWebLinks(unittest.TestCase):
    def test_links_include_type_no_secrets(self):
        try:
            raise ValueError("connection failed with password=hunter2")
        except ValueError as exc:
            links = pyerror.search_links(exc)
        self.assertIn("ValueError", links["stackoverflow"])
        self.assertNotIn("hunter2", links["stackoverflow"])
        self.assertNotIn("hunter2", links["github_issues"])


class TestRootCause(unittest.TestCase):
    def test_explicit_cause_picked_as_origin(self):
        try:
            try:
                raise KeyError("missing")
            except KeyError as inner:
                raise RuntimeError("wrap") from inner
        except RuntimeError as exc:
            report = pyerror.analyze_chain(exc)
        # The deepest link should be the explicit cause (KeyError).
        self.assertTrue(any(getattr(link, "explicit", False) for link in report.links))


class TestChainViz(unittest.TestCase):
    def test_format_chain_shows_both_links(self):
        try:
            try:
                raise KeyError("k")
            except KeyError as inner:
                raise RuntimeError("outer") from inner
        except RuntimeError as exc:
            text = pyerror.format_chain(exc)
        self.assertIn("KeyError", text)
        self.assertIn("RuntimeError", text)


class TestSmartRepr(unittest.TestCase):
    def test_handles_huge_list(self):
        rep = pyerror.smart_repr(list(range(5000)))
        self.assertIn("5000", rep)

    def test_tensor_duck_typing(self):
        class FakeTensor:
            shape = (3, 4)
            dtype = "float32"
        FakeTensor.__module__ = "torch.nn"
        rep = pyerror.smart_repr(FakeTensor())
        self.assertTrue("shape" in rep or "Tensor" in rep or "(3, 4)" in rep)


# ---------------------------------------------------------------------------
# Runtime capture
# ---------------------------------------------------------------------------

class TestAsyncTb(unittest.TestCase):
    def test_flatten_removes_asyncio_frames(self):
        async def inner():
            raise ValueError("boom")
        try:
            asyncio.run(inner())
        except ValueError as exc:
            frames = pyerror.flatten_async_tb(exc)
        self.assertTrue(all("asyncio" not in f.filename.lower() for f in frames))


class TestThreadHooks(unittest.TestCase):
    def test_install_and_uninstall(self):
        pyerror.install_thread_hooks()
        try:
            self.assertTrue(callable(threading.excepthook))
        finally:
            pyerror.uninstall_thread_hooks()

    def test_capture_subprocess_errors_wraps_into_remote_error(self):
        @pyerror.capture_subprocess_errors
        def worker(x):
            return 1 / x

        with self.assertRaises(pyerror.RemoteError) as cm:
            worker(0)
        self.assertEqual(cm.exception.remote_type, "ZeroDivisionError")
        self.assertIn("worker", cm.exception.__remote_traceback__)


class TestFrameTiming(unittest.TestCase):
    def test_timed_frames_annotates(self):
        try:
            with pyerror.timed_frames():
                def inner():
                    raise ValueError("boom")
                inner()
        except ValueError as exc:
            timings = getattr(exc, "__frame_timings__", None)
        self.assertTrue(timings)


class TestMemwatch(unittest.TestCase):
    def test_snapshot_top_returns_strings(self):
        import tracemalloc
        tracemalloc.start()
        try:
            data = [b"x" * 1024 for _ in range(50)]
            top = pyerror.snapshot_top(top_n=3)
            self.assertTrue(all(isinstance(s, str) for s in top))
        finally:
            tracemalloc.stop()


class TestWarnings(unittest.TestCase):
    def test_explain_deprecation_warning(self):
        details = pyerror.explain_warning(DeprecationWarning, "old API")
        self.assertEqual(details["name"], "DeprecationWarning")
        self.assertIn("phased out", details["translation"])

    def test_escalate_turns_into_error(self):
        import warnings as warnings_mod
        with warnings_mod.catch_warnings():
            pyerror.escalate(UserWarning)
            with self.assertRaises(UserWarning):
                warnings_mod.warn("boom", UserWarning)


# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------

class TestRetryDiffLocals(unittest.TestCase):
    def test_diff_locals_records_attempts(self):
        attempts_counter = {"n": 0}

        @pyerror.retry(tries=3, delay=0.01, diff_locals=True)
        def flaky():
            attempts_counter["n"] += 1
            x = attempts_counter["n"]  # noqa: F841
            raise ValueError("attempt {}".format(attempts_counter["n"]))

        with self.assertRaises(ValueError) as cm:
            flaky()
        attempts = getattr(cm.exception, "__retry_attempts__", None)
        self.assertTrue(attempts and len(attempts) == 3)


class TestCircuitBreaker(unittest.TestCase):
    def test_persistence_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            state_path = os.path.join(td, "cb.json")

            @pyerror.circuit_breaker(failure_threshold=2, recovery_timeout=60.0,
                                     name="testcb", persist=state_path)
            def f():
                raise RuntimeError("nope")

            for _ in range(2):
                try:
                    f()
                except RuntimeError:
                    pass
            with open(state_path) as fh:
                state = json.load(fh)
            self.assertEqual(state["state"], "OPEN")

    def test_breakers_registry(self):
        @pyerror.circuit_breaker(failure_threshold=3, name="reg_test_breaker")
        def g():
            return 1
        g()
        snap = pyerror.breakers()
        self.assertIn("reg_test_breaker", snap)


class TestTimeoutBulkhead(unittest.TestCase):
    def test_timeout_raises_humanized(self):
        @pyerror.timeout(seconds=0.05)
        def slow():
            time.sleep(0.5)

        with self.assertRaises(BaseException) as cm:
            slow()
        self.assertTrue(hasattr(cm.exception, "__translation__"))

    def test_bulkhead_rejects_over_capacity(self):
        gate = threading.Event()

        @pyerror.bulkhead(max_concurrent=1, max_waiting=0, name="bk_test")
        def held():
            gate.wait(timeout=0.5)

        t = threading.Thread(target=held)
        t.start()
        try:
            time.sleep(0.05)  # let the worker grab the slot
            with self.assertRaises(pyerror.BulkheadFullError):
                held()
        finally:
            gate.set()
            t.join(timeout=1.0)


class TestDeadLetter(unittest.TestCase):
    def test_writes_and_replays(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dl.jsonl")

            @pyerror.dead_letter(path=path)
            def f(x):
                raise ValueError("nope: " + str(x))

            with self.assertRaises(ValueError):
                f(42)
            records = pyerror.replay(path=path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["args"], [42])
            self.assertEqual(records[0]["exc_type"], "ValueError")
            self.assertTrue(records[0]["fingerprint"])


class TestRateLimitRetry(unittest.TestCase):
    def test_honors_retry_after(self):
        calls = {"n": 0}

        @pyerror.retry_rate_limited(tries=3, max_wait=1.0, base_delay=0.01)
        def f():
            calls["n"] += 1
            if calls["n"] < 2:
                exc = Exception("rate limited")
                exc.retry_after = 0.01
                raise exc
            return "ok"

        self.assertEqual(f(), "ok")


class TestHedge(unittest.TestCase):
    def test_hedge_returns_first_success(self):
        @pyerror.hedge(delay=0.05, max_hedges=1)
        def quick():
            return 7

        self.assertEqual(quick(), 7)


# ---------------------------------------------------------------------------
# Async (aio)
# ---------------------------------------------------------------------------

class TestAio(unittest.TestCase):
    def test_aretry_retries_coroutine(self):
        calls = {"n": 0}

        @pyerror.aretry(tries=3, delay=0.01)
        async def f():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError("flap")
            return "ok"

        self.assertEqual(asyncio.run(f()), "ok")

    def test_atimeout_raises_humanized(self):
        @pyerror.atimeout(0.05)
        async def slow():
            await asyncio.sleep(0.5)

        with self.assertRaises(BaseException) as cm:
            asyncio.run(slow())
        self.assertTrue(hasattr(cm.exception, "__translation__"))

    def test_aretry_rejects_sync_function(self):
        with self.assertRaises(TypeError):
            pyerror.aretry()(lambda: None)


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

class TestAnalyticsExtras(unittest.TestCase):
    def test_fingerprint_and_release_stamped(self):
        with tempfile.TemporaryDirectory() as td:
            t = AnalyticsTracker(filename=os.path.join(td, ".a.json"))
            from pyerror import analytics as ana
            ana._RELEASE = "v1.2.3"
            try:
                try:
                    raise ValueError("hi")
                except ValueError as exc:
                    t.record_exception(exc)
            finally:
                ana._RELEASE = None
            record = next(iter(t.data.values()))
            self.assertEqual(record.get("release"), "v1.2.3")
            self.assertTrue(record.get("fingerprint"))

    def test_releases_summary(self):
        summary = pyerror.releases_summary()
        self.assertIsInstance(summary, dict)


class TestNotifiers(unittest.TestCase):
    def setUp(self):
        pyerror.configure_integrations(
            discord_webhook="https://discord.example/x",
            teams_webhook="https://teams.example/x",
            webhook_url="https://webhook.example/x",
            pagerduty_routing_key="pdkey",
            opsgenie_api_key="oggie",
        )

    def _make_exc(self):
        try:
            raise ValueError("connection failed with password=hunter2")
        except ValueError as e:
            return e

    @patch("urllib.request.urlopen")
    def test_discord_scrubbed(self, urlopen):
        urlopen.return_value.__enter__.return_value.status = 200
        ok = pyerror.notify_discord(self._make_exc())
        self.assertTrue(ok)
        sent = urlopen.call_args[0][0].data.decode()
        self.assertNotIn("hunter2", sent)

    @patch("urllib.request.urlopen")
    def test_pagerduty_payload(self, urlopen):
        urlopen.return_value.__enter__.return_value.status = 202
        pyerror.notify_pagerduty(self._make_exc())
        body = json.loads(urlopen.call_args[0][0].data.decode())
        self.assertEqual(body["routing_key"], "pdkey")
        self.assertEqual(body["event_action"], "trigger")

    @patch("urllib.request.urlopen")
    def test_teams_no_secret(self, urlopen):
        urlopen.return_value.__enter__.return_value.status = 200
        pyerror.notify_teams(self._make_exc())
        self.assertNotIn("hunter2", urlopen.call_args[0][0].data.decode())

    @patch("urllib.request.urlopen")
    def test_webhook(self, urlopen):
        urlopen.return_value.__enter__.return_value.status = 200
        pyerror.notify_webhook(self._make_exc())
        self.assertTrue(urlopen.called)


class TestMetrics(unittest.TestCase):
    def test_record_no_crash_without_prometheus(self):
        try:
            raise ValueError("hi")
        except ValueError as exc:
            pyerror.metrics.record(exc)  # never raises


class TestStructuredLogging(unittest.TestCase):
    def test_log_exception_emits_json(self):
        import logging
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        log = logging.getLogger("pyerror")
        log.addHandler(handler)
        log.setLevel("ERROR")
        try:
            try:
                raise ValueError("x")
            except ValueError as exc:
                event = pyerror.log_exception(exc)
        finally:
            log.removeHandler(handler)
        self.assertEqual(event["error_type"], "ValueError")
        self.assertTrue(event["fingerprint"])


class TestBudgets(unittest.TestCase):
    def test_breach_fires_once(self):
        clock = {"t": 0.0}

        def now():
            return clock["t"]

        breached: list = []
        pyerror.set_budget(2, on_breach=lambda s: breached.append(s), _time_fn=now)
        try:
            for _ in range(5):
                clock["t"] += 0.1
                pyerror.budgets.record(None)
            self.assertEqual(len(breached), 1)
        finally:
            pyerror.clear_budget()


class TestDashboard(unittest.TestCase):
    def test_create_app_renders_index(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, ".a.json")
            t = AnalyticsTracker(filename=path)
            try:
                raise ValueError("dashtest")
            except ValueError as exc:
                t.record_exception(exc)
            app = pyerror.dashboard.create_app(analytics_path=path)
            client = app.test_client()
            resp = client.get("/")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"pyerror", resp.data)
            api = client.get("/api/analytics")
            self.assertEqual(api.status_code, 200)


# ---------------------------------------------------------------------------
# Framework integrations
# ---------------------------------------------------------------------------

class TestDBErrors(unittest.TestCase):
    def test_unique_violation(self):
        class FakeDBError(Exception):
            pass
        exc = FakeDBError('duplicate key value violates unique constraint "users_email_key"')
        details = pyerror.explain_db_error(exc)
        self.assertEqual(details["name"], "UniqueViolation")
        self.assertIn("users_email_key", details["why"])

    def test_fk_violation_enrich(self):
        class FakeDBError(Exception):
            pass
        exc = FakeDBError('insert or update on table "orders" violates foreign key constraint "fk_customer"')
        pyerror.enrich_db_error(exc)
        self.assertIn("fk_customer", exc.__why__)


class TestServerless(unittest.TestCase):
    def test_lambda_handler_emits_json_and_reraises(self):
        @pyerror.lambda_handler
        def handler(event, context):
            raise ValueError("boom")

        ctx = MagicMock(aws_request_id="abc", function_name="test")
        saved = sys.stdout
        sys.stdout = io.StringIO()
        try:
            with self.assertRaises(ValueError):
                handler({}, ctx)
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = saved
        record = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(record["error_type"], "ValueError")
        self.assertEqual(record["aws_request_id"], "abc")
        self.assertTrue(record["fingerprint"])

    def test_lambda_handler_no_reraise_returns_response(self):
        @pyerror.lambda_handler(reraise=False, response={"statusCode": 500})
        def handler(event, context):
            raise RuntimeError("nope")

        saved = sys.stdout
        sys.stdout = io.StringIO()
        try:
            self.assertEqual(handler({}, MagicMock(aws_request_id=None, function_name=None)),
                             {"statusCode": 500})
        finally:
            sys.stdout = saved


class TestCliApps(unittest.TestCase):
    def test_humanize_cli_exits_1(self):
        @pyerror.humanize_cli
        def main():
            raise ValueError("boom")

        saved = sys.stderr
        sys.stderr = io.StringIO()
        try:
            with self.assertRaises(SystemExit) as cm:
                main()
        finally:
            sys.stderr = saved
        self.assertEqual(cm.exception.code, 1)

    def test_humanize_cli_passes_through_system_exit(self):
        @pyerror.humanize_cli
        def main():
            raise SystemExit(0)

        with self.assertRaises(SystemExit) as cm:
            main()
        self.assertEqual(cm.exception.code, 0)


class TestTasksSupport(unittest.TestCase):
    def test_celery_handler_attaches_task_context(self):
        from pyerror.tasks_support import celery_task_failure_handler
        exc = ValueError("oops")
        saved = sys.stderr
        sys.stderr = io.StringIO()
        try:
            celery_task_failure_handler(
                sender=MagicMock(name="MyTask"), task_id="t-1",
                exception=exc, args=("password=hunter2",), kwargs={},
            )
        finally:
            sys.stderr = saved
        self.assertTrue(hasattr(exc, "__task_context__"))
        self.assertNotIn("hunter2", exc.__task_context__["args"])


# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------

class TestI18n(unittest.TestCase):
    def tearDown(self):
        pyerror.reset_language()

    def test_hindi_translation(self):
        pyerror.set_language("hi")
        try:
            raise KeyError("k")
        except KeyError as exc:
            details = pyerror.suggest(exc)
        # Suggestions should now start with the Hindi prefix line
        self.assertTrue(any("सुझाव" in s or "नीचे" in s for s in details))

    def test_labels(self):
        pyerror.set_language("hi")
        labs = pyerror.labels()
        self.assertEqual(labs["suggestions"], "सुझाव")

    def test_reset_restores(self):
        before = pyerror.explain(KeyError("k")).details["translation"]
        pyerror.set_language("es")
        pyerror.reset_language()
        after = pyerror.explain(KeyError("k")).details["translation"]
        self.assertEqual(before, after)


class TestEncyclopedia(unittest.TestCase):
    def test_lookup_zerodivision(self):
        entry = pyerror.lookup("ZeroDivisionError")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["name"], "ZeroDivisionError")

    def test_case_insensitive(self):
        entry = pyerror.lookup("zerodivisionerror")
        self.assertIsNotNone(entry)

    def test_search(self):
        results = pyerror.encyclopedia_search("zero")
        self.assertTrue(any("Zero" in r for r in results))

    def test_generate_markdown(self):
        text = pyerror.encyclopedia.generate_markdown()
        self.assertIn("# pyerror error encyclopedia", text)
        # Should cover at least 25 types
        self.assertGreaterEqual(text.count("## "), 25)


class TestClassroom(unittest.TestCase):
    def tearDown(self):
        pyerror.disable_classroom()

    def test_level1_hides_example(self):
        pyerror.classroom_mode(level=1)
        try:
            raise KeyError("k")
        except KeyError as exc:
            details = pyerror.explain(exc).details
        self.assertIsNone(details["example"])

    def test_level3_shows_example(self):
        pyerror.classroom_mode(level=3)
        try:
            raise KeyError("k")
        except KeyError as exc:
            details = pyerror.explain(exc).details
        self.assertIsNotNone(details["example"])

    def test_reveal_more(self):
        pyerror.classroom_mode(level=1)
        new_level = pyerror.reveal_more()
        self.assertEqual(new_level, 2)


class TestQuiz(unittest.TestCase):
    def test_scripted_correct_answer(self):
        import random as _random
        rng = _random.Random(42)
        try:
            raise KeyError("k")
        except KeyError as exc:
            # We don't know which letter is the correct one a-priori; play through.
            stream = io.StringIO()

            def fake_input(prompt):
                # Pick from the rendered options whichever matches the answer
                rendered = stream.getvalue()
                lines = [ln for ln in rendered.splitlines() if ln.strip().startswith(("A", "B", "C", "D")) and ")" in ln]
                # The right answer is the one whose text equals the translation
                from pyerror.suggestions import SuggestionEngine
                answer = SuggestionEngine.get_details(exc)["translation"]
                for ln in lines:
                    if answer.split()[0] in ln:
                        return ln.split(")")[0].strip()
                return "A"

            result = pyerror.quiz(exc, input_fn=fake_input, output=stream, rng=rng)
        self.assertIn(result.chosen, result.options)


class TestCommunitySharing(unittest.TestCase):
    def test_disabled_refuses(self):
        pyerror.configure_community(endpoint=None, enabled=False)
        try:
            raise ValueError("boom")
        except ValueError as exc:
            self.assertFalse(pyerror.share_fix(exc, "note"))

    @patch("urllib.request.urlopen")
    def test_enabled_posts_fingerprint_only(self, urlopen):
        urlopen.return_value.__enter__.return_value.status = 200
        pyerror.configure_community(endpoint="https://server.example", enabled=True)
        try:
            raise ValueError("connection failed with password=hunter2 at /var/secret/path")
        except ValueError as exc:
            pyerror.share_fix(exc, "fixed by reinstalling")
        sent = urlopen.call_args[0][0].data.decode()
        self.assertNotIn("hunter2", sent)
        self.assertNotIn("/var/secret/path", sent)
        body = json.loads(sent)
        self.assertEqual(body["exc_type"], "ValueError")
        self.assertTrue(body["fingerprint"])


# ---------------------------------------------------------------------------
# CLI / Doctor / Navigator
# ---------------------------------------------------------------------------

class TestCliRun(unittest.TestCase):
    def test_run_crashing_script(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "boom.py")
            with open(script, "w") as fh:
                fh.write("raise ValueError('crashed')\n")
            env = dict(os.environ)
            env["HOME"] = td
            env["USERPROFILE"] = td
            result = subprocess.run(
                [sys.executable, "-m", "pyerror", "run", script],
                capture_output=True, env=env, cwd=td, timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            last_error = os.path.join(td, ".pyerror", "last_error.json")
            self.assertTrue(os.path.exists(last_error),
                            "expected {} to exist; stderr={!r}".format(
                                last_error, result.stderr.decode(errors="replace")[:200]))


class TestDoctor(unittest.TestCase):
    def test_run_doctor_returns_results(self):
        results = pyerror.run_doctor(print_output=False)
        self.assertTrue(results)


class TestNavigator(unittest.TestCase):
    def test_scripted_session(self):
        try:
            raise ValueError("walk me")
        except ValueError as exc:
            captured = exc
        cmds = iter(["n", "l", "q"])
        out = io.StringIO()
        pyerror.navigate(captured, input_fn=lambda prompt: next(cmds), output=out)
        text = out.getvalue()
        self.assertIn("frame", text.lower())


class TestPytestPlugin(unittest.TestCase):
    def test_plugin_section_in_failure_output(self):
        with tempfile.TemporaryDirectory() as td:
            test_file = os.path.join(td, "test_dummy.py")
            with open(test_file, "w") as fh:
                fh.write(
                    "def test_fail():\n"
                    "    d = {'a': 1}\n"
                    "    assert d['b'] == 1\n"
                )
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-p", "pyerror.pytest_plugin",
                 "-v", "--no-header", test_file],
                capture_output=True, text=True, cwd=td, timeout=60,
            )
        self.assertIn("pyerror", result.stdout + result.stderr)


class TestMagics(unittest.TestCase):
    def test_register_with_mock_ipython(self):
        ip = MagicMock()
        from pyerror import magics
        self.assertTrue(magics.register_magics(ip))
        # Two magics should have been registered
        self.assertEqual(ip.register_magic_function.call_count, 2)


if __name__ == "__main__":
    unittest.main()

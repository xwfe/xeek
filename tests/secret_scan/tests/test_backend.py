"""只用现场拼接的公开合成字符串验证检测与输出边界。"""
from __future__ import annotations

import contextlib
import io
import logging
import sys
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backend
from backend import Backend, Hit, ScanFailure

PUBLIC = "SYNTHETIC_ONLY_NOT_VALID"
GITHUB = "ghp" + "_" + "aB7c" * 9
PEM = "-" * 5 + "BEGIN RSA PRIVATE KEY" + "-" * 5


class BackendTests(unittest.TestCase):
    def test_clean_input(self):
        with Backend() as detector:
            self.assertEqual(list(detector.scan('message = "hello world"\n')), [])

    def test_fixed_plugins_and_line_numbers(self):
        with Backend() as detector:
            hits = list(detector.scan("ordinary\n" + GITHUB + "\n" + PEM))
            self.assertEqual(len(detector.plugins), 27)
        self.assertIn(Hit("GitHubTokenDetector", 2), hits)
        self.assertIn(Hit("PrivateKeyDetector", 3), hits)
        self.assertTrue(all(set(asdict(hit)) == {"rule", "line"} for hit in hits))

    def test_network_and_verification_are_never_called(self):
        with Backend() as detector, contextlib.ExitStack() as stack:
            mocks = [stack.enter_context(patch.object(plugin, "verify", side_effect=AssertionError(PUBLIC)))
                     for plugin in detector.plugins]
            mocks += [stack.enter_context(patch(target, side_effect=AssertionError(PUBLIC)))
                      for target in ("requests.sessions.Session.request", "socket.create_connection")]
            text = "\n".join((GITHUB, PEM, "AKIA" + "B" * 16,
                              "https://synthetic:synthetic-only@example.test/"))
            self.assertTrue(list(detector.scan(text)))
            for function in mocks:
                function.assert_not_called()

    def test_normal_entropy_thresholds(self):
        value = "aB9cD8eF7gH6iJ5kL4mN3oP2qR1sT0uV"
        with Backend() as detector:
            quoted = list(detector.scan('value = "' + value + '"'))
            unquoted = list(detector.scan(value))
            low = list(detector.scan('value = "' + "a" * 40 + '"'))
        self.assertIn("Base64HighEntropyString", {hit.rule for hit in quoted})
        self.assertNotIn("Base64HighEntropyString", {hit.rule for hit in unquoted + low})

    def test_extra_prefixes_positive_and_boundary_negative(self):
        cases = (
            ("KeexGithubPat", "github" + "_pat_" + "aB" * 8, "github" + "_pat_" + "a" * 15),
            ("KeexBearerToken", "Bearer " + "aB" * 8, "Bearer " + "a" * 15),
            ("KeexOtpSeed", "otpauth" + "://totp/synthetic?secret=" + "ABCD" * 2,
             "otpauth" + "://totp/synthetic?secret=" + "ABC"),
            ("KeexEsimActivation", "LPA:" + "1$synthetic.example.test$TEST",
             "LPA:" + "1$synthetic.example.test$A"),
        )
        with Backend() as detector:
            for rule, positive, negative in cases:
                with self.subTest(rule=rule):
                    self.assertIn(rule, {hit.rule for hit in detector.scan(positive)})
                    self.assertNotIn(rule, {hit.rule for hit in detector.scan(negative)})

    def test_inline_allowlist_and_lockfile_do_not_skip(self):
        text = 'api_key = "' + PUBLIC + '" # pragma: allowlist secret'
        with Backend() as detector:
            for suffix in (".py", ".lock"):
                self.assertIn("KeywordDetector", {hit.rule for hit in detector.scan(text, suffix)})

    def test_allowed_rule_does_not_disable_other_rules(self):
        with Backend() as detector:
            hits = list(detector.scan(GITHUB + "\n" + PEM, allowed_rules={"PrivateKeyDetector"}))
        self.assertIn("GitHubTokenDetector", {hit.rule for hit in hits})
        self.assertNotIn("PrivateKeyDetector", {hit.rule for hit in hits})

    def test_unknown_rule_fails_closed(self):
        with Backend() as detector:
            with self.assertRaisesRegex(ScanFailure, "^UNKNOWN_RULE$"):
                list(detector.scan(PUBLIC, allowed_rules={"unknown"}))

    def test_backend_gets_only_safe_filename(self):
        with Backend() as detector:
            plugin = detector.plugins[0]
            with patch.object(plugin, "analyze_line", return_value=set()) as analyze:
                list(detector.scan("ordinary", "/private/" + PUBLIC + "\n"))
                self.assertEqual(analyze.call_args.kwargs["filename"], "input.txt")

    def test_detector_stdout_stderr_logs_and_exception_are_redacted(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        def broken(**_):
            print(PUBLIC)
            print(PUBLIC, file=sys.stderr)
            logging.critical(PUBLIC)
            raise ValueError(PUBLIC)
        with Backend() as detector:
            with patch.object(detector.plugins[0], "analyze_line", side_effect=broken):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(ScanFailure) as error:
                        list(detector.scan("ordinary"))
        self.assertEqual(str(error.exception), "DETECTOR_SCAN")
        self.assertTrue(error.exception.__suppress_context__)
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")

    def test_first_yield_restores_caller_streams_and_logging(self):
        stdout, stderr, level = sys.stdout, sys.stderr, logging.root.manager.disable
        with Backend() as detector:
            iterator = detector.scan(GITHUB + "\n" + PEM)
            next(iterator)
            self.assertIs(sys.stdout, stdout)
            self.assertIs(sys.stderr, stderr)
            self.assertEqual(logging.root.manager.disable, level)
            iterator.close()

    def test_initialization_failure_is_redacted(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        def broken():
            print(PUBLIC)
            raise RuntimeError(PUBLIC)
        with patch.object(backend, "_load_dependencies", side_effect=broken):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                with self.assertRaisesRegex(ScanFailure, "^DETECTOR_INIT$"):
                    with Backend():
                        self.fail("unexpected success")
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")

    def test_initialization_failure_exits_entered_settings(self):
        events = []
        class Settings:
            filters = {}
            def disable_filters(self, *_):
                pass
        @contextlib.contextmanager
        def settings(_):
            events.append("enter")
            try:
                yield Settings()
            finally:
                events.append("exit")
        with patch.object(backend, "_load_dependencies", return_value=(lambda: (), settings)):
            with self.assertRaisesRegex(ScanFailure, "^DETECTOR_INIT$"):
                Backend().__enter__()
        self.assertEqual(events, ["enter", "exit"])

    def test_dependency_metadata_version_drift_rejected(self):
        with patch.object(backend.importlib.metadata, "distribution") as distribution:
            distribution.return_value.version = "0.0.0"
            with self.assertRaisesRegex(ScanFailure, "^DETECTOR_INIT$"):
                Backend().__enter__()

    def test_preloaded_module_from_outside_project_rejected(self):
        with Backend():
            pass
        import requests
        with patch.object(requests, "__file__", "/outside-project/requests.py"):
            with self.assertRaisesRegex(ScanFailure, "^DETECTOR_INIT$"):
                Backend().__enter__()

    def test_marker_only_detector_is_not_content_identity(self):
        with Backend() as detector:
            first = list(detector.scan(PEM + "\n" + "PUBLIC_A"))
            changed = list(detector.scan(PEM + "\n" + "PUBLIC_B"))
        self.assertEqual(first, changed)
        self.assertIn(Hit("PrivateKeyDetector", 1), first)


if __name__ == "__main__":
    unittest.main()

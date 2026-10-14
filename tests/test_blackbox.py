from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

from cep.blackbox import MAX_DECLARATION, parse_declaration, run_cases, validate_cases
from cep.process import clean_env, run_process


class BlackBoxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "candidate"
        self.repo.mkdir()
        self.scratch = self.root / "protected"
        self.scratch.mkdir()
        self.case = {
            "id": "CLI-contract",
            "kind": "tests",
            "requirements": ["REQ-CLI"],
            "argv": [sys.executable, "--root", "{fixture}"],
            "fixtures": {"input.txt": "approved"},
            "exit_code": 0,
            "stdout_json": {"status": "ok"},
            "stderr_empty": True,
        }

    def outcome(self, **kwargs):
        return {
            "exit_code": 0,
            "stdout": '{"status":"ok","extra":1}',
            "stderr": "",
            "timed_out": False,
            "output_exceeded": False,
            "output_truncated": False,
            "elapsed_seconds": 0.01,
            **kwargs,
        }

    def test_declaration_rejects_ambiguous_malformed_nonfinite_and_deep_json(self):
        for text in (
            '{"policy":1,"policy":2}',
            '{"nested":{"a":1,"a":1}}',
            '{"x":NaN}',
            '{"x":Infinity}',
            '{"x":-Infinity}',
            '{"x":1e400}',
            "{broken",
            "[" * 2000 + "0" + "]" * 2000,
        ):
            with self.subTest(text=text[:60]), self.assertRaises(ValueError):
                parse_declaration(text)
        with self.assertRaises(ValueError):
            parse_declaration('"' + "x" * MAX_DECLARATION + '"')
        with self.assertRaises(ValueError):
            parse_declaration('"' + "é" * (MAX_DECLARATION // 2) + '"')

    def test_declaration_finite_float_is_plain_json_serializable(self):
        # Floats must remain ordinary JSON values for frozen policy hashing.
        parsed = parse_declaration('{"limit":1.25,"large":1e300,"enabled":true}')
        self.assertIs(type(parsed["limit"]), float)
        self.assertEqual(parsed["limit"], 1.25)
        self.assertEqual(parse_declaration('"' + "[" * 2000 + '"'), "[" * 2000)
        from cep.evidence import digest_json

        self.assertEqual(digest_json(parsed), digest_json(dict(parsed)))

    def run_case(self, executor, case=None):
        return run_cases(
            self.repo, [case or self.case], executor=executor, scratch_root=self.scratch
        )

    def test_real_json_command_fixture_substitution_and_separate_scratch(self):
        case = deepcopy(self.case)
        case["argv"] = [
            sys.executable,
            "-I",
            "-c",
            "import json,sys;from pathlib import Path;print(json.dumps({'status':Path(sys.argv[1],'input.txt').read_text()}))",
            "{fixture}",
        ]
        case["stdout_json"] = {"status": "approved"}

        def executor(argv, fixture, execution):
            self.assertEqual(argv[-1], str(fixture))
            self.assertFalse(fixture.is_relative_to(execution))
            self.assertEqual((fixture / "input.txt").read_text(), "approved")
            return run_process(argv, self.repo, 5, env=clean_env(execution))

        result = self.run_case(executor, case)
        self.assertTrue(result["passed"])
        self.assertEqual(result["checks"][0]["requirement_ids"], ["REQ-CLI"])
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_zero_exit_without_json_is_not_acceptance(self):
        for text in ("", "PASS", "[]", '{"status":"wrong"}'):
            with self.subTest(text=text):
                result = self.run_case(lambda *args: self.outcome(stdout=text))
                self.assertFalse(result["passed"])

    def test_limits_override_correct_exit_and_complete_json(self):
        for flag in ("timed_out", "output_exceeded", "output_truncated"):
            with self.subTest(flag=flag):
                result = self.run_case(lambda *args: self.outcome(**{flag: True}))
                self.assertFalse(result["passed"])
                self.assertTrue(result["outcomes"][0][flag])
                self.assertIn(flag, result["checks"][0]["detail"])
        self.assertFalse(
            self.run_case(lambda *args: self.outcome(exit_code=2))["passed"]
        )

    def test_all_capture_flags_must_be_explicit_booleans(self):
        for field in ("timed_out", "output_exceeded", "output_truncated"):
            for invalid in (None, 0, "false"):
                with self.subTest(field=field, invalid=invalid):
                    outcome = self.outcome()
                    if invalid is None:
                        outcome.pop(field)
                    else:
                        outcome[field] = invalid
                    result = self.run_case(lambda *args: outcome)
                    self.assertFalse(result["passed"])
                    self.assertIn(field, result["checks"][0]["detail"])

    def test_duplicate_keys_nonfinite_constants_and_json_type_confusion_fail(self):
        for text in (
            '{"status":"ok","status":"ok"}',
            '{"status":"ok","value":NaN}',
            '{"status":"ok","value":Infinity}',
            '{"status":"ok","value":-Infinity}',
        ):
            with self.subTest(text=text):
                self.assertFalse(
                    self.run_case(lambda *args: self.outcome(stdout=text))["passed"]
                )
        case = dict(self.case, stdout_json={"status": True})
        self.assertFalse(
            self.run_case(lambda *args: self.outcome(stdout='{"status":1}'), case)[
                "passed"
            ]
        )

    def test_fixture_changes_and_symlink_replacement_are_detected_without_following(
        self,
    ):
        outside = self.root / "outside.txt"
        outside.write_text("private sentinel")

        def replaced(argv, fixture, execution):
            (fixture / "input.txt").unlink()
            (fixture / "input.txt").symlink_to(outside)
            return self.outcome()

        result = self.run_case(replaced)
        self.assertFalse(result["passed"])
        self.assertIn("fixture tree changed", result["checks"][0]["detail"])
        self.assertEqual(outside.read_text(), "private sentinel")

        def same_bytes_new_inode(argv, fixture, execution):
            replacement = fixture / "replacement"
            replacement.write_text("approved")
            replacement.replace(fixture / "input.txt")
            return self.outcome()

        self.assertFalse(self.run_case(same_bytes_new_inode)["passed"])

    def test_explicit_mutable_fixture_and_unchanged_policy(self):
        case = dict(
            self.case,
            mutable_fixture=True,
            unchanged=False,
            fixtures={".state/config": "initial"},
        )

        def mutate(argv, fixture, execution):
            self.assertTrue(fixture.is_relative_to(execution))
            (fixture / ".state/config").write_text("updated")
            return self.outcome()

        self.assertTrue(self.run_case(mutate, case)["passed"])
        case["unchanged"] = True
        self.assertFalse(self.run_case(mutate, case)["passed"])

    def test_stderr_json_empty_and_forbidden_output_are_independent(self):
        case = dict(
            self.case,
            stderr_json={"error": "rejected"},
            stderr_empty=False,
            forbidden_output=["private sentinel"],
        )
        result = self.run_case(
            lambda *args: self.outcome(stderr='{"error":"rejected","code":2}'), case
        )
        self.assertTrue(result["passed"])
        result = self.run_case(
            lambda *args: self.outcome(
                stderr='{"error":"rejected","detail":"private sentinel"}'
            ),
            case,
        )
        self.assertFalse(result["passed"])

    def test_invalid_declarations_fail_before_executor(self):
        invalid = []
        for changed in (
            {"argv": ["python"]},
            {"argv": [sys.executable, "{fixture}/file"]},
            {"requirements": ["UNKNOWN"]},
            {"fixtures": {"../outside": "x"}},
            {"fixtures": {"a": "x", "a/b": "y"}},
            {"fixtures": {"File": "x", "file": "y"}},
            {"exit_code": True},
            {"unchanged": 1},
            {"mutable_fixture": 1},
            {"stdout_json": {"number": float("inf")}},
            {"shell": "evil"},
            {"fixtures": {"big": "x" * 1_048_577}},
        ):
            invalid.append(dict(self.case, **changed))
        for case in invalid:
            with self.subTest(case=case.get("id")):
                with self.assertRaises(ValueError):
                    validate_cases([case], ["REQ-CLI"])
        with self.assertRaises(ValueError):
            validate_cases([self.case, self.case], ["REQ-CLI"])
        with self.assertRaises(ValueError):
            validate_cases(
                [dict(self.case, fixtures={str(i): "" for i in range(129)})],
                ["REQ-CLI"],
            )
        with self.assertRaises(ValueError):
            run_cases(
                self.repo,
                [dict(self.case, requirements=None)],
                executor=lambda *args: self.fail("executor ran"),
                scratch_root=self.scratch,
            )

    def test_exception_produces_failed_case_and_outcomes_are_bounded_redacted(self):
        def failed(*args):
            raise RuntimeError("execution unavailable")

        self.assertFalse(self.run_case(failed)["passed"])
        result = self.run_case(
            lambda *args: self.outcome(stdout="ghp_privateFixtureToken" + "x" * 210000)
        )
        self.assertFalse(result["passed"])
        self.assertLessEqual(len(result["outcomes"][0]["stdout"]), 200000)
        self.assertNotIn("ghp_privateFixtureToken", result["outcomes"][0]["stdout"])


class RawSecurityOutputTests(unittest.TestCase):
    def test_token_shaped_leak_fails_before_evidence_redaction(self):
        from cep.process import run_process
        from cep.blackbox import run_cases

        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            repo, scratch = root / "repo", root / "scratch"
            repo.mkdir()
            scratch.mkdir()
            canary = "ghp_fixtureCanary123"
            case = {
                "id": "leak",
                "kind": "security",
                "requirements": ["SEC-LEAK"],
                "argv": [sys.executable, "-c", "print('" + canary + "')"],
                "exit_code": 0,
                "forbidden_output": [canary],
            }

            def execute(argv, fixture, execution):
                return run_process(argv, repo, 10, redact_output=False)

            result = run_cases(repo, [case], executor=execute, scratch_root=scratch)
            self.assertFalse(result["passed"])
            self.assertIn("forbidden output", result["checks"][0]["detail"])
            self.assertNotIn(canary, str(result))
            self.assertIn("[REDACTED]", str(result))

    def test_truncated_output_cannot_hide_an_early_leak(self):
        from cep.process import run_process
        from cep.blackbox import run_cases

        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            repo, scratch = root / "repo", root / "scratch"
            repo.mkdir()
            scratch.mkdir()
            case = {
                "id": "early-leak",
                "kind": "security",
                "requirements": ["SEC-LEAK"],
                "argv": [
                    sys.executable,
                    "-c",
                    "print('ghp_fixtureCanary123'); print('x'*210000)",
                ],
                "exit_code": 0,
                "forbidden_output": ["ghp_fixtureCanary123"],
            }

            def execute(argv, fixture, execution):
                return run_process(argv, repo, 10, redact_output=False)

            result = run_cases(repo, [case], executor=execute, scratch_root=scratch)
            self.assertFalse(result["passed"])
            self.assertIn("output_truncated", result["checks"][0]["detail"])

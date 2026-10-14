"""Fixed probe logic tests; no local UID/GID drops or root SDK execution."""

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import time
from unittest.mock import patch

from native import build_probe


class BuildProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.sdk = {
            role: {
                "root": "/sdk/" + role,
                "path": "/sdk/" + role + "/bin/" + role,
                "version": {
                    "python": "3.13.9",
                    "uv": "0.9.9",
                    "node": "24.11.1",
                    "go": "1.27.2",
                }[role],
            }
            for role in build_probe.ROLES
        }

    def receipt(self, argv, stdout=""):
        return {
            "argv": argv,
            "status": 0,
            "stdout": stdout,
            "stderr": "",
            "timed_out": False,
            "output_exceeded": False,
        }

    def report(self, mode):
        versions, builds = build_probe.commands(mode, self.sdk, "/source", "/scratch")
        roles = ["uv", "python"] if mode == "python" else [mode]
        outputs = {
            "uv": "uv 0.9.9",
            "python": "Python 3.13.9",
            "node": "v24.11.1",
            "go": "go version go1.27.2 darwin/arm64",
        }
        receipts = [
            self.receipt(argv, outputs[role]) for role, argv in zip(roles, versions)
        ]
        receipts += [self.receipt(argv) for argv in builds]
        receipts[-1]["stdout"] = json.dumps({"toolchain": mode, "answer": 42})
        return {"mode": mode, "outcomes": receipts}

    def test_inspect_never_imports_privileged_helpers_or_claims_qualification(self):
        output = io.StringIO()
        with redirect_stdout(output), patch.object(build_probe, "_helpers") as helpers:
            self.assertEqual(build_probe.main(["--inspect"]), 0)
        helpers.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertFalse(report["production_qualified"])
        self.assertEqual(report["experiment"], "not_run")

    def test_offline_commands_use_fixed_argv_and_fresh_caches(self):
        versions, builds = build_probe.commands(
            "python", self.sdk, "/source", "/scratch"
        )
        self.assertIn("--offline", builds[0])
        self.assertIn("--no-project", builds[0])
        self.assertIn("--no-managed-python", builds[0])
        versions, builds = build_probe.commands("go", self.sdk, "/source", "/scratch")
        self.assertIn("-p=1", builds[0])
        env = build_probe.environment(Path("/scratch"), self.sdk)
        self.assertEqual(env["CGO_ENABLED"], "0")
        self.assertEqual(env["GOTOOLCHAIN"], "local")
        self.assertEqual(env["GOMAXPROCS"], "2")
        self.assertEqual(env["GOPROXY"], "off")
        self.assertEqual(env["HOME"], "/scratch/home")
        self.assertNotIn("SSH_AUTH_SOCK", env)
        self.assertNotIn("NODE_OPTIONS", env)

    def test_receipts_bind_sdk_version_fixed_commands_and_expected_json(self):
        for mode in ("python", "node", "go"):
            report = self.report(mode)
            build_probe.verify_outcomes(mode, self.sdk, report)
            for change in ("timed_out", "output_exceeded", "stderr", "argv", "stdout"):
                broken = deepcopy(report)
                broken["outcomes"][-1][change] = {
                    "timed_out": True,
                    "output_exceeded": True,
                    "stderr": "unexpected",
                    "argv": ["/unapproved/sdk"],
                    "stdout": '{"answer":42}',
                }[change]
                with (
                    self.subTest(mode=mode, change=change),
                    self.assertRaises((ValueError, RuntimeError)),
                ):
                    build_probe.verify_outcomes(mode, self.sdk, broken)
            report["outcomes"][0]["stdout"] = "wrong SDK release"
            with self.assertRaises(RuntimeError):
                build_probe.verify_outcomes(mode, self.sdk, report)

    def test_expired_budget_never_spawns_even_after_pipe_setup(self):
        with (
            patch.object(build_probe.time, "monotonic", return_value=120),
            patch.object(build_probe.os, "posix_spawn") as spawn,
        ):
            with self.assertRaises(RuntimeError):
                build_probe._execute(["/sdk/go"], {}, 120)
            spawn.assert_not_called()
        # The second check closes the time-of-check gap immediately before spawn.
        with (
            patch.object(build_probe.time, "monotonic", side_effect=[119, 120]),
            patch.object(build_probe.os, "posix_spawn") as spawn,
        ):
            with self.assertRaises(RuntimeError):
                build_probe._execute(["/sdk/go"], {}, 120)
            spawn.assert_not_called()

    def test_drop_precedes_dispatch_and_failures_stop_future_commands(self):
        class Helpers:
            dropped = False

            def drop(self, uid):
                self.dropped = True

        helpers = Helpers()
        for failure in (
            {"status": 3},
            {"status": None},
            {"timed_out": True},
            {"output_exceeded": True},
            {"stderr": "failed"},
        ):
            helpers.dropped = False
            frames = []

            def execute(argv, env, deadline):
                self.assertTrue(helpers.dropped)
                return dict(self.receipt(argv, "uv 0.9.9"), **failure)

            with ExitStack() as stack:
                stack.enter_context(
                    patch.object(build_probe, "_helpers", return_value=helpers)
                )
                stack.enter_context(patch.object(build_probe.os, "chdir"))
                executor = stack.enter_context(
                    patch.object(build_probe, "_execute", side_effect=execute)
                )
                stack.enter_context(
                    patch.object(
                        build_probe,
                        "_write_progress",
                        side_effect=lambda fd, value: frames.append(deepcopy(value)),
                    )
                )
                build_probe._worker(
                    62001, "python", self.sdk, Path("/source"), Path("/scratch"), 999
                )
            self.assertEqual(executor.call_count, 1)
            self.assertEqual(len(frames), 1)
            self.assertEqual(len(frames[0]["outcomes"]), 1)

    def test_complete_under_limit_output_never_discards_junk_before_expected_json(self):
        # Ordinary local UID only: this verifies capture semantics, not UID drop.
        text = "unexpected canary" + "x" * 12000 + '{"toolchain":"node","answer":42}'
        result = build_probe._execute(
            [
                sys.executable,
                "-I",
                "-c",
                "import sys;sys.stdout.write(" + repr(text) + ")",
            ],
            {"PATH": os.defpath},
            time.monotonic() + 5,
        )
        self.assertEqual(result["status"], 0)
        self.assertFalse(result["output_exceeded"])
        self.assertEqual(result["stdout"], text)
        report = self.report("node")
        report["outcomes"][-1]["stdout"] = result["stdout"]
        with self.assertRaises(ValueError):
            build_probe.verify_outcomes("node", self.sdk, report)

    def test_malformed_success_receipt_types_cannot_pass(self):
        valid = self.report("node")["outcomes"][0]
        self.assertTrue(build_probe._receipt_ok(valid))
        for key, value in (
            ("status", False),
            ("status", 0.0),
            ("timed_out", 0),
            ("output_exceeded", 0),
            ("stderr", None),
            ("stdout", None),
        ):
            self.assertFalse(build_probe._receipt_ok(dict(valid, **{key: value})))

    def test_delayed_descendant_diagnostics_are_captured_after_direct_child_exit(self):
        # Fixed, self-terminating ordinary-UID process; no privileged probe/drop.
        script = (
            "import os,time;pid=os.fork();"
            "\nif pid: os._exit(0)"
            "\ntime.sleep(0.12);os.write(2,b'delayed descendant diagnostic');os._exit(0)"
        )
        receipt = build_probe._execute(
            [sys.executable, "-I", "-c", script],
            {"PATH": os.defpath},
            time.monotonic() + 5,
        )
        self.assertEqual(receipt["status"], 0)
        self.assertFalse(receipt["timed_out"])
        self.assertEqual(receipt["stderr"], "delayed descendant diagnostic")
        self.assertFalse(build_probe._receipt_ok(receipt))

    def test_parent_report_capture_waits_for_eof_after_wrapper_exit(self):
        frame = {"mode": "node", "outcomes": [self.report("node")["outcomes"][0]]}
        helpers = type(
            "Helpers",
            (),
            {"inventory_uid": lambda self, uid: [], "InventoryError": RuntimeError},
        )()
        selections = []

        def select_report(reads, *args):
            selections.append(reads)
            # The exited wrapper's writer has not reached EOF at first poll.
            return (reads if len(selections) in (2, 3) else [], [], [])

        evidence = self.root / "evidence"
        evidence.mkdir()
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(build_probe, "_helpers", return_value=helpers)
            )
            stack.enter_context(patch.object(build_probe.os, "chown"))
            forks = stack.enter_context(
                patch.object(build_probe.os, "fork", side_effect=[991, 992])
            )
            stack.enter_context(
                patch.object(
                    build_probe.os, "waitpid", side_effect=lambda pid, flags: (pid, 0)
                )
            )
            stack.enter_context(
                patch.object(build_probe.select, "select", side_effect=select_report)
            )
            stack.enter_context(
                patch.object(
                    build_probe.os,
                    "read",
                    side_effect=[(json.dumps(frame) + "\n").encode(), b""],
                )
            )
            verifier = stack.enter_context(
                patch.object(
                    build_probe,
                    "verify_outcomes",
                    side_effect=RuntimeError("incomplete fixed receipts"),
                )
            )
            result = build_probe.run_build(62001, "node", self.sdk, self.root, evidence)
        self.assertEqual(forks.call_count, 2)
        self.assertGreaterEqual(len(selections), 3)
        self.assertEqual(result["report"]["outcomes"], frame["outcomes"])
        self.assertFalse(result["timed_out"])
        self.assertFalse(result["passed"])
        verifier.assert_called_once()

    def test_worker_deadline_prevents_dispatch_and_retains_prior_receipt(self):
        frames = []
        helpers = type("Helpers", (), {"drop": lambda self, uid: None})()
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(build_probe, "_helpers", return_value=helpers)
            )
            stack.enter_context(patch.object(build_probe.os, "chdir"))
            stack.enter_context(
                patch.object(
                    build_probe.time, "monotonic", side_effect=[0, 1, 121, 121]
                )
            )
            executor = stack.enter_context(
                patch.object(
                    build_probe,
                    "_execute",
                    side_effect=lambda argv, *args: self.receipt(argv, "uv 0.9.9"),
                )
            )
            stack.enter_context(
                patch.object(
                    build_probe,
                    "_write_progress",
                    side_effect=lambda fd, value: frames.append(deepcopy(value)),
                )
            )
            build_probe._worker(
                62001, "python", self.sdk, Path("/source"), Path("/scratch"), 999
            )
        self.assertEqual(executor.call_count, 1)
        self.assertEqual(len(frames[-1]["outcomes"]), 2)
        self.assertEqual(frames[-1]["outcomes"][0]["status"], 0)
        self.assertTrue(frames[-1]["outcomes"][1]["timed_out"])

    def test_progress_cannot_lose_prior_receipts_and_preserves_terminal_error(self):
        first = self.report("node")["outcomes"][0]
        frames = [
            {"mode": "node", "outcomes": [first]},
            {"error": "fixed child failed"},
        ]
        report = build_probe._parse_progress(
            ("\n".join(json.dumps(frame) for frame in frames) + "\n").encode()
        )
        self.assertEqual(report["outcomes"], [first])
        self.assertEqual(report["error"], "fixed child failed")
        frames = [
            {"mode": "node", "outcomes": [first]},
            {"mode": "node", "outcomes": []},
        ]
        with self.assertRaises(ValueError):
            build_probe._parse_progress(
                ("\n".join(json.dumps(frame) for frame in frames) + "\n").encode()
            )

    def test_fixture_sources_are_readonly_and_have_no_dependency_fetches(self):
        source = self.root / "source"
        build_probe._sources(source, "node")
        self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o555)
        for file in source.iterdir():
            self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o444)
        self.assertIn("spawnSync", (source / "build.mjs").read_text())
        self.assertIn("shell:false", (source / "build.mjs").read_text())
        self.assertNotIn("npm", (source / "build.mjs").read_text())

    def test_sdk_tree_rejects_unprivileged_or_mutable_staging(self):
        root = self.root / "sdk"
        root.mkdir()
        (root / "binary").write_text("not an SDK")
        with self.assertRaises(RuntimeError):
            build_probe.sdk_tree_digest(root)

import math
import os
from pathlib import Path
import tempfile
import unittest

from cep.worker_tools import MAX_FILE, WorkerTools


class FakeSandbox:
    def __init__(self):
        self.calls = []

    def run(self, argv, repo, scratch, timeout, **kwargs):
        self.calls.append((argv, repo, scratch, timeout, kwargs))
        return {
            "stdout": "command output",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "elapsed_seconds": 0.01,
        }


class WorkerToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.sandbox = FakeSandbox()
        self.broker = WorkerTools(
            self.repo, self.root / "scratch", writable=True, sandbox=self.sandbox
        )

    def test_file_roundtrip_and_listing(self):
        response = self.broker.call(
            "cep_apply_file", {"path": "src/demo.py", "content": "print('hello')\n"}
        )
        self.assertEqual(response["bytes"], 15)
        self.assertEqual(
            self.broker.call("cep_read_file", {"path": "src/demo.py"})["content"],
            "print('hello')\n",
        )
        self.assertEqual(
            self.broker.call("cep_list_files", {})["files"], ["src/demo.py"]
        )

    def test_readonly_cannot_write_or_expand_capabilities(self):
        broker = WorkerTools(self.repo, self.root / "review", sandbox=self.sandbox)
        with self.assertRaises(ValueError):
            broker.call("cep_apply_file", {"path": "file", "content": "x"})
        with self.assertRaises(ValueError):
            broker.call("cep_grant_permissions", {})
        broker.call("cep_run_command", {"argv": ["python", "-V"]})
        self.assertFalse(self.sandbox.calls[-1][-1]["writable"])

    def test_path_escape_symlinks_hardlinks_and_protected_config(self):
        secret = self.root / "secret"
        secret.write_text("private")
        (self.repo / "link").symlink_to(secret)
        (self.repo / "directory").symlink_to(self.root, target_is_directory=True)
        os.link(secret, self.repo / "hardlink")
        for path in (
            "../secret",
            str(secret),
            "link",
            "directory/secret",
            "hardlink",
            ".git/config",
            ".codex/config.toml",
        ):
            with self.subTest(path=path):
                with self.assertRaises((ValueError, OSError)):
                    self.broker.call("cep_read_file", {"path": path})
                with self.assertRaises((ValueError, OSError)):
                    self.broker.call(
                        "cep_apply_file", {"path": path, "content": "changed"}
                    )
        self.assertEqual(secret.read_text(), "private")
        self.assertNotIn(
            "directory/secret", self.broker.call("cep_list_files", {})["files"]
        )

    def test_protected_test_writes_denied(self):
        for path in (
            "tests/protected.txt",
            "nested/__tests__/case.ts",
            "test_security.py",
            "slug_test.go",
            "app.test.tsx",
            "openspec/change.md",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.broker.call(
                    "cep_apply_file", {"path": path, "content": "weakened"}
                )

    def test_case_variant_administrative_paths_are_rejected_before_access(self):
        for path in (".CoDeX/config.toml", ".GiT/config", "nested/.CeP/bindings.json"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.broker.call("cep_read_file", {"path": path})
                with self.assertRaises(ValueError):
                    self.broker.call(
                        "cep_apply_file", {"path": path, "content": "changed"}
                    )
        for namespace in (".CoDeX", ".GiT", ".CeP"):
            (self.repo / namespace).mkdir()
            (self.repo / namespace / "private").write_text("private")
        self.assertEqual(self.broker.call("cep_list_files", {})["files"], [])

    def test_case_alias_cannot_overwrite_existing_configuration(self):
        config = self.repo / ".codex/config.toml"
        config.parent.mkdir()
        config.write_text("protected config")
        with self.assertRaises(ValueError):
            self.broker.call(
                "cep_apply_file", {"path": ".CoDeX/config.toml", "content": "changed"}
            )
        self.assertEqual(config.read_text(), "protected config")

    def test_authoritative_guidance_remains_readable_but_case_variant_writes_denied(
        self,
    ):
        skill = self.repo / ".agents/skills/example/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("approved guidance")
        self.assertEqual(
            self.broker.call(
                "cep_read_file", {"path": ".agents/skills/example/SKILL.md"}
            )["content"],
            "approved guidance",
        )
        for path in (
            ".AgEnTs/skills/example/SKILL.md",
            "nested/.AGENTS/agent.md",
            "AGENTS.md",
            "nested/agents.MD",
            "deep/AgEnTs.OvErRiDe.Md",
            "OpEnSpEc/change.md",
            "TeStS/protected.py",
            "TEST_security.py",
            "app.SPEC.TS",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.broker.call(
                    "cep_apply_file", {"path": path, "content": "weakened"}
                )
        self.assertEqual(skill.read_text(), "approved guidance")

    def test_binary_and_oversized_files_rejected(self):
        (self.repo / "binary").write_bytes(b"\xff\x00")
        with self.assertRaises(ValueError):
            self.broker.call("cep_read_file", {"path": "binary"})
        (self.repo / "large").write_bytes(b"x" * (MAX_FILE + 1))
        with self.assertRaises(ValueError):
            self.broker.call("cep_read_file", {"path": "large"})
        with self.assertRaises(ValueError):
            self.broker.call(
                "cep_apply_file", {"path": "file", "content": "x" * (MAX_FILE + 1)}
            )

    def test_commands_have_direct_argv_and_bounded_timeout(self):
        self.broker.call(
            "cep_run_command",
            {"argv": ["echo", "$(not-expanded)"], "timeout_seconds": 2},
        )
        self.assertEqual(self.sandbox.calls[-1][0], ["echo", "$(not-expanded)"])
        for timeout in (math.nan, math.inf, 0, -1, 31, True):
            with self.assertRaises(ValueError):
                self.broker.call(
                    "cep_run_command", {"argv": ["echo"], "timeout_seconds": timeout}
                )
        with self.assertRaises(ValueError):
            self.broker.call("cep_run_command", {"argv": "echo hello"})

    def test_minimal_mcp_and_error_keys(self):
        init = self.broker.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(init["result"]["serverInfo"]["name"], "cep-worker-tools")
        listing = self.broker.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        self.assertEqual(len(listing["result"]["tools"]), 4)
        response = self.broker.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "cep_read_file", "arguments": {"path": "../secret"}},
            }
        )
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(response["result"]["content"][0]["type"], "text")
        self.assertIsNone(
            self.broker.handle(
                {"jsonrpc": "2.0", "method": "notifications/initialized"}
            )
        )
        ping = self.broker.handle({"jsonrpc": "2.0", "id": 4, "method": "ping"})
        self.assertEqual(ping["result"], {})
        unknown = self.broker.handle(
            {"jsonrpc": "2.0", "id": 5, "method": "shutdown-job"}
        )
        self.assertEqual(unknown["error"]["code"], -32601)

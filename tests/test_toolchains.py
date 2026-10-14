"""Executable identity and exact-file authority regressions."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from cep.toolchains import executable_digest, validate_bindings
from cep.worker_tools import WorkerTools


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.binary = self.root / "tool"
        self.binary.write_bytes(b"operator tool")
        self.binary.chmod(0o755)
        self.binding = {
            "name": "example",
            "executable": str(self.binary),
            "sha256": executable_digest(self.binary),
        }

    def test_changed_binary_invalidates_binding(self):
        self.assertEqual(validate_bindings([self.binding], self.repo), (self.binary,))
        self.binary.write_bytes(b"changed tool")
        with self.assertRaisesRegex(ValueError, "changed"):
            validate_bindings([self.binding], self.repo)

    def test_candidate_owned_and_writable_tools_rejected(self):
        owned = self.repo / "tool"
        shutil.copy2(self.binary, owned)
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_bindings([{**self.binding, "executable": str(owned)}], self.repo)
        self.binary.chmod(0o777)
        with self.assertRaisesRegex(ValueError, "writable"):
            validate_bindings([self.binding], self.repo)

    def test_binding_cannot_expand_to_directory_or_symlink(self):
        alias = self.root / "alias"
        alias.symlink_to(self.binary)
        for path in (alias, self.root):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_bindings(
                    [{**self.binding, "executable": str(path)}], self.repo
                )

    @unittest.skipUnless(
        sys.platform == "darwin" and shutil.which("node"), "native Node boundary"
    )
    def test_broker_node_access_does_not_grant_adjacent_files_or_forks(self):
        binary = Path(shutil.which("node")).resolve()
        secret = self.root / "outside"
        secret.write_text("protected")
        worker = WorkerTools(self.repo, self.root / "scratch", readable_tools=(binary,))
        source = (
            "const fs=require('fs'),cp=require('child_process'); let denied=false; try{fs.readFileSync("
            + repr(str(secret))
            + ")}catch(e){denied=e.code==='EPERM'};if(!denied)process.exit(2); const child=cp.spawnSync(process.execPath,['-e','process.exit(0)']);if(!child.error||child.error.code!=='EPERM')process.exit(3); console.log('contained')"
        )
        result = worker.call("cep_run_command", {"argv": [str(binary), "-e", source]})
        self.assertEqual(result["exit_code"], 0, result)
        self.assertEqual(result["stdout"].strip(), "contained")
        self.assertEqual(secret.read_text(), "protected")

    @unittest.skipUnless(sys.platform == "darwin", "native hard-link boundary")
    def test_readable_binding_cannot_be_hardlinked_into_writable_root(self):
        from cep.sandbox import NativeSandbox

        before = self.binary.read_bytes()
        code = (
            "import os; from pathlib import Path; os.link("
            + repr(str(self.binary))
            + ", 'alias'); Path('alias').write_text('changed')"
        )
        result = NativeSandbox().run(
            [sys.executable, "-I", "-c", code],
            self.repo,
            self.root / "scratch",
            10,
            writable=True,
            readable=(self.binary,),
        )
        self.assertNotEqual(result["exit_code"], 0)
        self.assertEqual(self.binary.read_bytes(), before)
        self.assertEqual(self.binary.stat().st_nlink, 1)

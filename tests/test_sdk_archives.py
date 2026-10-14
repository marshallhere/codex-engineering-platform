"""Exercise the exact workflow extractor without downloads, SDKs or root authority.

The two extractor byte limits are reduced only in the compiled test AST for
three tiny fixtures. The checked-in workflow and its production limits stay
unchanged. Ownership attestation is mocked; these are archive safety tests.
"""

import ast
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import stat
import tarfile
import tempfile
import textwrap
from types import SimpleNamespace
import unicodedata
import unittest
from unittest.mock import Mock


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/native-toolchain-experiments.yml"
)


def extractor_program(byte_cap=None):
    """Select the reviewed extractor, never the privileged workflow driver."""
    text = WORKFLOW.read_text()
    marker = "      - name: Verify pinned archives and stage immutable SDK files\n"
    if text.count(marker) != 1:
        raise AssertionError("expected exactly one SDK staging workflow step")
    step = text.split(marker, 1)[1].split("      - name: ", 1)[0]
    if step.count("<<'PY'\n") != 1 or step.count("\n          PY\n") != 1:
        raise AssertionError("expected one bounded Python staging heredoc")
    source = step.split("<<'PY'\n", 1)[1].split("\n          PY\n", 1)[0]
    tree = ast.parse(textwrap.dedent(source))
    helpers = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "name_checked"
    ]
    loops = [
        node
        for node in tree.body
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Call)
        and isinstance(node.iter.func, ast.Attribute)
        and isinstance(node.iter.func.value, ast.Name)
        and node.iter.func.value.id == "archives"
    ]
    if len(helpers) != 1 or len(loops) != 1:
        raise AssertionError(
            "workflow extractor structure changed; review test binding"
        )
    tree = ast.Module(body=helpers + loops, type_ignores=[])
    if byte_cap is not None:

        class ScaledLimit(ast.NodeTransformer):
            replacements = 0

            def visit_Constant(self, node):
                if node.value == 1_500_000_000:
                    self.replacements += 1
                    return ast.copy_location(ast.Constant(byte_cap), node)
                return node

        scaler = ScaledLimit()
        tree = scaler.visit(tree)
        if not scaler.replacements:
            raise AssertionError("test byte cap no longer binds the workflow limit")
    return compile(ast.fix_missing_locations(tree), str(WORKFLOW), "exec")


CASES = [
    ("parent_traversal", [("python/../escape", "file", b"x")], {}),
    ("absolute_member", [("/escape", "file", b"x")], {}),
    ("outbound_symlink", [("python/bin/python3.13", "symlink", "../../../escape")], {}),
    ("absolute_symlink", [("python/bin/python3.13", "symlink", "/etc/passwd")], {}),
    ("cyclic_alias", [("python/a", "symlink", "b"), ("python/b", "symlink", "a")], {}),
    ("setuid_member", [("python/bin/python3.13", "setuid", b"x")], {}),
    ("case_alias", [("python/Case", "file", b"x"), ("python/case", "file", b"y")], {}),
    ("special_member", [("python/fifo", "fifo", b"")], {}),
    ("hash_mismatch", [("python/bin/python3.13", "file", b"x")], {}),
    (
        "safe_internal_alias",
        [
            ("python/bin/python3.13", "file", b"x"),
            ("python/bin/python", "symlink", "python3.13"),
        ],
        {"accept": True, "expected_files": 2, "expected_bytes": 2},
    ),
    (
        "safe_internal_hardlink",
        [
            ("python/bin/python3.13", "file", b"x"),
            ("python/bin/python", "hardlink", "python/bin/python3.13"),
        ],
        {"accept": True, "expected_files": 2, "expected_bytes": 2},
    ),
    (
        "alias_amplification",
        [
            ("python/base", "file", b"x" * 80),
            ("python/a", "symlink", "base"),
            ("python/b", "hardlink", "python/base"),
            ("python/c", "symlink", "a"),
        ],
        {"cap": 96},
    ),
    (
        "implicit_case_alias",
        [("python/Foo/a", "file", b"x"), ("python/foo/b", "file", b"y")],
        {},
    ),
    (
        "explicit_after_implicit_case_alias",
        [("python/Foo/a", "file", b"x"), ("python/foo", "directory", b"")],
        {},
    ),
    (
        "file_then_implicit_directory",
        [("python/foo", "file", b"x"), ("python/foo/bar", "file", b"y")],
        {},
    ),
    (
        "implicit_directory_then_file",
        [("python/foo/bar", "file", b"x"), ("python/foo", "file", b"y")],
        {},
    ),
    (
        "unicode_implicit_alias",
        [("python/caf\u00e9/a", "file", b"x"), ("python/cafe\u0301/b", "file", b"y")],
        {},
    ),
    (
        "consistent_implicit_directory",
        [("python/foo/a", "file", b"x"), ("python/foo/b", "file", b"y")],
        {"accept": True, "expected_files": 2, "expected_bytes": 2},
    ),
    (
        "explicit_after_same_implicit_directory",
        [("python/foo/a", "file", b"x"), ("python/foo", "directory", b"")],
        {"accept": True, "expected_files": 1, "expected_bytes": 1},
    ),
    (
        "exact_materialized_limit",
        [("python/base", "file", b"x" * 48), ("python/alias", "symlink", "base")],
        {"cap": 96, "accept": True, "expected_files": 2, "expected_bytes": 96},
    ),
    (
        "node_counts_only_selected_binary",
        [
            ("python/base", "file", b"x" * 80),
            ("python/bin/node", "file", b"x"),
            ("python/a", "symlink", "base"),
            ("python/b", "symlink", "base"),
        ],
        {
            "cap": 96,
            "accept": True,
            "role": "node",
            "expected_files": 1,
            "expected_bytes": 1,
        },
    ),
]


class SDKArchiveTests(unittest.TestCase):
    def check_archive(
        self,
        label,
        members,
        *,
        accept=False,
        cap=None,
        role="python",
        expected_files=None,
        expected_bytes=None,
    ):
        with tempfile.TemporaryDirectory(prefix="cep-sdk-archive-test-") as folder:
            root = Path(folder)
            archive = root / "fixture.tar.gz"
            sdk = root / "sdk"
            archive_root = root / "archives"
            sdk.mkdir()
            archive_root.mkdir()
            with tarfile.open(archive, "w:gz") as bundle:
                for name, kind, payload in members:
                    entry = tarfile.TarInfo(name)
                    entry.mode = 0o755
                    if kind in ("file", "setuid"):
                        entry.size = len(payload)
                        if kind == "setuid":
                            entry.mode |= 0o4000
                        bundle.addfile(entry, io.BytesIO(payload))
                    else:
                        entry.type = {
                            "symlink": tarfile.SYMTYPE,
                            "hardlink": tarfile.LNKTYPE,
                            "fifo": tarfile.FIFOTYPE,
                            "directory": tarfile.DIRTYPE,
                        }[kind]
                        if kind in ("symlink", "hardlink"):
                            entry.linkname = payload
                        bundle.addfile(entry)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            if label == "hash_mismatch":
                digest = "0" * 64

            def download(arguments, **kwargs):
                self.assertEqual("https://example.invalid/sdk.tar.gz", arguments[-1])
                destination = Path(arguments[arguments.index("--output") + 1])
                self.assertEqual(archive_root, destination.parent)
                shutil.copyfile(archive, destination)

            downloader = Mock(side_effect=download)
            attestation = Mock(return_value="synthetic-tree-no-ownership-attestation")
            namespace = {
                "hashlib": hashlib,
                "json": json,
                "os": os,
                "Path": Path,
                "PurePosixPath": PurePosixPath,
                "posixpath": posixpath,
                "shutil": shutil,
                "stat": stat,
                "tarfile": tarfile,
                "unicodedata": unicodedata,
                "subprocess": SimpleNamespace(run=downloader),
                "archive_root": archive_root,
                "sdk": sdk,
                "pin": {role: digest},
                "archives": {
                    role: (
                        "3.13.9",
                        "https://example.invalid/sdk.tar.gz",
                        "python",
                        "bin/python3.13",
                    )
                },
                "provenance": {"archives": {}, "aliases": []},
                "manifest": {"sdks": {}},
                "sdk_tree_digest": attestation,
            }
            try:
                if accept:
                    exec(extractor_program(cap), namespace)
                    files = [path for path in sdk.rglob("*") if path.is_file()]
                    self.assertEqual(expected_files, len(files))
                    self.assertEqual(
                        expected_bytes, sum(path.stat().st_size for path in files)
                    )
                    self.assertEqual(
                        len(files), len({path.stat().st_ino for path in files})
                    )
                    for path in [sdk / role, *(sdk / role).rglob("*")]:
                        self.assertFalse(path.is_symlink())
                        self.assertEqual(0, stat.S_IMODE(path.stat().st_mode) & 0o7222)
                        if path.is_file():
                            self.assertEqual(1, path.stat().st_nlink)
                    attestation.assert_called_once_with(sdk / role)
                else:
                    with self.assertRaises(RuntimeError):
                        exec(extractor_program(cap), namespace)
                    self.assertEqual(
                        [],
                        list(sdk.iterdir()),
                        "invalid archive wrote SDK destinations",
                    )
                    attestation.assert_not_called()
                downloader.assert_called_once()
            finally:
                # The real extractor seals directories; permit only temporary-tree cleanup.
                directories = [
                    root,
                    *[
                        path
                        for path in root.rglob("*")
                        if path.is_dir() and not path.is_symlink()
                    ],
                ]
                for directory in directories:
                    directory.chmod(0o700)


def archive_case(label, members, options):
    def test(self):
        self.check_archive(label, members, **options)

    test.__name__ = "test_" + label
    test.__doc__ = "Archive preflight: " + label.replace("_", " ") + "."
    return test


# Separate discovered methods retain a precise 21-case result in stdlib unittest.
for _label, _members, _options in CASES:
    setattr(SDKArchiveTests, "test_" + _label, archive_case(_label, _members, _options))


if __name__ == "__main__":
    unittest.main()

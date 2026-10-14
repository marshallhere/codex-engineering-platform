"""Technology-neutral, operator-owned declarative JSON CLI acceptance cases."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile

from .process import redact

KINDS = {"spec", "tests", "security", "quality"}
MAX_FIXTURES = 1_048_576
MAX_OUTPUT = 200_000
MAX_DECLARATION = 8 * 1_048_576
FIELDS = {
    "id",
    "kind",
    "requirements",
    "argv",
    "fixtures",
    "exit_code",
    "stdout_json",
    "stderr_json",
    "stdout_empty",
    "stderr_empty",
    "forbidden_output",
    "unchanged",
    "mutable_fixture",
}


def parse_declaration(text):
    """Parse protected policy/case JSON without ambiguous keys or infinite floats."""
    if not isinstance(text, str):
        raise ValueError("declaration must be UTF-8 text")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError as error:
        raise ValueError("declaration must be valid UTF-8 text") from error
    if size > MAX_DECLARATION:
        raise ValueError("declaration exceeds 8 MiB limit")
    # Bound container nesting before allocation and later policy serialization.
    # Brackets within JSON strings (including fixture contents) are plain text.
    depth, quoted, escaped = 0, False, False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > 128:
                raise ValueError("declaration exceeds 128 container levels")
        elif character in "]}":
            depth -= 1

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate declaration key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("nonfinite declaration number")

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("nonfinite declaration float")
        return parsed

    try:
        return json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=constant,
            parse_float=finite_float,
        )
    except (ValueError, RecursionError) as error:
        raise ValueError("invalid JSON declaration: " + str(error)[:256]) from error


def _text(value, maximum, *, nonempty=False, allow_nul=False):
    if not isinstance(value, str) or (nonempty and not value):
        raise ValueError("text value required")
    if len(value.encode("utf-8")) > maximum or (not allow_nul and "\0" in value):
        raise ValueError("text value exceeds its limit or contains NUL")


def _fixture_path(name):
    _text(name, 1024, nonempty=True)
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or path.as_posix() != name
        or name == "."
    ):
        raise ValueError("fixture filenames must be canonical relative POSIX paths")
    return path


def _json_value(value):
    if value is None or type(value) in {bool, int, str}:
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _json_value(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise ValueError("expected JSON must contain finite JSON values")


def validate_cases(cases, requirements):
    if not isinstance(cases, list) or not 1 <= len(cases) <= 64:
        raise ValueError("one to 64 black-box cases required")
    if not isinstance(requirements, (list, tuple, set)) or any(
        not isinstance(r, str) or not r for r in requirements
    ):
        raise ValueError("frozen requirement IDs required")
    known, ids = set(requirements), set()
    total_bytes, total_files = 0, 0
    for case in cases:
        if (
            not isinstance(case, dict)
            or set(case) - FIELDS
            or {"id", "kind", "requirements", "argv", "exit_code"} - set(case)
        ):
            raise ValueError("unknown or missing black-box case fields")
        _text(case["id"], 128, nonempty=True)
        if case["id"] in ids:
            raise ValueError("duplicate case ID")
        ids.add(case["id"])
        if not isinstance(case["kind"], str) or case["kind"] not in KINDS:
            raise ValueError("invalid case gate kind")
        mapped = case["requirements"]
        if (
            not isinstance(mapped, list)
            or not mapped
            or any(not isinstance(r, str) or r not in known for r in mapped)
            or len(mapped) != len(set(mapped))
        ):
            raise ValueError("case requirements must be unique frozen IDs")
        argv = case["argv"]
        if not isinstance(argv, list) or not 1 <= len(argv) <= 128:
            raise ValueError("case requires bounded direct argv")
        for arg in argv:
            _text(arg, 8192, nonempty=True)
            if "{fixture}" in arg and arg != "{fixture}":
                raise ValueError("fixture placeholder must be an exact argv token")
        if (
            not Path(argv[0]).is_absolute()
            or sum(len(arg.encode()) for arg in argv) > 65536
        ):
            raise ValueError(
                "operator-resolved absolute executable and bounded argv required"
            )
        if type(case["exit_code"]) is not int:
            raise ValueError("exit_code must be an integer")
        for field in ("stdout_empty", "stderr_empty", "unchanged", "mutable_fixture"):
            if field in case and type(case[field]) is not bool:
                raise ValueError("case flags must be booleans")
        for field in ("stdout_json", "stderr_json"):
            if field in case:
                if not isinstance(case[field], dict):
                    raise ValueError("expected JSON must be a top-level object subset")
                _json_value(case[field])
                if len(json.dumps(case[field], allow_nan=False).encode()) > MAX_OUTPUT:
                    raise ValueError("expected JSON exceeds limit")
                if case.get(field.replace("_json", "_empty")) is True:
                    raise ValueError("JSON output cannot also be required empty")
        forbidden = case.get("forbidden_output", [])
        if not isinstance(forbidden, list) or len(forbidden) > 128:
            raise ValueError("forbidden_output must be a bounded list")
        for text in forbidden:
            _text(text, 1024, nonempty=True)
        fixtures = case.get("fixtures", {})
        if not isinstance(fixtures, dict):
            raise ValueError("fixtures must map relative filenames to text")
        canonical = set()
        for filename, content in fixtures.items():
            path = _fixture_path(filename)
            folded = path.as_posix().casefold()
            if folded in canonical:
                raise ValueError("case-alias fixture filenames are forbidden")
            canonical.add(folded)
            _text(content, MAX_FIXTURES, allow_nul=True)
            total_bytes += len(content.encode())
            total_files += 1
        for path in canonical:
            if any(
                parent.as_posix() in canonical
                for parent in PurePosixPath(path).parents
                if parent.as_posix() != "."
            ):
                raise ValueError("fixture file conflicts with a parent directory")
        if total_bytes > MAX_FIXTURES or total_files > 128:
            raise ValueError("fixture declaration exceeds byte or file limit")


def _manifest(root):
    manifest, total, nodes = {}, 0, 0

    def walk(fd, prefix, depth):
        nonlocal total, nodes
        if depth > 32:
            raise ValueError("fixture tree depth exceeded")
        with os.scandir(fd) as entries:
            for entry in entries:
                nodes += 1
                if nodes > 1024:
                    raise ValueError("fixture tree entry limit exceeded")
                name = prefix + entry.name
                info = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                metadata = {
                    "mode": stat.S_IMODE(info.st_mode),
                    "device": info.st_dev,
                    "inode": info.st_ino,
                }
                if stat.S_ISLNK(info.st_mode):
                    metadata.update(
                        kind="symlink", target=os.readlink(entry.name, dir_fd=fd)
                    )
                    current = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                    if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                        raise ValueError("fixture symlink changed during measurement")
                elif stat.S_ISDIR(info.st_mode):
                    metadata["kind"] = "directory"
                    child = os.open(
                        entry.name,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=fd,
                    )
                    try:
                        current = os.fstat(child)
                        metadata.update(
                            mode=stat.S_IMODE(current.st_mode),
                            device=current.st_dev,
                            inode=current.st_ino,
                            modified_ns=current.st_mtime_ns,
                        )
                        walk(child, name + "/", depth + 1)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    file = os.open(
                        entry.name,
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=fd,
                    )
                    try:
                        current = os.fstat(file)
                        if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
                            raise ValueError("fixture file has unsafe alias")
                        metadata.update(
                            mode=stat.S_IMODE(current.st_mode),
                            device=current.st_dev,
                            inode=current.st_ino,
                            modified_ns=current.st_mtime_ns,
                        )
                        with os.fdopen(file, "rb", closefd=False) as handle:
                            data = handle.read(MAX_FIXTURES + 1)
                    finally:
                        os.close(file)
                    total += len(data)
                    if total > MAX_FIXTURES:
                        raise ValueError("fixture tree byte limit exceeded")
                    metadata.update(
                        kind="file", sha256=hashlib.sha256(data).hexdigest()
                    )
                else:
                    metadata["kind"] = "special"
                manifest[name] = metadata

    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        manifest[""] = {
            "kind": "root",
            "mode": stat.S_IMODE(info.st_mode),
            "device": info.st_dev,
            "inode": info.st_ino,
            "modified_ns": info.st_mtime_ns,
        }
        walk(fd, "", 0)
    finally:
        os.close(fd)
    return manifest


def _parse_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("nonfinite JSON number")

    return json.loads(
        text, object_pairs_hook=pairs, parse_float=Decimal, parse_constant=constant
    )


def _equal(actual, expected):
    if type(expected) is bool or expected is None or isinstance(expected, str):
        return type(actual) is type(expected) and actual == expected
    if type(expected) in {int, float}:
        return type(actual) in {int, Decimal} and Decimal(actual) == Decimal(
            str(expected)
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_equal(a, b) for a, b in zip(actual, expected))
        )
    return (
        isinstance(actual, dict)
        and set(actual) == set(expected)
        and all(_equal(actual[key], expected[key]) for key in expected)
    )


def run_cases(repo, cases, *, executor, scratch_root):
    requirements = set()
    if isinstance(cases, list):
        for case in cases:
            if isinstance(case, dict) and isinstance(case.get("requirements"), list):
                requirements.update(
                    requirement
                    for requirement in case["requirements"]
                    if isinstance(requirement, str)
                )
    validate_cases(cases, requirements)
    root = Path(repo).resolve(strict=True)
    scratch_root = Path(scratch_root).resolve(strict=True)
    if scratch_root.is_relative_to(root):
        raise ValueError("protected fixture scratch must remain outside candidate")
    checks, outcomes = [], []
    for case in cases:
        reasons, result = [], None
        suffix = hashlib.sha256(case["id"].encode()).hexdigest()[:16]
        with tempfile.TemporaryDirectory(
            prefix="case-" + suffix + "-", dir=scratch_root
        ) as directory:
            directory = Path(directory)
            execution = directory / ("exec-" + suffix)
            execution.mkdir(mode=0o700)
            fixture = (
                execution if case.get("mutable_fixture", False) else directory
            ) / ("inputs-" + suffix)
            fixture.mkdir(mode=0o700)
            try:
                for filename, content in case.get("fixtures", {}).items():
                    file = fixture.joinpath(*PurePosixPath(filename).parts)
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_text(content, encoding="utf-8")
                before = _manifest(fixture)
                argv = [
                    str(fixture) if arg == "{fixture}" else arg for arg in case["argv"]
                ]
                result = executor(argv, fixture, execution)
                if not isinstance(result, dict):
                    raise ValueError("executor outcome must be an object")
                for field in ("timed_out", "output_exceeded", "output_truncated"):
                    value = result.get(field)
                    if type(value) is not bool or value:
                        reasons.append("execution " + field)
                if (
                    type(result.get("exit_code")) is not int
                    or result["exit_code"] != case["exit_code"]
                ):
                    reasons.append("incorrect exit code")
                for stream in ("stdout", "stderr"):
                    text = result.get(stream)
                    if (
                        not isinstance(text, str)
                        or len(text.encode("utf-8")) > MAX_OUTPUT
                    ):
                        reasons.append(stream + " exceeded limit or is not text")
                        continue
                    if (
                        stream + "_empty" in case
                        and (not text.strip()) != case[stream + "_empty"]
                    ):
                        reasons.append(stream + " emptiness mismatch")
                    if stream + "_json" in case:
                        try:
                            actual = _parse_json(text)
                            expected = case[stream + "_json"]
                            if not isinstance(actual, dict) or any(
                                key not in actual or not _equal(actual[key], value)
                                for key, value in expected.items()
                            ):
                                reasons.append(stream + " JSON subset mismatch")
                        except (ValueError, ArithmeticError, RecursionError):
                            reasons.append(stream + " invalid JSON")
                    if any(
                        forbidden in text
                        for forbidden in case.get("forbidden_output", [])
                    ):
                        reasons.append(stream + " forbidden output")
                if case.get("unchanged", True) and _manifest(fixture) != before:
                    reasons.append("fixture tree changed")
            except (ValueError, OSError, RuntimeError, RecursionError) as error:
                reasons.append(type(error).__name__ + ": " + redact(str(error))[:1024])
            outcome = {"id": case["id"]}
            if isinstance(result, dict):
                for field in (
                    "exit_code",
                    "timed_out",
                    "output_exceeded",
                    "output_truncated",
                    "elapsed_seconds",
                ):
                    value = result.get(field)
                    if type(value) in {int, bool} or (
                        type(value) is float and math.isfinite(value)
                    ):
                        outcome[field] = value
                for field in ("stdout", "stderr"):
                    if isinstance(result.get(field), str):
                        outcome[field] = redact(result[field][-MAX_OUTPUT:])
            outcomes.append(outcome)
            checks.append(
                {
                    "id": case["id"],
                    "kind": case["kind"],
                    "requirement_ids": case["requirements"],
                    "passed": not reasons,
                    "detail": "; ".join(reasons),
                }
            )
    return {
        "passed": bool(checks) and all(check["passed"] for check in checks),
        "checks": checks,
        "outcomes": outcomes,
    }

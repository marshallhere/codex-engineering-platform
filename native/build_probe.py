"""Fixed offline toolchain builds in disposable CI; not a CEP execution backend."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import select
import selectors
import stat
import sys
import time

ROLES = {"python", "uv", "node", "go"}
MAX_OUTPUT = 65536
MAX_SDK_BYTES = 1_610_612_736
SOURCES = {
    "python": {
        "answer.py": "def answer():\n    return 42\n",
        "build.py": "import importlib.machinery,importlib.util,json,py_compile,sys\nfrom pathlib import Path\np=Path(sys.argv[1]);out=Path(sys.argv[2]);py_compile.compile(str(p/'answer.py'),cfile=str(out/'answer.pyc'),dfile='answer.py',doraise=True)\nloader=importlib.machinery.SourcelessFileLoader('answer',str(out/'answer.pyc'));spec=importlib.util.spec_from_loader('answer',loader);m=importlib.util.module_from_spec(spec);loader.exec_module(m)\nobj={'toolchain':'python','answer':m.answer()};(out/'artifact.json').write_text(json.dumps(obj,sort_keys=True));print(json.dumps(obj,sort_keys=True))\n",
    },
    "node": {
        "emit.mjs": "console.log(JSON.stringify({toolchain:'node',answer:42}));\n",
        "build.mjs": "import{spawnSync}from'node:child_process';import{writeFileSync}from'node:fs';\nconst r=spawnSync(process.execPath,[process.argv[2]+'/emit.mjs'],{encoding:'utf8',timeout:30000,maxBuffer:65536,env:process.env,shell:false});\nif(r.error||r.status!==0||r.signal||r.stderr)throw new Error('fixed child build failed');\nwriteFileSync(process.argv[3]+'/artifact.json',r.stdout,{mode:0o600});process.stdout.write(r.stdout);\n",
    },
    "go": {
        "go.mod": "module cepfixture\n\ngo 1.23\n",
        "main.go": 'package main\nimport("encoding/json";"os")\nfunc main(){json.NewEncoder(os.Stdout).Encode(map[string]interface{}{"toolchain":"go","answer":42})}\n',
    },
}


def _json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate declaration key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("nonfinite declaration number")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def _checked_root(path, mode=None):
    path = Path(path)
    if not path.is_absolute() or path != path.resolve(strict=True):
        raise RuntimeError("absolute canonical staging root required")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError(
            "staging root must be root-owned without foreign write access"
        )
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise RuntimeError("staging root has incorrect permissions")
    return path


def _helpers():
    if __package__:
        return importlib.import_module(".uid_probe", __package__)
    stage = _checked_root(Path(__file__).resolve().parent, 0o700)
    for name in ("build_probe.py", "uid_probe.py", "uid_domain.py"):
        info = (stage / name).lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_nlink != 1
            or info.st_mode & 0o022
        ):
            raise RuntimeError("private experiment code staging is unsafe")
    sys.path.insert(0, str(stage))
    return importlib.import_module("uid_probe")


def sdk_tree_digest(root):
    """Read-only SDK identity: sorted [path,sha256,size,permission-mode] rows."""
    root = _checked_root(root)
    rows, total = [], 0
    for directory, directories, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        info = parent.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & (0o222 | stat.S_ISUID | stat.S_ISGID)
            or info.st_mode & 0o005 != 0o005
        ):
            raise RuntimeError(
                "SDK directories must be immutable root-owned real directories"
            )
        for name in directories:
            if (parent / name).is_symlink():
                raise RuntimeError("SDK aliases are forbidden")
        for name in files:
            file = parent / name
            fd = os.open(file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != 0
                    or info.st_nlink != 1
                    or info.st_mode & (0o222 | stat.S_ISUID | stat.S_ISGID)
                    or not info.st_mode & 0o004
                ):
                    raise RuntimeError("SDK file is mutable, privileged or aliased")
                total += info.st_size
                if total > MAX_SDK_BYTES or len(rows) >= 40000:
                    raise RuntimeError("SDK content exceeds bounded inventory")
                digest = hashlib.sha256()
                with os.fdopen(fd, "rb", closefd=False) as handle:
                    while True:
                        block = handle.read(1_048_576)
                        if not block:
                            break
                        digest.update(block)
                after = os.fstat(fd)
                if (after.st_size, after.st_mtime_ns, after.st_ino) != (
                    info.st_size,
                    info.st_mtime_ns,
                    info.st_ino,
                ):
                    raise RuntimeError("SDK changed during inventory")
                rows.append(
                    [
                        file.relative_to(root).as_posix(),
                        digest.hexdigest(),
                        info.st_size,
                        stat.S_IMODE(info.st_mode),
                    ]
                )
            finally:
                os.close(fd)
    if not rows:
        raise RuntimeError("SDK tree must not be empty")
    return hashlib.sha256(
        json.dumps(sorted(rows), separators=(",", ":")).encode()
    ).hexdigest()


def validate_manifest(path):
    path = Path(path)
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or info.st_nlink != 1
        or info.st_mode & 0o077
        or info.st_size > 8_388_608
    ):
        raise RuntimeError(
            "SDK declaration must be bounded private root-owned regular data"
        )
    value = _json(path.read_text())
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "sdks"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or not isinstance(value["sdks"], dict)
        or set(value["sdks"]) != ROLES
    ):
        raise RuntimeError("invalid SDK declaration")
    for role, declaration in value["sdks"].items():
        if not isinstance(declaration, dict) or set(declaration) != {
            "root",
            "executable",
            "tree_sha256",
            "version",
        }:
            raise RuntimeError(
                "SDK identity requires exact root, executable, content and version"
            )
        relative = Path(declaration["executable"])
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise RuntimeError(
                "SDK executable must be a relative path inside its frozen root"
            )
        version = declaration["version"]
        if not isinstance(version, str) or not re.fullmatch(
            r"[0-9]+(?:\.[0-9]+){1,3}", version
        ):
            raise RuntimeError("exact numeric SDK version required")
        root = _checked_root(declaration["root"])
        if sdk_tree_digest(root) != declaration["tree_sha256"]:
            raise RuntimeError("SDK content identity mismatch")
        executable = root / relative
        if executable.resolve(strict=True) != executable:
            raise RuntimeError("SDK executable aliases are forbidden")
        with executable.open("rb") as handle:
            binary = handle.read(4)
        if (
            binary
            not in (
                b"\xcf\xfa\xed\xfe",
                b"\xfe\xed\xfa\xcf",
                b"\xca\xfe\xba\xbe",
                b"\xbe\xba\xfe\xca",
                b"\xca\xfe\xba\xbf",
                b"\xbf\xba\xfe\xca",
            )
            or not executable.stat().st_mode & 0o001
        ):
            raise RuntimeError(
                "SDK entrypoint must be a trusted executable Mach-O binary"
            )
        declaration["path"] = str(executable)
    return value


def environment(scratch, sdk):
    scratch = Path(scratch)
    return {
        "PATH": os.defpath,
        "HOME": str(scratch / "home"),
        "TMPDIR": str(scratch / "tmp"),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "UV_CACHE_DIR": str(scratch / "uv-cache"),
        "UV_PYTHON_DOWNLOADS": "never",
        "UV_OFFLINE": "1",
        "UV_NO_PROGRESS": "1",
        "GOCACHE": str(scratch / "go-cache"),
        "GOMODCACHE": str(scratch / "go-mod"),
        "GOPATH": str(scratch / "go-path"),
        "GOROOT": sdk["go"]["root"],
        "GOENV": "off",
        "GOTOOLCHAIN": "local",
        "GOPROXY": "off",
        "GOSUMDB": "off",
        "CGO_ENABLED": "0",
        "GOMAXPROCS": "2",
    }


def commands(mode, sdk, source, scratch):
    source, scratch = str(source), str(scratch)

    def path(role):
        return sdk[role]["path"]

    versions = [
        [path(role), "version" if role == "go" else "--version"]
        for role in (["uv", "python"] if mode == "python" else [mode])
    ]
    if mode == "python":
        builds = [
            [
                path("uv"),
                "--quiet",
                "--offline",
                "--no-config",
                "run",
                "--no-project",
                "--no-managed-python",
                "--python",
                path("python"),
                "--",
                path("python"),
                "-I",
                source + "/build.py",
                source,
                scratch,
            ]
        ]
    elif mode == "node":
        builds = [[path("node"), source + "/build.mjs", source, scratch]]
    elif mode == "go":
        builds = [
            [
                path("go"),
                "build",
                "-p=1",
                "-trimpath",
                "-o",
                scratch + "/fixture-go",
                source + "/main.go",
            ],
            [scratch + "/fixture-go"],
        ]
    else:
        raise RuntimeError("unknown fixed build fixture")
    return versions, builds


def _execute(argv, env, deadline):
    """Dropped wrapper spawns fixed argv, drains output and reaps its SDK child."""
    if time.monotonic() >= deadline:
        raise RuntimeError("fixed worker budget exhausted before SDK dispatch")
    reads, writes = [], []
    try:
        for _ in range(2):
            read, write = os.pipe()
            reads.append(read)
            writes.append(write)
        actions = [
            (os.POSIX_SPAWN_OPEN, 0, os.devnull, os.O_RDONLY, 0),
            (os.POSIX_SPAWN_DUP2, writes[0], 1),
            (os.POSIX_SPAWN_DUP2, writes[1], 2),
        ]
        actions += [(os.POSIX_SPAWN_CLOSE, fd) for fd in reads + writes]
        if time.monotonic() >= deadline:
            raise RuntimeError("fixed worker budget exhausted before SDK dispatch")
        pid = os.posix_spawn(argv[0], argv, env, file_actions=actions)
        for fd in writes:
            os.close(fd)
        writes = []
        selector = selectors.DefaultSelector()
        output = [bytearray(), bytearray()]
        for index, fd in enumerate(reads):
            os.set_blocking(fd, False)
            selector.register(fd, selectors.EVENT_READ, index)
        status, count, timed_out, exceeded = None, 0, False, False
        try:
            while selector.get_map() or status is None:
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                if status is None:
                    reaped, current = os.waitpid(pid, os.WNOHANG)
                    if reaped:
                        status = current
                # Exit of the direct child does not imply EOF: a descendant may
                # still own either stream. Capture through both EOFs or fail the
                # finite deadline, including delayed descendant diagnostics.
                ready = selector.select(min(0.02, max(0, deadline - time.monotonic())))
                for key, _ in ready:
                    data = os.read(key.fd, 8192)
                    if not data:
                        selector.unregister(key.fd)
                        continue
                    available = max(0, MAX_OUTPUT - count)
                    output[key.data].extend(data[:available])
                    count += len(data)
                    if count > MAX_OUTPUT:
                        exceeded = True
                        break
                if exceeded:
                    break
        finally:
            selector.close()
        return {
            "argv": argv,
            "status": status,
            "timed_out": timed_out,
            "output_exceeded": exceeded,
            "stdout": output[0].decode("utf-8", "replace"),
            "stderr": output[1].decode("utf-8", "replace"),
        }
    finally:
        for fd in reads + writes:
            os.close(fd)


def _worker(uid, mode, sdk, source, scratch, report_fd):
    helpers = _helpers()
    helpers.drop(uid)  # No SDK executable is run with parent authority.
    os.chdir(source)
    env = environment(scratch, sdk)
    version_commands, build_commands = commands(mode, sdk, source, scratch)
    deadline = time.monotonic() + 120
    outcomes = []
    for command in version_commands + build_commands:
        try:
            if time.monotonic() >= deadline:
                raise RuntimeError("fixed worker budget exhausted before dispatch")
            outcome = _execute(command, env, deadline)
            if not isinstance(outcome, dict):
                raise RuntimeError("invalid SDK command receipt")
        except (OSError, RuntimeError) as error:
            outcome = {
                "argv": command,
                "status": None,
                "timed_out": time.monotonic() >= deadline,
                "output_exceeded": False,
                "stdout": "",
                "stderr": str(error)[:2048],
            }
        outcomes.append(outcome)
        _write_progress(report_fd, {"mode": mode, "outcomes": outcomes})
        if not _receipt_ok(outcome):
            break
        if len(outcomes) <= len(version_commands):
            role = (["uv", "python"] if mode == "python" else [mode])[len(outcomes) - 1]
            if not _version_matches(role, sdk[role]["version"], outcome["stdout"]):
                break


def _receipt_ok(outcome):
    return (
        isinstance(outcome, dict)
        and type(outcome.get("status")) is int
        and outcome["status"] == 0
        and outcome.get("timed_out") is False
        and outcome.get("output_exceeded") is False
        and isinstance(outcome.get("stdout"), str)
        and outcome.get("stderr") == ""
    )


def _version_matches(role, version, text):
    prefix = {"python": "Python ", "uv": "uv ", "node": "v", "go": "go version go"}[
        role
    ] + version
    suffix = {
        "python": "",
        "node": "",
        "uv": r"(?: \([^\n]+\))?",
        "go": r" darwin/(?:arm64|amd64)",
    }[role]
    return re.fullmatch(re.escape(prefix) + suffix, text.strip()) is not None


def _write_progress(report_fd, report):
    data = (json.dumps(report, sort_keys=True) + "\n").encode()
    if len(data) > 131072:
        raise RuntimeError("worker report exceeds bound")
    while data:
        written = os.write(report_fd, data)
        data = data[written:]


def _parse_progress(data):
    report = {"outcomes": []}
    for line in data.decode("utf-8").splitlines():
        value = _json(line)
        if not isinstance(value, dict):
            raise ValueError("invalid worker report frame")
        if set(value) == {"error"}:
            report["error"] = value["error"]
            continue
        if set(value) != {"mode", "outcomes"} or not isinstance(
            value["outcomes"], list
        ):
            raise ValueError("invalid worker report frame")
        previous = report["outcomes"]
        if (
            value["outcomes"][: len(previous)] != previous
            or len(value["outcomes"]) != len(previous) + 1
        ):
            raise ValueError("worker command evidence lost or replaced")
        report.update(value)
    return report


def _sources(root, mode):
    root.mkdir(mode=0o755)
    for name, text in SOURCES[mode].items():
        path = root / name
        path.write_text(text)
        path.chmod(0o444)
    root.chmod(0o555)


def _read_artifact(path, uid, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != uid
            or not 0 < info.st_size <= limit
        ):
            raise RuntimeError("artifact has unsafe ownership, alias or size")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise RuntimeError("artifact exceeds limit")
        return data
    finally:
        os.close(fd)


def verify_outcomes(mode, sdk, report, *, source="/source", scratch="/scratch"):
    versions, builds = commands(mode, sdk, source, scratch)
    if report.get("error") or report.get("mode") != mode:
        raise RuntimeError("unexpected worker diagnostic or mode")
    outcomes = report.get("outcomes", [])
    if not isinstance(outcomes, list) or len(outcomes) != len(versions) + len(builds):
        raise RuntimeError("incomplete fixed build outcomes")
    for outcome, expected_argv in zip(outcomes, versions + builds):
        if not _receipt_ok(outcome) or outcome.get("argv") != expected_argv:
            raise RuntimeError("SDK build failed or emitted unexpected diagnostics")
    roles = ["uv", "python"] if mode == "python" else [mode]
    for role, outcome in zip(roles, outcomes):
        if not _version_matches(role, sdk[role]["version"], outcome["stdout"]):
            raise RuntimeError("SDK version identity mismatch")
    if mode == "go" and outcomes[-2]["stdout"]:
        raise RuntimeError("Go compiler emitted unexpected output")
    if _json(outcomes[-1]["stdout"]) != {"toolchain": mode, "answer": 42}:
        raise RuntimeError("fixed build output does not match protected expectation")


def run_build(uid, mode, sdk, work, evidence):
    helpers = _helpers()
    case = work / (mode + "-" + str(uid))
    case.mkdir(mode=0o755)
    source, scratch = case / "source", case / "scratch"
    _sources(source, mode)
    scratch.mkdir(mode=0o700)
    os.chown(scratch, uid, uid)
    for name in ("home", "tmp", "uv-cache", "go-cache", "go-mod", "go-path"):
        directory = scratch / name
        directory.mkdir(mode=0o700)
        os.chown(directory, uid, uid)
    read, write = os.pipe()
    worker = os.fork()
    if worker == 0:
        os.close(read)
        try:
            _worker(uid, mode, sdk, source, scratch, write)
            os._exit(0)
        except BaseException as error:
            try:
                os.write(
                    write,
                    (
                        json.dumps(
                            {"error": type(error).__name__ + ":" + str(error)[:2048]}
                        )
                        + "\n"
                    ).encode(),
                )
            except OSError:
                pass
            os._exit(3)
    os.close(write)
    os.set_blocking(read, False)
    data, worker_status, cleaner_status, diagnostics = bytearray(), None, None, []
    errors, timed_out, overflow, survivors = 0, False, False, None
    cleaner = None
    cleaner_read = cleaner_write = None
    deadline = time.monotonic() + 125
    try:
        while time.monotonic() < deadline:
            if worker_status is None:
                done, status = os.waitpid(worker, os.WNOHANG)
                if done:
                    worker_status = status
            ready, _, _ = select.select([read], [], [], 0.02)
            if ready:
                block = os.read(read, 8192)
                if not block:
                    break
                data.extend(block)
                if len(data) > 131072:
                    overflow = True
                    break
            # Reaped wrapper status cannot substitute for report-pipe EOF.
            # An inherited writer must close within the same finite deadline.
        else:
            timed_out = True
    except (OSError, RuntimeError) as error:
        diagnostics.append(str(error))
        errors += 1
    finally:
        try:
            cleaner_read, cleaner_write = os.pipe()
            cleaner = os.fork()
            if cleaner == 0:
                os.close(cleaner_read)
                os.close(read)
                try:
                    helpers.cleanup_child(uid)
                except BaseException as error:
                    try:
                        os.write(
                            cleaner_write,
                            (type(error).__name__ + ":" + str(error))[:2048].encode(),
                        )
                    except OSError:
                        pass
                    os._exit(3)
            os.close(cleaner_write)
            cleaner_write = None
            os.set_blocking(cleaner_read, False)
        except OSError as error:
            diagnostics.append(str(error))
            errors += 1
        until = time.monotonic() + 8
        while time.monotonic() < until:
            for pid, label in ((worker, "worker"), (cleaner, "cleaner")):
                if pid is None or (
                    worker_status is not None
                    if label == "worker"
                    else cleaner_status is not None
                ):
                    continue
                try:
                    done, status = os.waitpid(pid, os.WNOHANG)
                    if done:
                        if label == "worker":
                            worker_status = status
                        else:
                            cleaner_status = status
                except OSError as error:
                    errors += 1
                    if len(diagnostics) < 8:
                        diagnostics.append(str(error))
            try:
                survivors = helpers.inventory_uid(uid)
            except helpers.InventoryError as error:
                survivors = None
                errors += 1
                if len(diagnostics) < 8:
                    diagnostics.append(str(error))
            if (
                worker_status is not None
                and cleaner_status is not None
                and survivors == []
            ):
                break
            time.sleep(0.02)
        for fd in (read, cleaner_read):
            if fd is not None:
                try:
                    ready, _, _ = select.select([fd], [], [], 0)
                    if ready:
                        block = os.read(fd, 8192)
                        if fd == read:
                            data.extend(block)
                        elif block:
                            diagnostics.append(block.decode("utf-8", "replace"))
                except OSError as error:
                    diagnostics.append(str(error))
                    errors += 1
        for fd in (read, cleaner_read, cleaner_write):
            if fd is not None:
                os.close(fd)
    result = {
        "case": mode,
        "uid": uid,
        "worker_status": worker_status,
        "cleaner_status": cleaner_status,
        "timed_out": timed_out,
        "output_exceeded": overflow,
        "survivors": None if survivors is None else len(survivors),
        "error_count": errors,
        "diagnostics": diagnostics,
        "production_qualified": False,
    }
    try:
        report = _parse_progress(data)
        result["report"] = report
        if (
            worker_status != 0
            or cleaner_status != 0
            or survivors != []
            or timed_out
            or overflow
            or diagnostics
        ):
            raise RuntimeError("build or UID cleanup incomplete; domain quarantined")
        verify_outcomes(mode, sdk, report, source=source, scratch=scratch)
        artifacts = {}
        names = (
            ["fixture-go"]
            if mode == "go"
            else ["artifact.json"] + (["answer.pyc"] if mode == "python" else [])
        )
        for name in names:
            value = _read_artifact(scratch / name, uid, 33554432)
            if name == "artifact.json" and _json(value.decode()) != {
                "toolchain": mode,
                "answer": 42,
            }:
                raise RuntimeError(
                    "built artifact does not match protected expectation"
                )
            (evidence / (mode + "-" + name)).write_bytes(value)
            artifacts[name] = {
                "sha256": hashlib.sha256(value).hexdigest(),
                "bytes": len(value),
            }
        result.update(passed=True, artifacts=artifacts)
    except (ValueError, OSError, RuntimeError) as error:
        result.update(passed=False, failure=str(error))
    (evidence / (mode + ".json")).write_text(
        json.dumps(result, sort_keys=True, indent=2)
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--qualify", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args(argv)
    report = {
        "production_qualified": False,
        "cases": [],
        "qualification": "blocked: fixed positive builds are not backend qualification",
    }
    if args.inspect and not args.qualify:
        report.update(experiment="not_run", platform=sys.platform)
        print(json.dumps(report, sort_keys=True))
        return 0
    if not args.qualify or args.inspect:
        parser.error("choose --inspect or --qualify")
    lease = None
    try:
        helpers = _helpers()
        helpers.guard()
        if not args.manifest or not args.work_root or not args.evidence_root:
            raise RuntimeError("trusted staging paths required")
        stage = _checked_root(Path(__file__).resolve().parent, 0o700)
        if args.manifest.resolve().parent != stage:
            raise RuntimeError("SDK declaration must reside in private code staging")
        sdk = validate_manifest(args.manifest)["sdks"]
        report["sdks"] = sdk
        work, evidence = (
            _checked_root(args.work_root),
            _checked_root(args.evidence_root, 0o700),
        )
        lease = helpers.exclusive_lease()
        used = set()
        deadline = time.monotonic() + 600
        for mode in ("python", "node", "go"):
            if time.monotonic() >= deadline:
                raise RuntimeError("fixed workflow budget exhausted")
            uid = helpers.choose_uid()
            if uid in used:
                raise RuntimeError("fixture identity must not be reused")
            used.add(uid)
            result = run_build(uid, mode, sdk, work, evidence)
            report["cases"].append(result)
            if not result["passed"]:
                raise RuntimeError(
                    "fixed build case failed; preserve evidence and quarantine UID"
                )
        for declaration in sdk.values():
            if sdk_tree_digest(declaration["root"]) != declaration["tree_sha256"]:
                raise RuntimeError("SDK identity changed during build")
        report["experiment"] = "passed"
        code = 0
    except (ValueError, OSError, RuntimeError) as error:
        report.update(experiment="failed", error=str(error))
        code = 1
    finally:
        if lease is not None:
            os.close(lease)
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

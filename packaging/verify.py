#!/usr/bin/env python3
"""Verify built archives and exercise an installed wheel outside the checkout."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile
import tempfile
import zipfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--sdist", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    wheel, sdist = args.wheel.resolve(strict=True), args.sdist.resolve(strict=True)
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "running",
        "checks": [],
        "artifacts": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (wheel, sdist)
        },
    }
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }

    def record(name, passed, **details):
        report["checks"].append({"name": name, "passed": bool(passed), **details})
        if not passed:
            raise ValueError("Packaging verification failed: " + name)

    def command(name, argv, cwd, *, extra_env=None):
        try:
            result = subprocess.run(
                [str(part) for part in argv],
                cwd=cwd,
                env={**env, **(extra_env or {})},
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            record(name, False, failure_kind=type(exc).__name__)
        (evidence / (name + ".stdout.log")).write_text(result.stdout)
        (evidence / (name + ".stderr.log")).write_text(result.stderr)
        record(name, result.returncode == 0, returncode=result.returncode)
        return result.stdout

    try:
        assets = runpy.run_path(str(root / "setup.py"))["collect_assets"](root)
        with zipfile.ZipFile(wheel) as archive:
            for source, destination in assets:
                record(
                    "wheel-asset:" + destination.as_posix(),
                    archive.read(destination.as_posix()) == source.read_bytes(),
                )
            actual = {
                name
                for name in archive.namelist()
                if name.startswith(("cep/bundle/", "cep/fixtures/"))
                and not name.endswith("/")
            }
            record(
                "wheel-exact-assets",
                actual == {destination.as_posix() for _, destination in assets},
                count=len(actual),
            )
        with tarfile.open(sdist) as archive:
            names = archive.getnames()
            top = names[0].split("/", 1)[0]
            for source, _ in assets:
                filename = top + "/" + source.relative_to(root).as_posix()
                member = archive.getmember(filename)
                record(
                    "sdist-asset:" + source.relative_to(root).as_posix(),
                    member.isfile()
                    and archive.extractfile(member).read() == source.read_bytes(),
                )
            for filename in (
                "scripts/check_publication.py",
                "config/capabilities.json",
                "packaging/assets.json",
                "tests/test_packaging.py",
            ):
                record("sdist-support:" + filename, top + "/" + filename in names)
        with tempfile.TemporaryDirectory(prefix="cep-packaging-") as temporary:
            scratch = Path(temporary).resolve()
            record("outside-checkout", root not in scratch.parents and scratch != root)
            venv = scratch / "venv"
            command("venv", [sys.executable, "-m", "venv", venv], scratch)
            python, cep = venv / "bin/python", venv / "bin/cep"
            command(
                "install-wheel",
                [
                    python,
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--no-deps",
                    "--disable-pip-version-check",
                    wheel,
                ],
                scratch,
            )
            command("version", [cep, "--version"], scratch)
            location = json.loads(
                command(
                    "installed-location",
                    [
                        python,
                        "-I",
                        "-c",
                        "import json, cep; from cep.cli import bundle_path; from pathlib import Path; p=bundle_path(); print(json.dumps({'module':cep.__file__,'bundle':str(p),'skills':len(list((p/'skills').glob('*/SKILL.md'))),'agents':len(list((p/'assets/agents').glob('*.toml')))}))",
                    ],
                    scratch,
                )
            )
            record(
                "installed-package-location",
                venv in Path(location["module"]).parents
                and venv in Path(location["bundle"]).parents,
                skills=location["skills"],
                agents=location["agents"],
            )
            command("doctor", [cep, "doctor"], scratch)
            project = scratch / "project"
            project.mkdir()
            (project / "pyproject.toml").write_text(
                '[project]\nname="fixture"\nversion="0.0.0"\n'
            )
            packs = json.loads(command("packs", [cep, "packs", project], scratch))
            record(
                "installed-python-go-packs",
                {item["id"] for item in packs} == {"python", "go"},
            )
            preview = json.loads(
                command("install-preview", [cep, "install", project], scratch)
            )
            record(
                "dry-run-preserves-project",
                not (project / "engineering-platform.toml").exists()
                and not preview.get("conflicts"),
            )
            applied = json.loads(
                command("install-apply", [cep, "install", project, "--apply"], scratch)
            )
            record(
                "installed-project-activation",
                applied["applied"] and (project / ".codex/config.toml").is_file(),
            )
            command("uninstall", [cep, "uninstall", project, "--apply"], scratch)
            record(
                "uninstall-restores-project",
                (project / "pyproject.toml").is_file()
                and not (project / "engineering-platform.toml").exists(),
            )
            demo = json.loads(
                command(
                    "demo",
                    [
                        cep,
                        "demo",
                        "--directory",
                        scratch / "demo",
                        "--budget-minutes",
                        "1",
                    ],
                    scratch,
                )
            )
            record(
                "installed-fixture-submission-without-worker",
                demo["executed"] is False
                and (scratch / "demo/project/task_cli.py").is_file(),
            )
            command(
                "demo-status",
                [cep, "status", "--control", scratch / "demo/control"],
                scratch,
            )
            source = scratch / "sdist"
            source.mkdir()
            with tarfile.open(sdist) as archive:
                archive.extractall(source, filter="data")
            unpacked = source / top
            command(
                "sdist-publication-tests",
                [
                    python,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests",
                    "-p",
                    "test_publication.py",
                    "-v",
                ],
                unpacked,
                extra_env={"PYTHONPATH": str(unpacked / "src")},
            )
            command(
                "sdist-packaging-tests",
                [
                    python,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests",
                    "-p",
                    "test_packaging.py",
                    "-v",
                ],
                unpacked,
                extra_env={"PYTHONPATH": str(unpacked / "src")},
            )
        report["status"] = "passed"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
    finally:
        (evidence / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "checks": len(report["checks"]),
                "failed_check": next(
                    (
                        item["name"]
                        for item in report["checks"]
                        if not item["passed"]
                    ),
                    None if report["status"] == "passed" else "verification-exception",
                ),
                "evidence": str(evidence),
            }
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

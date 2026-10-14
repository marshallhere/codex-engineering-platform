"""Read OpenSpec requirements as contracts, never as completion evidence."""

from __future__ import annotations
import hashlib
from pathlib import Path
import re

ID = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+"


def validate_task_graph(tasks: list[dict]) -> list[str]:
    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")
    graph = {}
    for task in tasks:
        if (
            not isinstance(task, dict)
            or not isinstance(task.get("id"), str)
            or not task["id"]
        ):
            raise ValueError("task must have a nonempty id")
        task_id = task["id"]
        if task_id in graph:
            raise ValueError(f"duplicate task {task_id}")
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list) or any(
            not isinstance(x, str) for x in dependencies
        ):
            raise ValueError("depends_on must contain task IDs")
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("duplicate dependency")
        graph[task_id] = dependencies
    ordered, visiting, visited = [], set(), set()

    def visit(task_id):
        if task_id not in graph:
            raise ValueError(f"unknown dependency {task_id}")
        if task_id in visiting:
            raise ValueError("task dependency cycle")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in graph[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)
        ordered.append(task_id)

    for task_id in graph:
        visit(task_id)
    return ordered


def load_change(repo: Path, slug: str) -> dict:
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("invalid OpenSpec change slug")
    root = Path(repo).resolve(strict=True)
    change = root / "openspec" / "changes" / slug
    if not change.resolve(strict=True).is_relative_to(root):
        raise ValueError("OpenSpec change escapes repository")
    if not change.is_dir():
        raise ValueError("change must be a directory")
    # No directory symlinks: rglob must not silently omit an external subtree.
    for directory in (root / "openspec", root / "openspec" / "changes", change):
        if directory.is_symlink():
            raise ValueError("OpenSpec directory symlinks are not allowed")
    files = []
    for path in sorted(change.rglob("*")):
        if path.is_symlink():
            raise ValueError("OpenSpec symlinks are not allowed")
        if path.is_file():
            if not path.resolve(strict=True).is_relative_to(root):
                raise ValueError("OpenSpec file escapes repository")
            files.append(path)
    if not (change / "proposal.md").is_file() or not (change / "tasks.md").is_file():
        raise ValueError("OpenSpec proposal.md and tasks.md are required")
    requirement_ids, scenarios, task_ids, file_hashes = [], {}, [], {}
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(change).as_posix()
        content = path.read_bytes()
        encoded_path = relative.encode()
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        file_hashes[relative] = hashlib.sha256(content).hexdigest()
        if path.suffix != ".md":
            continue
        text = content.decode("utf-8")
        if relative.startswith("specs/"):
            current = None
            for line in text.splitlines():
                if re.match(r"^### Requirement:", line):
                    match = re.match(rf"^### Requirement:\s+({ID})(?:\s|$)", line)
                    if not match:
                        raise ValueError(
                            "requirement heading needs a stable uppercase requirement ID"
                        )
                    current = match.group(1)
                    if current in requirement_ids:
                        raise ValueError(f"duplicate requirement {current}")
                    requirement_ids.append(current)
                    scenarios[current] = []
                elif re.match(r"^#### Scenario:", line):
                    if current is None:
                        raise ValueError("scenario without a requirement")
                    title = line.split(":", 1)[1].strip()
                    if not title:
                        raise ValueError("scenario title required")
                    scenarios[current].append(title)
        if relative == "tasks.md":
            task_ids = re.findall(
                rf"^\s*-\s+\[[ xX]\]\s+({ID})(?:\s|:|$)", text, re.MULTILINE
            )
    if not requirement_ids or any(not titles for titles in scenarios.values()):
        raise ValueError("requirements and scenarios are required")
    if not task_ids or len(task_ids) != len(set(task_ids)):
        raise ValueError("unique stable task IDs are required")
    if set(requirement_ids) - set(task_ids):
        raise ValueError("every requirement needs a task reference")
    return {
        "slug": slug,
        "requirement_ids": requirement_ids,
        "task_ids": task_ids,
        "scenarios": scenarios,
        "digest": digest.hexdigest(),
        "files": file_hashes,
    }

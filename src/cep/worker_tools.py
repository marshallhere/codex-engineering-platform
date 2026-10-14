"""Protected, narrowly scoped stdio MCP broker for qualified worker sessions."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import stat
import sys

MAX_REQUEST = 1_000_000
MAX_FILE = 128_000
TOOLS = [
    {
        "name": "cep_list_files",
        "description": "List project files without following symlinks.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "cep_read_file",
        "description": "Read a UTF-8 project file, up to 128 KB.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cep_apply_file",
        "description": "Write a UTF-8 implementation file when authorized.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cep_run_command",
        "description": "Execute direct argv inside the qualified sandbox, at most 30 seconds.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "argv": {"type": "array", "items": {"type": "string"}},
                "timeout_seconds": {"type": "number", "minimum": 0.001, "maximum": 30},
            },
            "required": ["argv"],
            "additionalProperties": False,
        },
    },
]


class WorkerTools:
    def __init__(
        self,
        repo: Path,
        scratch: Path,
        *,
        writable=False,
        sandbox=None,
        registry=None,
        readable_tools=(),
    ):
        from .sandbox import NativeSandbox

        self.repo = Path(repo).resolve(strict=True)
        if not self.repo.is_dir():
            raise ValueError("repository must be a directory")
        self.scratch = Path(scratch).resolve()
        self.scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.readable_tools = tuple(
            Path(p).resolve(strict=True) for p in readable_tools
        )
        self.writable = writable is True
        self.registry = Path(registry).resolve() if registry else None
        self.sandbox = sandbox or NativeSandbox()

    @staticmethod
    def _relative(value):
        if not isinstance(value, str) or not value or "\0" in value or "\\" in value:
            raise ValueError("nonempty relative POSIX path required")
        path = Path(value)
        if path.is_absolute() or any(
            part.casefold() in {"..", ".git", ".codex", ".cep"} for part in path.parts
        ):
            raise ValueError("path is outside authorized implementation files")
        if not path.parts or any(part == "." for part in value.split("/")):
            raise ValueError("file path required")
        return path

    def _parent(self, relative, create=False):
        fd = os.open(self.repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in relative.parts[:-1]:
                try:
                    child = os.open(
                        part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                    )
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(part, mode=0o755, dir_fd=fd)
                    child = os.open(
                        part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                    )
                os.close(fd)
                fd = child
            return fd
        except Exception:
            os.close(fd)
            raise

    def call(self, name: str, arguments: dict) -> dict:
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        schemas = {tool["name"]: tool["inputSchema"] for tool in TOOLS}
        if not isinstance(name, str) or name not in schemas:
            raise ValueError("unknown worker tool")
        schema = schemas[name]
        if set(arguments) - set(schema["properties"]) or set(
            schema.get("required", [])
        ) - set(arguments):
            raise ValueError("unexpected or missing tool arguments")
        if name == "cep_list_files":
            files = []

            def visit(fd, prefix=""):
                for filename in sorted(os.listdir(fd)):
                    if filename.casefold() in {".git", ".codex", ".cep"}:
                        continue
                    info = os.stat(filename, dir_fd=fd, follow_symlinks=False)
                    relative = prefix + filename
                    if stat.S_ISREG(info.st_mode):
                        files.append(relative)
                    elif stat.S_ISDIR(info.st_mode):
                        child = os.open(
                            filename,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd,
                        )
                        try:
                            visit(child, relative + "/")
                        finally:
                            os.close(child)
                    if len(files) >= 2000:
                        return

            fd = os.open(self.repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                visit(fd)
            finally:
                os.close(fd)
            return {"files": files, "truncated": len(files) >= 2000}
        if name == "cep_run_command":
            argv = arguments["argv"]
            if (
                not isinstance(argv, list)
                or not argv
                or any(not isinstance(a, str) or not a or "\0" in a for a in argv)
            ):
                raise ValueError("argv must contain nonempty strings")
            timeout = arguments.get("timeout_seconds", 30)
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout)
                or not 0 < timeout <= 30
            ):
                raise ValueError(
                    "timeout_seconds must be finite, positive and at most 30"
                )
            options = {"writable": self.writable}
            if self.readable_tools:
                options["readable"] = self.readable_tools
            if self.registry is not None:
                options["registry"] = self.registry
            return self.sandbox.run(argv, self.repo, self.scratch, timeout, **options)
        relative = self._relative(arguments["path"])
        writing = name == "cep_apply_file"
        parts = tuple(part.casefold() for part in relative.parts)
        filename = relative.name.casefold()
        if writing and (
            parts[0] == "openspec"
            or ".agents" in parts
            or filename in {"agents.md", "agents.override.md"}
            or any(part in {"tests", "test", "__tests__"} for part in parts)
            or filename.startswith("test_")
            or filename.endswith(("_test.go", ".test.ts", ".spec.ts", ".test.tsx"))
        ):
            raise ValueError(
                "Frozen requirements and authoritative instructions cannot be edited by workers"
            )
        if writing and not self.writable:
            raise ValueError("reviewer tools are read-only")
        data = None
        if writing:
            if not isinstance(arguments["content"], str):
                raise ValueError("content must be UTF-8 text")
            data = arguments["content"].encode("utf-8")
            if len(data) > MAX_FILE:
                raise ValueError("content exceeds 128 KB")
        parent = self._parent(relative, create=writing)
        try:
            flags = (os.O_WRONLY | os.O_CREAT) if writing else os.O_RDONLY
            fd = os.open(
                relative.name,
                flags | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o644,
                dir_fd=parent,
            )
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError(
                        "ordinary unlinked-alias-free project files required"
                    )
                if writing:
                    os.ftruncate(fd, 0)
                    with os.fdopen(fd, "wb", closefd=False) as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
                    return {"path": relative.as_posix(), "bytes": len(data)}
                if info.st_size > MAX_FILE:
                    raise ValueError("file exceeds 128 KB")
                with os.fdopen(fd, "rb", closefd=False) as handle:
                    content = handle.read(MAX_FILE + 1)
                if len(content) > MAX_FILE:
                    raise ValueError("file exceeds 128 KB")
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise ValueError("binary file is not readable as UTF-8") from error
                return {
                    "path": relative.as_posix(),
                    "content": text,
                    "bytes": len(content),
                }
            finally:
                os.close(fd)
        finally:
            os.close(parent)

    def handle(self, request: dict) -> dict | None:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid request"},
            }
        if "id" not in request:
            return None
        response = {"jsonrpc": "2.0", "id": request["id"]}
        method, params = request.get("method"), request.get("params", {})
        if method == "initialize":
            response["result"] = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cep-worker-tools", "version": "0.1.0"},
            }
        elif method == "ping":
            response["result"] = {}
        elif method == "tools/list":
            response["result"] = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                if not isinstance(params, dict):
                    raise ValueError("params must be an object")
                value = self.call(params.get("name"), params.get("arguments", {}))
                response["result"] = {
                    "content": [
                        {"type": "text", "text": json.dumps(value, ensure_ascii=True)}
                    ],
                    "isError": False,
                }
            except (ValueError, OSError) as error:
                response["result"] = {
                    "content": [{"type": "text", "text": str(error)}],
                    "isError": True,
                }
        else:
            response["error"] = {"code": -32601, "message": "Unknown method"}
        return response


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--writable", action="store_true")
    parser.add_argument("--readonly", action="store_true")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--readable-tool", action="append", type=Path, default=[])
    args = parser.parse_args(argv)
    if args.writable and args.readonly:
        parser.error("choose one access mode")
    broker = WorkerTools(
        args.repo,
        args.scratch,
        writable=args.writable,
        registry=args.registry,
        readable_tools=args.readable_tool,
    )
    stream = sys.stdin.buffer
    while True:
        line = stream.readline(MAX_REQUEST + 1)
        if not line:
            break
        if len(line) > MAX_REQUEST:
            # Oversized messages terminate the connection rather than parse tails.
            return 2
        try:
            request = json.loads(line)
            response = broker.handle(request)
        except (ValueError, UnicodeDecodeError):
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
        if response is not None:
            print(json.dumps(response, ensure_ascii=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build only the explicitly listed plugin and disposable reference assets."""

import json
from pathlib import Path, PurePosixPath
import shutil


def collect_assets(root: Path) -> list[tuple[Path, Path]]:
    """Reject missing or linked source assets; never discover local private files."""
    manifest = json.loads((root / "packaging/assets.json").read_text())
    if set(manifest) != {"schema_version", "groups"} or manifest["schema_version"] != 1:
        raise ValueError("Unsupported packaging asset manifest")
    result, seen = [], set()
    expected = {"plugin": "bundle", "examples": "fixtures"}
    for group in manifest["groups"]:
        if set(group) != {"source", "destination", "files"}:
            raise ValueError("Invalid packaging asset group")
        source, destination = group["source"], group["destination"]
        if source not in expected or expected[source] != destination:
            raise ValueError("Invalid packaging asset destination")
        for value in group["files"]:
            if not isinstance(value, str):
                raise ValueError("Unsafe packaging asset path")
            relative = PurePosixPath(value)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or str(relative) != value
            ):
                raise ValueError("Unsafe packaging asset path")
            path = root / source / relative
            key = source + "/" + value
            if key in seen:
                raise ValueError("Duplicate packaging asset")
            seen.add(key)
            if any(
                part.is_symlink()
                for part in (path, *path.parents)
                if part != root and root in part.parents
            ):
                raise ValueError("Linked packaging assets are forbidden")
            if not path.is_file():
                raise ValueError("Missing packaging asset")
            result.append((path, Path("cep") / destination / relative))
    if {group["source"] for group in manifest["groups"]} != set(expected):
        raise ValueError("Missing packaging asset group")
    return result


def copy_assets(root: Path, build_lib: Path) -> None:
    assets = collect_assets(root)
    if build_lib.is_symlink() or (build_lib / "cep").is_symlink():
        raise ValueError("Linked packaging destination is forbidden")
    # Repeated local builds must not retain assets removed from the manifest.
    for name in ("bundle", "fixtures"):
        target = build_lib / "cep" / name
        if target.is_symlink():
            raise ValueError("Linked packaging destination is forbidden")
        if target.exists():
            shutil.rmtree(target)
    for source, relative in assets:
        target = build_lib / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


if __name__ == "__main__":
    from setuptools import setup
    from setuptools.command.build_py import build_py

    class BuildWithAssets(build_py):
        def run(self):
            super().run()
            copy_assets(Path(__file__).parent, Path(self.build_lib))

    setup(cmdclass={"build_py": BuildWithAssets})

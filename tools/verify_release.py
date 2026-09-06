"""Reject a release tag that does not match project metadata."""

from __future__ import annotations

import argparse
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import cast


def project_version(manifest: Path) -> str:
    document = tomllib.loads(manifest.read_text(encoding="utf-8"))
    project_value: object = document.get("project")
    if not isinstance(project_value, dict):
        raise ValueError(f"{manifest} has no [project] table")
    project = cast(dict[str, object], project_value)
    version: object = project.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{manifest} has no valid project version")
    return version


def verify_release(manifest: Path, tag: str) -> None:
    expected = f"v{project_version(manifest)}"
    if tag != expected:
        raise ValueError(f"release tag {tag!r} does not match {expected!r}")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--tag", required=True)
    command.add_argument("--manifest", type=Path, default=Path("pyproject.toml"))
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    verify_release(cast(Path, args.manifest), cast(str, args.tag))
    print(f"release tag {args.tag} matches project metadata")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

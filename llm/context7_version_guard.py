#!/usr/bin/env python3
"""Claude PreToolUse hook: deny Context7 queries that ignore the project's pinned version."""

import json
import re
import sys
import tomllib
from pathlib import Path

REQUIREMENT = re.compile(r"(?m)^\s*([A-Za-z0-9._-]+)(?:\[[^\]]*\])?\s*==\s*([^\s;#]+)")
DIST_INFO = re.compile(r"(.+?)-(\d[^-]*)\.dist-info$")


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def package_names(library_id: str) -> set[str] | None:
    parts = library_id.strip("/").split("/")
    if len(parts) != 2:
        return None
    org, project = parts
    # ponytail: name guessed from the Context7 id; a package under another name is not checked.
    return {norm(project), norm(project.removesuffix(".js")), norm(f"{org}-{project}")}


def project_roots(cwd: Path) -> list[Path]:
    for path in [cwd, *cwd.parents]:
        if (path / ".git").exists():
            return list(dict.fromkeys([cwd, path]))
    return [cwd, *sorted(c for c in cwd.iterdir() if (c / ".git").exists())]


def pinned_versions(root: Path, names: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for venv in (".venv", "venv"):
        for info in (root / venv).glob("lib/python*/site-packages/*.dist-info"):
            match = DIST_INFO.match(info.name)
            if match and norm(match[1]) in names:
                found.setdefault(match[2], f"{root.name}/{venv}")
    for lock in ("uv.lock", "poetry.lock"):
        if (root / lock).is_file():
            for package in tomllib.loads((root / lock).read_text(encoding="utf-8")).get("package", []):
                if norm(package.get("name", "")) in names and package.get("version"):
                    found.setdefault(package["version"], f"{root.name}/{lock}")
    for requirements in root.glob("requirements*.txt"):
        for name, version in REQUIREMENT.findall(requirements.read_text(encoding="utf-8")):
            if norm(name) in names:
                found.setdefault(version, f"{root.name}/{requirements.name}")
    for name in names:
        manifest = root / "node_modules" / name / "package.json"
        if manifest.is_file():
            found.setdefault(json.loads(manifest.read_text(encoding="utf-8"))["version"], f"{root.name}/node_modules")
    return found


def mentions(text: str, version: str) -> bool:
    major_minor = ".".join(version.split(".")[:2])
    return version in text or re.search(rf"(?<![\d.]){re.escape(major_minor)}(?!\d)", text) is not None


def check(tool_input: dict, cwd: Path) -> str | None:
    library_id = tool_input.get("libraryId", "")
    names = package_names(library_id)
    if not names:
        return None
    found: dict[str, str] = {}
    for root in project_roots(cwd):
        for version, source in pinned_versions(root, names).items():
            found.setdefault(version, source)
    text = f"{library_id} {tool_input.get('query', '')}"
    if not found or any(mentions(text, version) for version in found):
        return None
    pins = ", ".join(f"{version} ({source})" for version, source in found.items())
    return (
        f"The project pins {library_id.rsplit('/', 1)[-1]} {pins}. Query that version: use "
        f"'{library_id}/<version>' if resolve-library-id listed it, otherwise name the version in the query."
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        reason = check(payload.get("tool_input") or {}, Path(payload.get("cwd") or ".").resolve())
    except (OSError, ValueError, KeyError):
        return
    if reason:
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            sys.stdout,
        )


if __name__ == "__main__":
    main()

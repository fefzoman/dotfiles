#!/usr/bin/env python3
"""Claude and Codex Bash hook: deny literal ctx7 queries that ignore pinned versions."""

import json
import argparse
import re
import shlex
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
    query = str(tool_input.get("query") or "")
    if re.search(r"/(?:v|release[-_])?\d+\.\d+(?:\.\d+)?$", library_id) or re.search(
        r"\btarget version:\s*v?\d+\.\d+(?:\.\d+)?\b", query, re.IGNORECASE
    ):
        return None
    names = package_names(library_id)
    if not names:
        return None
    found: dict[str, str] = {}
    for root in project_roots(cwd):
        for version, source in pinned_versions(root, names).items():
            found.setdefault(version, source)
    text = f"{library_id} {query}"
    if not found or any(mentions(text, version) for version in found):
        return None
    pins = ", ".join(f"{version} ({source})" for version, source in found.items())
    return (
        f"The project pins {library_id.rsplit('/', 1)[-1]} {pins}. Query that version: use "
        f"'{library_id}/<version>' if ctx7 library listed it, otherwise name the version in the query. "
        "For upgrade research, write 'target version: X.Y.Z' and verify the returned source covers that target."
    )


def cli_inputs(command: str):
    if "ctx7" not in command:
        return
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    tokens = list(lexer)
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False, exit_on_error=False)
    parser.add_argument("action", choices=("docs", "search", "library"))
    parser.add_argument("arguments", nargs="*")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--language")
    parser.add_argument("--base-url")
    parser.add_argument("--library", action="append", default=[])
    parser.add_argument("--library-version", default="")
    # shortcut: inspect literal CLI calls, extend this if generated shell commands become common.
    for index, token in enumerate(tokens):
        if Path(token).name != "ctx7":
            continue
        words = []
        for word in tokens[index + 1:]:
            if word in {";", "&&", "||", "|", "&", "(", ")"}:
                break
            words.append(word)
        try:
            args, extra = parser.parse_known_intermixed_args(words)
        except argparse.ArgumentError:
            continue
        if extra:
            continue
        if args.action == "docs" and len(args.arguments) == 2:
            yield {"libraryId": args.arguments[0], "query": args.arguments[1]}
        elif args.action == "search" and len(args.arguments) == 1:
            for library in args.library:
                yield {"libraryId": library if library.startswith("/") else f"/_/{library}",
                       "query": f"{args.arguments[0]} {args.library_version}"}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        cwd = Path(payload.get("cwd") or ".").resolve()
        reason = next((reason for query in cli_inputs((payload.get("tool_input") or {}).get("command", ""))
                       if (reason := check(query, cwd))), None)
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

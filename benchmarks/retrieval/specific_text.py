"""Compare equivalent text searches; requires the existing token-profiler Python."""

import hashlib
import json
from pathlib import Path
import statistics
import time

import tiktoken

from large import DIRECTORY, run


def main():
    destination = DIRECTORY / "specific-text-results.json"
    if destination.exists():
        raise ValueError("Preserve existing results first")
    manifest = json.loads((DIRECTORY / "specific-manifest.json").read_text())
    corpus = Path(manifest["corpus"])
    encoding = tiktoken.get_encoding("o200k_base")
    tools = ("rg", "ag", "ack")
    results = []
    for name, scope, needle, filenames in (
            ("local_literal", "Lib/test/test_subprocess.py", "shell=True", False),
            ("recursive_literal", "Lib", "follow_symlinks", False),
            ("typed_filenames", "Lib", "ExtendedInterpolation", True)):
        paths = run(["git", "ls-files", "--", scope], corpus, check=True).stdout.splitlines()
        expected = set()
        digest = hashlib.sha256()
        for path in paths:
            if not path.endswith(".py"):
                continue
            data = (corpus / path).read_bytes()
            digest.update(path.encode() + b"\0" + data)
            for number, line in enumerate(data.splitlines(), 1):
                if needle.encode() in line:
                    expected.add(path if filenames else f"{path}:{number}:{line.decode('utf-8')}")
        assert expected
        commands = {
            "rg": ["rg", "-F", "--type", "py", "--color", "never", *(["-l"] if filenames else ["-H", "-n", "--no-heading"])],
            "ag": ["ag", "--vimgrep", "-s", "-Q", "--python", "--nocolor", *(["-l"] if filenames else [])],
            "ack": ["ack", "--no-filter", "-Q", "--python", "--nocolor", *(["-l"] if filenames else ["-H", "--noheading"])],
        }
        commands = {tool: [*args, "--", needle, scope] for tool, args in commands.items()}
        samples = {tool: [] for tool in tools}
        outputs = {}
        for repeat in range(10):
            order = tools[repeat % 3:] + tools[:repeat % 3]
            for tool in order:
                start = time.perf_counter()
                result = run(commands[tool], corpus, check=True, input="")
                elapsed = time.perf_counter() - start
                normalized = set()
                for line in result.stdout.splitlines():
                    if tool == "ag" and not filenames:
                        file, row, column, text = line.split(":", 3)
                        line = f"{file}:{row}:{text}"
                    normalized.add(line)
                assert normalized == expected, (name, tool, len(normalized), len(expected))
                if repeat:
                    samples[tool].append(elapsed)
                outputs[tool] = result.stdout
        canonical = "\n".join(sorted(expected)) + "\n"
        results.append(dict(task=name, source_sha256=digest.hexdigest(), matches=len(expected),
                            normalized_output_tokens=len(encoding.encode(canonical)),
                            tools={tool: dict(command=commands[tool], median_seconds=statistics.median(samples[tool]),
                                              samples=samples[tool], raw_output_tokens=len(encoding.encode(outputs[tool])))
                                   for tool in tools}))
    document = dict(tokenizer="o200k_base", tokenizer_version=tiktoken.__version__, warmups=1, repeats=9,
                    note="Rotated order; subprocess wall time including startup. Output tokens are not total model consumption.",
                    tools={tool: run([tool, "--version"], corpus, check=True).stdout for tool in tools}, results=results)
    destination.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

import ast
import hashlib
import json
import os
from pathlib import Path
import shlex
import statistics
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(tempfile.mkdtemp(prefix='smart-read-benchmark-'))
TASKS = [
    ('line-count', 'llm/read_hint.py', 'line_count', 'How does line_count handle missing files and count lines?'),
    ('shell-targets', 'llm/read_hint.py', 'bash_targets', 'How does bash_targets handle quoted paths pipelines and redirections?'),
    ('version-match', 'llm/context7_version_guard.py', 'mentions', 'How does mentions match pinned package versions in a query?'),
    ('pinned-versions', 'llm/context7_version_guard.py', 'pinned_versions', 'Where does pinned_versions discover package version pins and installed package metadata?'),
    ('jsonl-tail', 'llm/idle_compact.py', 'records', 'How does records read JSONL tails and skip invalid sidechain records?'),
    ('plugin-policy', 'llm/agent_config.py', 'context_efficiency', 'How does context_efficiency enable Ponytail and disable Superpowers for Codex and Claude?'),
    ('plugin-install', 'llm/ai-install.sh', 'install_ponytail', 'How does install_ponytail install and update Ponytail in all Codex and Claude profiles?'),
    ('small-known-file', 'llm/skills/natural-article/SKILL.md', None, 'What are the natural-article skill writing rules and delivery checks?'),
]


def run(command):
    start = time.perf_counter()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60,
                            env={**os.environ, 'RTK_DISABLED': '1'})
    assert result.returncode == 0, (command, result.returncode, result.stderr)
    return result.stdout + result.stderr, time.perf_counter() - start


def tokens(text):
    path = ARTIFACTS / 'token-input.txt'
    path.write_text(text)
    output, _ = run(['token-count', str(path)])
    return int(output.strip())


assert tokens('Hello world') == 2
results = []
for task_id, file, symbol, query in TASKS:
    source = (ROOT / file).read_text()
    lines = source.splitlines()
    if file.endswith('.py'):
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == symbol)
        start, end = node.lineno, node.end_lineno
    elif symbol:
        start = next(i for i, line in enumerate(lines, 1) if line.startswith(symbol + '()'))
        end = next(i for i in range(start, len(lines) + 1) if lines[i - 1] == '}')
    else:
        start, end = 1, len(lines)
    expected = [line.strip() for line in lines[start - 1:end] if line.strip() and not line.lstrip().startswith('#')]
    assert expected
    precise = ['sed', '-n', f'{start},{end}p', file]
    commands = {
        'whole-file': ['cat', file],
        'targeted-rg': ['rg', '-n', '-C', '12', '^' + ('def ' if file.endswith('.py') else '') + symbol, file] if symbol else ['cat', file],
        'smart-read': ['smart-read', 'search', query, '--lexical', '--path', file, '-k', '2'],
        'known-range-sed': precise,
    }
    task = {'id': task_id, 'file': file, 'query': query, 'required_range': [start, end],
            'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'methods': {}}
    for method, command in commands.items():
        outputs, times = [], []
        for _ in range(3):
            output, seconds = run(command)
            outputs.append(output)
            times.append(seconds)
        assert len(set(outputs)) == 1, (task_id, method, 'unstable output')
        output = outputs[0]
        covered = sum(line in output for line in expected)
        followup = None
        followup_output = ''
        if covered != len(expected):
            followup = precise
            followup_output, _ = run(followup)
        assert all(line in output + followup_output for line in expected), (task_id, method)
        raw = ARTIFACTS / f'{task_id}-{method}.txt'
        raw.write_text(output)
        if followup:
            raw.with_suffix('.followup.txt').write_text(followup_output)
        command_text = shlex.join(command)
        command_tokens = tokens(command_text)
        output_tokens = tokens(output)
        followup_tokens = tokens(shlex.join(followup)) + tokens(followup_output) if followup else 0
        task['methods'][method] = {
            'command': command_text, 'output_tokens': output_tokens, 'command_tokens': command_tokens,
            'initial_tokens': output_tokens + command_tokens, 'covered_lines': covered,
            'required_lines': len(expected), 'complete_initially': covered == len(expected),
            'followup_command': shlex.join(followup) if followup else None,
            'followup_tokens': followup_tokens,
            'complete_tokens': output_tokens + command_tokens + followup_tokens,
            'median_seconds': round(statistics.median(times), 6), 'raw_output': str(raw),
        }
    results.append(task)
    print(task_id, {method: (value['complete_tokens'], value['complete_initially']) for method, value in task['methods'].items()}, flush=True)

summary = {method: {
    'output_tokens': sum(t['methods'][method]['output_tokens'] for t in results),
    'initial_tokens': sum(t['methods'][method]['initial_tokens'] for t in results),
    'complete_tokens': sum(t['methods'][method]['complete_tokens'] for t in results),
    'complete_initially': sum(t['methods'][method]['complete_initially'] for t in results),
    'median_seconds': round(statistics.median(t['methods'][method]['median_seconds'] for t in results), 6),
} for method in commands}
commit, _ = run(['git', 'rev-parse', 'HEAD'])
document = {'commit': commit.strip(), 'tokenizer': 'o200k_base via installed token-count',
            'repetitions': 3, 'artifacts': str(ARTIFACTS), 'summary': summary, 'tasks': results}
path = ROOT / 'benchmarks/smart_read/results.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(document, indent=2) + '\n')
print(json.dumps(summary, indent=2))
print('Artifacts:', ARTIFACTS)

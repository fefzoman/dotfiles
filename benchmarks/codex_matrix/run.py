import concurrent.futures
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path.home() / 'codex-matrix-runs-20261016'
COMMIT = 'a5d36f3'
SETTINGS = [('gpt-6-luna', 'low'), ('gpt-6.1-sol', 'medium'),
            ('gpt-6.1-sol', 'high'), ('gpt-6-astra', 'high')]
RATES = {'gpt-6-luna': (0.10, 0.01, 0.125, 0.50),
         'gpt-6.1-sol': (2.00, 0.10, 2.50, 10.00),
         'gpt-6-astra': (10.00, 1.00, 12.50, 50.00)}
TASKS = {
    'line-count': ('llm/read_hint.py',
        'Fix line_count so a nonempty final line without a newline is counted. Empty files must count as zero; '
        'trailing newlines must not create an extra line. Keep missing-file, directory and size-limit behavior.'),
    'quoted-shell': ('llm/read_hint.py',
        'Fix bash_targets to preserve shell control characters inside quoted filenames, including ;, &&, | and >. '
        'Still recognize unquoted command separators, and skip an entire pipeline or redirection segment. '
        'Preserve filename order and silently ignore unmatched quotes. No shell execution or new dependencies.'),
    'codex-hook': ('llm/read_hint.py',
        'Extend targets to accept Codex exec_command hooks, whose tool_input uses cmd. Preserve Claude Bash command '
        'and Read file_path handling, including ranged-read suppression. Empty inputs and unsupported tool names '
        'must return no targets. Pipelines must still produce no targets.'),
    'version-boundary': ('llm/context7_version_guard.py',
        'Fix mentions: accept either the exact pinned dotted numeric version or its major.minor as a complete '
        'version token, optionally prefixed with v. For a pin of 2.1.0 accept 2.1 and v2.1.0, but reject 12.1.0, '
        '2.10.0, 2.1.01 and 2.1.9. Punctuation may surround the version. Keep the public API.'),
    'npm-pins': ('llm/context7_version_guard.py',
        'Extend pinned_versions to read exact dotted numeric versions from dependencies and devDependencies in '
        'the root package.json. Match existing normalized package names. Ignore ranges (^, ~, wildcard, >=) '
        'and non-exact values. Report package.json as the source and preserve existing pin-source precedence. '
        'The existing check() caller must deny unversioned queries and accept matching major.minor queries for '
        'these new pins. Preserve current Python and installed-node_modules pin support.'),
    'tail-boundary': ('llm/idle_compact.py',
        'Fix records(path, tail): when the byte-tail starts exactly at a JSONL record boundary, retain that first '
        'complete record. When it starts inside a record, discard only the partial record. Preserve unbounded '
        'reads, malformed-record filtering and missing-file handling. The shared fix must also work through '
        'codex_records without changing its API.'),
}
REGRESSION = ['llm.test_read_hint', 'llm.test_context7_version_guard', 'llm.test_idle_compact']


def summarize_usage(usages, model):
    totals = {k: sum(u.get(k, 0) for u in usages) for k in
              ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
               'output_tokens', 'reasoning_output_tokens')}
    for usage in usages:
        if not all(k in usage for k in ('input_tokens', 'output_tokens', 'reasoning_output_tokens')):
            raise ValueError('Missing required usage counter')
        values = [usage.get(k, 0) for k in totals]
        if any(not isinstance(v, int) or v < 0 for v in values):
            raise ValueError('Invalid token counter')
        if usage.get('cached_input_tokens', 0) + usage.get('cache_write_input_tokens', 0) > usage['input_tokens']:
            raise ValueError('Cached and written tokens exceed input tokens')
        if usage.get('reasoning_output_tokens', 0) > usage['output_tokens']:
            raise ValueError('Reasoning tokens exceed output tokens')
        if usage['input_tokens'] > 272000:
            raise ValueError('This benchmark prices short-context calls only')
    calls = len(usages)
    fresh = totals['input_tokens'] - totals['cached_input_tokens']
    write = totals['cache_write_input_tokens']
    rate_input, rate_cache, rate_write, rate_output = RATES[model]
    cost = ((fresh - write) * rate_input + totals['cached_input_tokens'] * rate_cache
            + write * rate_write + totals['output_tokens'] * rate_output) / 1000000
    return dict(totals, calls=calls, fresh_input_per_call=fresh / calls if calls else None,
                reasoning_per_call=totals['reasoning_output_tokens'] / calls if calls else None,
                cache_hit_percent=100 * totals['cached_input_tokens'] / totals['input_tokens']
                if totals['input_tokens'] else None, api_equivalent_cost_usd=cost)


def command(args, cwd, timeout=60):
    return subprocess.run(args, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=timeout, env=os.environ | {'PYTHONDONTWRITEBYTECODE': '1'})


def prepare():
    ARTIFACTS.mkdir(exist_ok=True)
    baseline = ARTIFACTS / 'baseline'
    if not baseline.exists():
        subprocess.run(['git', 'clone', '--quiet', '--shared', str(ROOT), str(baseline)], check=True)
        subprocess.run(['git', '-C', str(baseline), 'checkout', '--quiet', '--detach', COMMIT], check=True)
    tests = command([sys.executable, '-m', 'unittest', *REGRESSION, '-q'], baseline)
    (ARTIFACTS / 'baseline-tests.log').write_text(tests.stdout + tests.stderr)
    assert tests.returncode == 0, tests.stderr
    for task in TASKS:
        result = command([sys.executable, str(ROOT / 'benchmarks/codex_matrix/grade.py'), str(baseline), task], baseline)
        assert result.returncode != 0 and 'AssertionError' in result.stderr, (task, result.stderr)
    print('Baseline: 21 regression tests pass; all six independent task graders fail as expected.', flush=True)
    return baseline


def trial(baseline, task, model, effort, repeat):
    name = f'{task}-{model}-{effort}-{repeat}'
    directory = ARTIFACTS / name
    if (directory / 'result.json').exists():
        return json.loads((directory / 'result.json').read_text())
    directory.mkdir(exist_ok=True)
    workspace = directory / 'repo'
    if workspace.exists():
        raise RuntimeError(f'Unfinished trial exists: {directory}')
    subprocess.run(['git', 'clone', '--quiet', '--shared', str(baseline), str(workspace)], check=True)
    target, description = TASKS[task]
    prompt = (
        'Implement this approved benchmark task directly in this repository. The requirements below are complete; '
        'do not ask questions or write design/plan documents. Use only local tools and the standard library. '
        'Do not delegate, access the network, install anything, change configuration, or commit. '
        f'Change only {target}; you may add new test files but must not change existing tests. '
        f'Python is {sys.executable}. Keep all existing behavior except the requested change.\n\n'
        f'{description}\n\nRun relevant tests, then briefly report the change and checks.'
    )
    (directory / 'prompt.txt').write_text(prompt)
    args = ['codex', 'exec', '--ignore-user-config', '--ignore-rules', '--json', '--color', 'never',
            '--sandbox', 'workspace-write', '--cd', str(workspace), '--model', model,
            '-c', f'model_reasoning_effort="{effort}"', '-c', 'service_tier="default"',
            '-c', 'approval_policy="never"', '--disable', 'multi_agent', prompt]
    start = time.monotonic()
    timed_out = False
    with (directory / 'events.jsonl').open('w') as out, (directory / 'stderr.log').open('w') as err:
        try:
            process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
            try:
                returncode = process.wait(timeout=240)
            except subprocess.TimeoutExpired:
                import signal
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=20)
                timed_out, returncode = True, process.returncode
        except OSError as error:
            raise RuntimeError(f'Cannot launch benchmark: {error}') from error
    elapsed = time.monotonic() - start
    events = [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines() if line.strip()]
    thread_ids = [e['thread_id'] for e in events if e.get('type') == 'thread.started']
    assert len(thread_ids) == 1, (name, events[-3:])
    rollout = list((Path.home() / '.codex/sessions').rglob(f'*{thread_ids[0]}.jsonl'))
    assert len(rollout) == 1, (name, rollout)
    records, contexts = {}, []
    for line in rollout[0].read_text().splitlines():
        row = json.loads(line)
        if row.get('type') == 'token_usage_record':
            records[row['payload']['response_id']] = row['payload']['usage']
        elif row.get('type') == 'turn_context':
            contexts.append((row['payload'].get('model'), row['payload'].get('effort')))
    assert contexts and set(contexts) == {(model, effort)}, (name, contexts)
    assert records, f'No per-call usage: {name}'
    usage = summarize_usage(list(records.values()), model)
    completed = [e['usage'] for e in events if e.get('type') == 'turn.completed']
    if completed:
        assert len(completed) == 1
        assert all(usage[k] == completed[0].get(k, 0) for k in
                   ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'output_tokens', 'reasoning_output_tokens'))
    grader = command([sys.executable, str(ROOT / 'benchmarks/codex_matrix/grade.py'), str(workspace), task], workspace)
    regressions = command([sys.executable, '-m', 'unittest', *REGRESSION, '-q'], workspace)
    (directory / 'grade.log').write_text(grader.stdout + grader.stderr + regressions.stdout + regressions.stderr)
    status = command(['git', 'status', '--porcelain', '--untracked-files=all'], workspace).stdout
    changed = [line[3:] for line in status.splitlines()]
    scope_ok = all(p == target or (line.startswith('?? ') and Path(p).name.startswith('test_') and p.endswith('.py'))
                   for line, p in zip(status.splitlines(), changed))
    head_ok = command(['git', 'rev-parse', '--short=7', 'HEAD'], workspace).stdout.strip() == COMMIT
    patch = command(['git', 'diff', '--no-ext-diff'], workspace)
    (directory / 'patch.diff').write_text(patch.stdout)
    success = returncode == 0 and not timed_out and bool(completed) and grader.returncode == 0 \
        and regressions.returncode == 0 and scope_ok and head_ok
    result = dict(task=task, model=model, effort=effort, repeat=repeat, thread_id=thread_ids[0],
                  elapsed_seconds=elapsed, exit_code=returncode, timed_out=timed_out,
                  task_tests_pass=grader.returncode == 0, regression_tests_pass=regressions.returncode == 0,
                  scope_ok=scope_ok, head_ok=head_ok, success=success, usage=usage)
    (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'{name}: {"PASS" if success else "FAIL"}; {usage["calls"]} calls; '
          f'${usage["api_equivalent_cost_usd"]:.4f}; {elapsed:.0f}s', flush=True)
    return result


def main():
    baseline = prepare()
    if '--prepare' in sys.argv:
        return
    jobs = []
    for repeat in range(2):
        for index, task in enumerate(TASKS):
            shift = (repeat * 2 + index) % len(SETTINGS)
            order = SETTINGS[shift:] + SETTINGS[:shift]
            jobs.extend((baseline, task, model, effort, repeat + 1) for model, effort in order)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: trial(*args), jobs))
    summary = []
    for model, effort in SETTINGS:
        runs = [r for r in results if (r['model'], r['effort']) == (model, effort)]
        tokens = [r['usage'] for r in runs]
        calls = sum(u['calls'] for u in tokens)
        total_input = sum(u['input_tokens'] for u in tokens)
        cached = sum(u['cached_input_tokens'] for u in tokens)
        summary.append(dict(model=model, effort=effort, trials=len(runs), successes=sum(r['success'] for r in runs),
                            calls=calls, fresh_input_per_call=(total_input - cached) / calls,
                            reasoning_per_call=sum(u['reasoning_output_tokens'] for u in tokens) / calls,
                            cache_hit_percent=100 * cached / total_input,
                            api_equivalent_cost_usd=sum(u['api_equivalent_cost_usd'] for u in tokens)))
    output = dict(commit=COMMIT, cli_version=command(['codex', '--version'], ROOT).stdout.strip(),
                  completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  repetitions=2, timeout_seconds=240, concurrency=2, rates_per_million=RATES,
                  pricing_source='https://developers.openai.com/api/docs/pricing',
                  tasks={k: {'target': v[0], 'prompt': v[1]} for k, v in TASKS.items()},
                  summary=summary, results=results)
    (ROOT / 'benchmarks/codex_matrix/results.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()

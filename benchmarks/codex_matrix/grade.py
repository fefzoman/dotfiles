import importlib.util
import json
import sys
import tempfile
from pathlib import Path


def load(root, name):
    spec = importlib.util.spec_from_file_location(name, root / 'llm' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def grade(root, task):
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        if task == 'line-count':
            module = load(root, 'read_hint')
            for text, expected in [('', 0), ('x', 1), ('x\n', 1), ('x\ny', 2), ('x\n' * 79 + 'x', 80)]:
                path = tmp / 'sample.py'
                path.write_text(text)
                assert module.line_count(path) == expected, (repr(text[:20]), expected)
            assert module.line_count(tmp / 'missing') == 0
            assert module.line_count(tmp) == 0
        elif task == 'quoted-shell':
            module = load(root, 'read_hint')
            cases = [
                ('cat "a;b.py"', ['a;b.py']),
                ("cat 'a&&b.py'", ['a&&b.py']),
                ('cat "a|b.py"', ['a|b.py']),
                ('cat "a>b.py"', ['a>b.py']),
                ('cat "a;b.py" && cat other.py', ['a;b.py', 'other.py']),
                ('cat x.py | head -2', []),
                ('cat x.py > out.txt', []),
                ('cat x.py < input.txt', []),
                ('cat "unfinished', []),
            ]
            for command, expected in cases:
                assert module.bash_targets(command) == expected, (command, expected)
        elif task == 'codex-hook':
            module = load(root, 'read_hint')
            assert module.targets({'tool_name': 'exec_command', 'tool_input': {'cmd': 'cat big.py'}}) == ['big.py']
            assert module.targets({'tool_name': 'Bash', 'tool_input': {'command': 'cat big.py'}}) == ['big.py']
            assert module.targets({'tool_name': 'Read', 'tool_input': {'file_path': 'big.py'}}) == ['big.py']
            assert module.targets({'tool_name': 'Read', 'tool_input': {'file_path': 'big.py', 'limit': 2}}) == []
            assert module.targets({'tool_name': 'exec_command', 'tool_input': {}}) == []
            assert module.targets({'tool_name': 'exec_command', 'tool_input': {'cmd': 'cat big.py | head'}}) == []
            for name in ['Write', 'Edit', 'unknown']:
                assert module.targets({'tool_name': name, 'tool_input': {'cmd': 'cat big.py'}}) == []
                assert module.targets({'tool_name': name, 'tool_input': {'command': 'cat big.py'}}) == []
        elif task == 'version-boundary':
            module = load(root, 'context7_version_guard')
            for text in ['package 2.1', 'package 2.1.0', '/org/project/v2.1.0', 'version 2.1.0, docs']:
                assert module.mentions(text, '2.1.0'), text
            for text in ['package 12.1.0', 'package 2.10.0', 'package 2.1.01', 'package 2.1.9', 'package 12.1']:
                assert not module.mentions(text, '2.1.0'), text
        elif task == 'npm-pins':
            module = load(root, 'context7_version_guard')
            (tmp / '.git').mkdir()
            (tmp / 'package.json').write_text(json.dumps({
                'dependencies': {'react': '19.1.0', 'vue': '^3.5.0', 'tilde': '~1.2.0',
                                 'wildcard': '*', 'comparison': '>=1.0.0', 'other': 'latest'},
                'devDependencies': {'typescript': '5.8.3'}}))
            pins = module.pinned_versions(tmp, {'react', 'vue', 'typescript', 'tilde', 'wildcard', 'comparison', 'other'})
            assert set(pins) == {'19.1.0', '5.8.3'}, pins
            assert all('package.json' in source for source in pins.values()), pins
            assert module.check({'libraryId': '/facebook/react', 'query': 'hooks'}, tmp) is not None
            assert module.check({'libraryId': '/facebook/react', 'query': 'react 19.1 hooks'}, tmp) is None
            assert module.check({'libraryId': '/vuejs/vue', 'query': 'routing'}, tmp) is None
            installed = tmp / 'node_modules/react'
            installed.mkdir(parents=True)
            (installed / 'package.json').write_text('{"version": "19.1.0"}')
            assert 'node_modules' in module.pinned_versions(tmp, {'react'})['19.1.0']
        elif task == 'tail-boundary':
            module = load(root, 'idle_compact')
            first = json.dumps({'n': 1}).encode() + b'\n'
            second = json.dumps({'n': 2}).encode() + b'\n'
            path = tmp / 'events.jsonl'
            path.write_bytes(first + second)
            assert module.records(path, len(second)) == [{'n': 2}]
            assert module.records(path, len(second) + 2) == [{'n': 2}]
            assert module.records(path) == [{'n': 1}, {'n': 2}]
            assert module.records(path, 1) == []
            assert module.records(tmp / 'missing') == []
            context = json.dumps({'type': 'turn_context', 'payload': {'model': 'sample'}}).encode() + b'\n'
            event = json.dumps({'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
                'last_token_usage': {'input_tokens': 42}}}}).encode() + b'\n'
            path.write_bytes(context + event)
            assert len(module.codex_records(path, len(event))) == 1
        else:
            raise ValueError(task)


if __name__ == '__main__':
    grade(Path(sys.argv[1]), sys.argv[2])
    print('PASS')

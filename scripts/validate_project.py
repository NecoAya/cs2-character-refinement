#!/usr/bin/env python3
"""Validate the curated repository, not a character model. Standard library only."""
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVACY_PATTERNS = [r'(?i)(?<![a-z0-9])[a-z]:[/\\]',
                    r'/' + r'Users' + r'/[^/\s]+/',
                    r'/' + r'home' + r'/[^/\s]+/',
                    r'gh[pousr]_[A-Za-z0-9]{20,}', r'github_pat_[A-Za-z0-9_]{20,}',
                    r'-----BEGIN [A-Z ]*PRIVATE KEY-----']


def contains_sensitive_pattern(text):
    return any(re.search(pattern, text) for pattern in PRIVACY_PATTERNS)


def validate():
    expected = json.loads((ROOT / 'release-files.json').read_text(encoding='utf-8'))
    if len(set(expected)) != len(expected):
        raise ValueError('Duplicate release file names')
    paths = []
    for name in expected:
        path = ROOT / name
        if not path.resolve().is_relative_to(ROOT) or path.is_symlink() or not path.is_file():
            raise ValueError(f'Missing or unsafe release member: {name}')
        paths.append(path)
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*')
              if p.is_file() and '.git' not in p.relative_to(ROOT).parts}
    if actual != set(expected):
        raise ValueError(f'Unlisted/missing repository files: {sorted(actual ^ set(expected))}')
    contents = {p: p.read_text(encoding='utf-8') for p in paths}
    for path, text in contents.items():
        if contains_sensitive_pattern(text):
            raise ValueError(f'Possible private path or credential in {path.relative_to(ROOT)}')
        if not text.endswith('\n'):
            raise ValueError(f'Missing final newline: {path.relative_to(ROOT)}')
        if path.suffix == '.py':
            ast.parse(text, filename=path.name)
        if path.suffix == '.json':
            json.loads(text)
        if path.suffix == '.md':
            for target in re.findall(r'\]\(([^)]+)\)', text):
                if '://' in target or target.startswith('#'):
                    continue
                link = (path.parent / target.split('#', 1)[0]).resolve()
                if not link.is_relative_to(ROOT) or not link.is_file():
                    raise ValueError(f'Broken or escaping document link in {path.relative_to(ROOT)}: {target}')
    skill = contents[ROOT / 'SKILL.md']
    if not skill.startswith('---\n') or len(skill.splitlines()) >= 500:
        raise ValueError('Invalid skill entrypoint boundary or length')
    front = skill.split('---', 2)[1]
    if not re.search(r'^name: cs2-character-refinement$', front, flags=re.M):
        raise ValueError('Skill name missing or changed')
    if not re.search(r'^description: "[^\n]+"$', front, flags=re.M):
        raise ValueError('Skill description must be a nonempty quoted line in this project')
    ui = contents[ROOT / 'agents/openai.yaml']
    if '$cs2-character-refinement' not in ui or 'allow_implicit_invocation: true' not in ui:
        raise ValueError('Skill invocation metadata missing')
    version = contents[ROOT / 'VERSION'].strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid release version')
    contract = json.loads(contents[ROOT / 'examples/task-contract.json'])
    if contract['example_only'] is not True or contract['baseline']['compiled_sha256'] is not None:
        raise ValueError('Example must not pretend to contain real input evidence')
    return {'status': 'passed', 'version': version, 'release_files': len(paths),
            'utf8_bytes': sum(p.stat().st_size for p in paths),
            'checks': ['exact release allowlist', 'UTF-8 and newlines', 'local documentation links',
                       'Python syntax', 'JSON syntax', 'required skill metadata', 'basic privacy patterns'],
            'limits': 'Not a full YAML schema validator, secret scanner or runtime model test.',
            'members': [{'path': p.relative_to(ROOT).as_posix(),
                         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]}


if __name__ == '__main__':
    try:
        print(json.dumps(validate(), ensure_ascii=False, indent=2))
    except (ValueError, OSError, SyntaxError, KeyError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)

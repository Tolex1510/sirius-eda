#!/usr/bin/env python3
"""Reproduce before/after on the same production money.py in temporary workspaces.
No mutation is ever applied to the working source tree.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/lab10/results'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for label, tests in [('before', ['test_money_baseline.py']),
                         ('after', ['test_money_baseline.py', 'test_money_regressions.py'])]:
        with tempfile.TemporaryDirectory(prefix='sirius-mutation-') as directory:
            work = Path(directory)
            (work / 'app/domain').mkdir(parents=True)
            for file in ['app/__init__.py', 'app/domain/__init__.py', 'app/domain/money.py']:
                shutil.copy2(ROOT / file, work / file)
            (work / 'tests').mkdir()
            for test in tests:
                shutil.copy2(ROOT / 'tests/mutation' / test, work / 'tests' / test)
            (work / 'setup.cfg').write_text('[mutmut]\nsource_paths=app/\nonly_mutate=app/domain/money.py\npytest_add_cli_args_test_selection=tests/\n')
            env = dict(os.environ, PACT_DO_NOT_TRACK='true')
            with (OUT / f'mutation-{label}.log').open('w') as log:
                subprocess.run([sys.executable, '-m', 'mutmut', 'run', '--max-children', '2'],
                               cwd=work, env=env, stdout=log, stderr=log, check=True, timeout=120)
            result = subprocess.run([sys.executable, '-m', 'mutmut', 'results'], cwd=work,
                                    env=env, capture_output=True, text=True, check=True)
            (OUT / f'mutation-{label}-results.txt').write_text(result.stdout)
            meta = list((work / 'mutants').rglob('*.meta'))
            snapshot = {str(p.relative_to(work / 'mutants')): json.loads(p.read_text()) for p in meta}
            (OUT / f'mutation-{label}.json').write_text(json.dumps(snapshot, indent=2)+'\n')
            # Save surviving diffs for explaining the added boundary checks.
            diffs = []
            for line in result.stdout.splitlines():
                if ': survived' in line:
                    name = line.strip().split(':')[0]
                    show = subprocess.run([sys.executable, '-m', 'mutmut', 'show', name], cwd=work,
                                          capture_output=True, text=True, check=True)
                    diffs.append(show.stdout)
            (OUT / f'mutation-{label}-survivors.diff').write_text('\n'.join(diffs))
            print(label, result.stdout, flush=True)


if __name__ == '__main__':
    main()

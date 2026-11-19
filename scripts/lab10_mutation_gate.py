"""Fail CI if mutants are untested/errors or the regression tests no longer improve detection."""
import json
from pathlib import Path


def counts(label):
    report = json.loads(Path(f'docs/lab10/results/mutation-{label}.json').read_text())
    statuses = [code for module in report.values() for code in module['exit_code_by_key'].values()]
    assert statuses and all(code in (0, 1) for code in statuses), 'Untested, timed-out or invalid mutants'
    return {'total':len(statuses), 'killed':statuses.count(1), 'survived':statuses.count(0)}


before, after = counts('before'), counts('after')
assert before['total'] == after['total'], 'Compare the same mutation population'
assert after['survived'] < before['survived'], 'Added boundary tests must kill previously surviving mutants'
print('before:', before, 'after:', after)

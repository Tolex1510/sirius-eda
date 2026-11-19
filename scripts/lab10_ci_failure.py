"""Local red-gate proof, without committing a broken test or altering application code."""
from pathlib import Path
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory(prefix='sirius-ci-red-') as directory:
    test = Path(directory) / 'test_deliberately_broken.py'
    test.write_text('def test_deliberately_broken():\n    assert 1 == 2\n')
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(test)], capture_output=True, text=True)
    assert result.returncode == 1, 'A broken assertion must fail the pytest command used by CI'
    out = Path('docs/lab10/results'); out.mkdir(parents=True, exist_ok=True)
    (out / 'local-red-gate.txt').write_text(result.stdout + '\npytest exit code: ' + str(result.returncode) + '\n')
    print('Expected pytest exit code 1 confirmed. This is a local check, not a GitHub Actions run.')

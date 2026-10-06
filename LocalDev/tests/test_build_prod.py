import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'LocalDev/scripts/build_prod.sh'


def test_build_and_check_preserve_prod_owned_files(tmp_path):
    prod = tmp_path / 'Prod'
    shutil.copytree(ROOT / 'Prod', prod)
    (prod / '.vercel').mkdir(exist_ok=True)
    (prod / '.vercel/project.json').write_text('deployment metadata')
    keep = ['README.md', 'package.json', '.gitignore', 'vercel.json',
            'secrets/.gitkeep', '.vercel/project.json']
    before = {p: (prod / p).read_bytes() for p in keep}
    env = dict(os.environ, PROD_DIR=str(prod))

    def run(*args):
        return subprocess.run(['bash', str(SCRIPT), *args], env=env,
                              capture_output=True, text=True)

    assert run('--check').returncode == 1
    (prod / 'api/obsolete.py').write_text('stale')
    result = run()
    assert result.returncode == 0, result.stderr
    assert run('--check').returncode == 0
    assert not (prod / 'api/obsolete.py').exists()
    assert not (prod / 'tests').exists()
    for path, content in before.items():
        assert (prod / path).read_bytes() == content
    assert json.loads((prod / 'vercel.json').read_text())['git']['deploymentEnabled'] is False
    assert (prod / 'api/index.py').read_bytes() == (ROOT / 'LocalDev/api/index.py').read_bytes()
    assert not list((prod / 'api').rglob('__pycache__'))
    assert not list((prod / 'fratos').rglob('.env*'))
    assert not (prod / 'fratos/node_modules').exists()
    assert not (prod / 'fratos/dist').exists()
    assert not any(line.startswith('pytest') for line in (prod / 'requirements.txt').read_text().splitlines())
    assert (prod / 'scripts/db_guard.py').exists()
    (prod / 'api/index.py').write_text('drift')
    assert run('--check').returncode == 1


def test_invalid_option_fails(tmp_path):
    result = subprocess.run(['bash', str(SCRIPT), '--unknown'],
                            env=dict(os.environ, PROD_DIR=str(tmp_path / 'unused')),
                            capture_output=True)
    assert result.returncode == 2
    assert not (tmp_path / 'unused').exists()


def test_check_missing_target_reports_drift_without_creating_it(tmp_path):
    prod = tmp_path / 'missing'
    result = subprocess.run(['bash', str(SCRIPT), '--check'],
                            env=dict(os.environ, PROD_DIR=str(prod)),
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert 'PROD DRIFT COUNTS:' in result.stdout
    assert not prod.exists()

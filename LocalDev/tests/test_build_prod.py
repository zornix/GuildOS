import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'LocalDev/scripts/build_prod.sh'


def test_build_and_check_preserve_prod_owned_files(tmp_path):
    prod = tmp_path / 'Prod'
    prod.mkdir()
    for path in ['README.md', 'package.json', '.gitignore', 'secrets/.gitkeep']:
        target = prod / path
        target.parent.mkdir(exist_ok=True)
        target.write_text('production owned')
    (prod / 'vercel.json').write_text(json.dumps(dict(
        json.loads((ROOT / 'LocalDev/vercel.json').read_text().replace('greekos', 'fratos')),
        git={'deploymentEnabled': False})))
    (prod / '.vercel').mkdir(exist_ok=True)
    (prod / '.vercel/project.json').write_text('deployment metadata')
    keep = ['README.md', 'package.json', '.gitignore', 'vercel.json',
            'secrets/.gitkeep', '.vercel/project.json']
    before = {p: (prod / p).read_bytes() for p in keep}
    env = dict(os.environ, PROD_DIR=str(prod))

    def run(*args):
        return subprocess.run(['bash', str(SCRIPT), *args], env=env,
                              capture_output=True, text=True)

    assert run().returncode == 0
    assert run('--check').returncode == 0
    (prod / 'api/index.py').write_text('stale')
    (prod / 'api/obsolete.py').write_text('extra')
    assert run('--check').returncode == 1
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
    assert all(p.name == '.env.example' for p in (prod / 'fratos').rglob('.env*'))
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


@pytest.mark.parametrize('enabled', [False, True])
def test_preserve_nested_deployment_config(tmp_path, enabled):
    prod = tmp_path / 'Prod'
    (prod / 'fratos').mkdir(parents=True)
    config = json.dumps({'git': {'deploymentEnabled': enabled}, 'custom': 'retained'}).encode() + b'\n'
    (prod / 'fratos/vercel.json').write_bytes(config)
    result = subprocess.run(['bash', str(SCRIPT)],
                            env=dict(os.environ, PROD_DIR=str(prod)),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    retained = (prod / 'fratos/vercel.json').read_bytes()
    assert json.loads(retained) == {'git': {'deploymentEnabled': False}, 'custom': 'retained'}
    if not enabled:
        assert retained == config


def test_env_example_is_synced_but_secrets_are_excluded(tmp_path):
    source = tmp_path / 'repo/LocalDev'
    for name in ['api', 'greekos', 'migrations', 'scripts']:
        (source / name).mkdir(parents=True)
    for name in ['build_prod.sh', 'migrate_db.py', 'db_guard.py',
                 'migration_checksums.py', 'check_prod_status.py', 'set_officer_password.py']:
        shutil.copyfile(ROOT / 'LocalDev/scripts' / name, source / 'scripts' / name)
    (source / 'requirements.txt').write_text('')
    (source / 'vercel.json').write_text('{}')
    (source / 'greekos/.env.example').write_text('EXAMPLE=placeholder\n')
    (source / 'greekos/.env').write_text('PRIVATE=synthetic\n')
    prod = tmp_path / 'output'
    result = subprocess.run(['bash', str(source / 'scripts/build_prod.sh')],
                            env=dict(os.environ, PROD_DIR=str(prod)),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (prod / 'fratos/.env.example').read_bytes() == (source / 'greekos/.env.example').read_bytes()
    assert not (prod / 'fratos/.env').exists()

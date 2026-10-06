#!/usr/bin/env bash
set -euo pipefail

# Production-owned files; vercel.json is retained byte-for-byte when its
# generated configuration agrees, otherwise regenerated with git deploys off.
KEEP=(README.md package.json .gitignore secrets .vercel vercel.json)
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE="$ROOT/LocalDev"
TARGET="${PROD_DIR:-$ROOT/Prod}"
CHECK=false
if [[ $# -gt 0 ]]; then
    if [[ $# -ne 1 || $1 != --check ]]; then
        echo 'Usage: build_prod.sh [--check]' >&2
        exit 2
    fi
    CHECK=true
fi
# Reject source/target overlap before creating or copying anything.
python3 - "$SOURCE" "$TARGET" <<'PY'
import pathlib, sys
source, target = map(lambda p: pathlib.Path(p).resolve(), sys.argv[1:])
if source == target or source in target.parents or target in source.parents:
    sys.exit('Refusing overlapping LocalDev and PROD_DIR paths')
PY
STAGING="$(mktemp -d)"
trap 'rm -rf -- "$STAGING"' EXIT
FILTERS=()
for entry in "${KEEP[@]}"; do
    if [[ -e "$TARGET/$entry" ]]; then
        cp -a -- "$TARGET/$entry" "$STAGING/"
    fi
    if [[ $entry != vercel.json ]]; then
        FILTERS+=(--exclude="/$entry")
    fi
done
rsync -a --exclude='__pycache__' "$SOURCE/api/" "$STAGING/api/"
rsync -a --exclude='node_modules' --exclude='dist' --exclude='.env*' "$SOURCE/greekos/" "$STAGING/fratos/"
rsync -a "$SOURCE/migrations/" "$STAGING/migrations/"
mkdir -p "$STAGING/scripts"
for entry in migrate_db.py db_guard.py migration_checksums.py check_prod_status.py; do
    cp -a -- "$SOURCE/scripts/$entry" "$STAGING/scripts/"
done
python3 - "$SOURCE" "$STAGING" <<'PY'
import json, pathlib, re, sys
source, staging = map(pathlib.Path, sys.argv[1:])
lines = (source / 'requirements.txt').read_text().splitlines(keepends=True)
(staging / 'requirements.txt').write_text(''.join(line for line in lines if not re.match(r'\s*pytest', line, re.I)))
config = json.loads((source / 'vercel.json').read_text().replace('greekos', 'fratos'))
path = staging / 'vercel.json'
old = json.loads(path.read_text()) if path.exists() else {}
config['git'] = dict(old.get('git', {}), deploymentEnabled=False)
if old != config:
    path.write_text(json.dumps(config, indent=2) + '\n')
PY
if $CHECK; then
    result=0
    if [[ -d "$TARGET" ]]; then
        diff -rq -- "$STAGING" "$TARGET" || result=$?
    else
        echo "Missing production directory: $TARGET"
        result=1
    fi
    python3 - "$STAGING" "$TARGET" <<'PY'
import pathlib, sys
expected, actual = map(pathlib.Path, sys.argv[1:])
def files(root):
    return {str(p.relative_to(root)): p for p in root.rglob('*') if p.is_file()}
a, b = files(expected), files(actual)
differing = sum(a[k].read_bytes() != b[k].read_bytes() for k in a.keys() & b.keys())
print(f'PROD DRIFT COUNTS: differing={differing} missing={len(a.keys()-b.keys())} extra={len(b.keys()-a.keys())}')
PY
    exit "$result"
fi
mkdir -p -- "$TARGET"
rsync -a --delete "${FILTERS[@]}" "$STAGING/" "$TARGET/"

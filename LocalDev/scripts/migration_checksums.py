#!/usr/bin/env python3
"""Checksums for migrations/*.sql, so an edit to an applied migration is visible.

  python3 scripts/migration_checksums.py --update   add lines for new files (never rewrites a line)
  python3 scripts/migration_checksums.py --check    exit 1 if a listed file changed or a file is unlisted
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
MANIFEST = MIGRATIONS_DIR / "CHECKSUMS"


def file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest(manifest: Path = MANIFEST) -> dict[str, str]:
    if not manifest.exists():
        return {}
    out = {}
    for line in manifest.read_text().splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            out[name.strip()] = digest
    return out


def current(migrations_dir: Path = MIGRATIONS_DIR) -> dict[str, str]:
    return {p.name: file_checksum(p) for p in sorted(migrations_dir.glob("*.sql"))}


def changed(listed: dict[str, str], now: dict[str, str]) -> list[str]:
    """Listed files whose content no longer matches (or that were deleted)."""
    return sorted(n for n, d in listed.items() if now.get(n) != d)


def unlisted(listed: dict[str, str], now: dict[str, str]) -> list[str]:
    return sorted(n for n in now if n not in listed)


def main(argv: list[str]) -> int:
    listed, now = read_manifest(), current()
    if "--update" in argv:
        merged = dict(listed)
        for name in unlisted(listed, now):
            merged[name] = now[name]
        MANIFEST.write_text("".join(f"{merged[n]}  {n}\n" for n in sorted(merged)))
        print(f"CHECKSUMS: {len(merged)} entries")
        return 0
    bad, missing = changed(listed, now), unlisted(listed, now)
    for n in bad:
        print(f"changed after it was recorded: {n}", file=sys.stderr)
    for n in missing:
        print(f"not in CHECKSUMS (run --update): {n}", file=sys.stderr)
    return 1 if (bad or missing) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

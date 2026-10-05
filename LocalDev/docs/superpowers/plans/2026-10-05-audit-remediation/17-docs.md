# 17 · Docs: describe the tree that exists

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Every statement you write must be checked against the files first. If you cannot verify something, leave it out.

**Stream:** `17-docs` · **Wave:** 4 (after every code stream is merged) · **Agent:** Gemini 3.8 Flash medium (Antigravity CLI) · **Branch:** `fix/audit-17-docs`
**Findings:** F-041, the documentation half of F-031, F-038, F-068, R-05, and the conventions in report §11
**Goal:** a new person or agent who reads the docs is sent to files that exist and told rules the code actually follows.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` card F-041, §8 row "Docs describe intent, not code", §10, §11; `00-README.md` "Decisions".

## Global constraints

- Allowed files (repo-root paths): `CLAUDE.md`, `CONTEXT.md`, `LocalDev/CLAUDE.md`, `LocalDev/docs/ARCHITECTURE.md`, `LocalDev/docs/CODEMAP.md`, `LocalDev/docs/TREASURY_ARCHITECTURE.md`, `LocalDev/docs/ops-runbook.md`, `LocalDev/docs/services/README.md`, `docs/adr/0002-supabase-is-hosted-postgres-only.md`, new `docs/adr/0006-authority-from-member-roles.md`, new `docs/adr/0007-chapter-timezone.md`, `LocalDev/tests/test_docs_paths.py` (new).
- No code changes. No file moves. Keep each document's existing headings unless a heading names something that no longer exists.
- Writing rules: short sentences, plain words, no marketing adjectives, no "robust/seamless/comprehensive". State facts. Use the same names the code uses.
- Before writing a path, run `ls` on it. Before writing a command, check it exists in `LocalDev/package.json`, `greekos/package.json` or `scripts/`.

## Review focus

1. Every backticked path in the three CLAUDE/ARCHITECTURE/CODEMAP files exists (Task 1's test enforces it).
2. Nothing says the frontend is Next.js, has an `app/` directory, `lib/api-client.ts`, `lib/adapters/`, `lib/contracts/`, `lib/formatters/` or `config/theme/tokens.ts`.
3. The docs do not promise behaviour the code lacks (for example "transactional outbox", "RLS enforces tenant isolation").
4. ADR text records a decision and its reason in a few lines; it does not restate the code.

---

### Task 1: a test that fails on a path that does not exist

**Files:** `LocalDev/tests/test_docs_paths.py`

- [ ] **Step 1: write the test**

```python
"""Docs must not point at files that do not exist (F-041)."""
import re
from pathlib import Path

import pytest

LOCALDEV = Path(__file__).resolve().parent.parent
REPO = LOCALDEV.parent
DOCS = [REPO / "CLAUDE.md", LOCALDEV / "CLAUDE.md", LOCALDEV / "docs" / "ARCHITECTURE.md", LOCALDEV / "docs" / "CODEMAP.md"]
# `path/with/slash.ext` or `dir/sub/` in backticks; skips globs, placeholders and URLs.
PATH = re.compile(r"`([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+/?)`")


def _candidates(doc: Path):
    for raw in PATH.findall(doc.read_text()):
        if any(ch in raw for ch in "*<>{}") or raw.startswith(("http", "api/<", "/api/")):
            continue
        yield raw


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_backticked_paths_exist(doc):
    missing = [
        raw for raw in _candidates(doc)
        if not any((base / raw).exists() for base in (REPO, LOCALDEV, LOCALDEV / "greekos", LOCALDEV / "greekos" / "src"))
    ]
    assert not missing, f"{doc.name} points at paths that do not exist: {missing}"
```

- [ ] **Step 2: run** `python3 -m pytest tests/test_docs_paths.py -q` from `LocalDev/`. Expected: FAIL, listing the dead paths. Keep that list; it is your work list for Tasks 2 and 3. Route paths such as `/api/health` are skipped by the test on purpose.

### Task 2: `LocalDev/CLAUDE.md` and the root `CLAUDE.md`

- [ ] **Frontend architecture section:** delete the current section and write it from the real tree. Run `ls LocalDev/greekos/src LocalDev/greekos/src/hooks LocalDev/greekos/src/lib LocalDev/greekos/src/components` first. State: single-page React app, no router, `App.tsx` switches tabs; `hooks/useAppData.ts` composes the domain hooks; `api.ts` is the fetch client and DTO types; `adapters.ts` converts DTOs to the shapes in `types.ts`; pure logic lives in `lib/*.ts` with a sibling `*.test.ts` run by `npm test`; permissions come from `GET /api/rbac/me/permissions` and are checked with `can()`; money is integer cents and is displayed through `formatMoney` in `formatters.ts`. Rules: a success toast only after the server answers; nothing on screen that the server did not return; new logic goes in `lib/` with a test.
- [ ] **Platform section:** add `PostgresClient.transaction()` with a three-line example (copy the contract from `01-db-client.md`, "Interfaces"), and the three caller rules. Change the sentence "`call_rpc` — the ONLY multi-write path" to say: a plpgsql RPC is the path for trust-boundary writes that need an audit row; `transaction()` is for multi-statement writes that do not.
- [ ] **Hard rules:** fix "Every tenant table carries `chapter_id` and has RLS enabled" to match report §2 ("RLS exists on 43 tables; the app connects as the table owner, so RLS never applies at runtime; Supabase API roles hold no grants since migration 0171"). Add: permissions come only from `member_roles` (the `members.role` column is display-only); `admin` and `president` are granted only by an admin, and every chapter keeps at least one admin; event times are local to `chapters.timezone`; the outbox enqueue runs after commit unless given a transaction client.
- [ ] **"What this is" paragraph:** fix the git-root path (`/home/mshi/GuildOS` → the repo root, written as "one level up"), and remove the "Temporary: production `DATABASE_URL` still points at the demo project" paragraph only if `00-README.md` "Decisions" says it is resolved; otherwise leave it.
- [ ] **Add a "Conventions" section** with the table from report §11, columns "Do" and "Do not", one row per concern, wording taken from that table and checked against the merged code.
- [ ] **Root `CLAUDE.md`:** replace "`Prod/api` is the LocalDev API" with what `00-README.md` "Decisions" D22 says about `Prod/`.

### Task 3: `ARCHITECTURE.md`, `CODEMAP.md`, ADR-0002, services README

- [ ] `ARCHITECTURE.md`: every mention of Next.js or `fratos` as the frontend becomes greekos (Vite + React). Fix or remove each dead path from Task 1's list.
- [ ] `CODEMAP.md`: remove entries for files deleted by streams 11, 12, 16 (`api/tasks/api/operations.py`, `api/tasks/services/templates.py`, `api/cron/core/templates.py`, `api/treasury/services/fine_processor.py`, `api/treasury/api/pagination.py`, `api/treasury/core/idempotency.py`); add `api/platform/message_templates.py`, `api/platform/errors.py`, `api/events/core/timing.py`, `api/treasury/services/remaining.py`; stop listing `AuditLogger` / `LedgerWriter` as production writers.
- [ ] `docs/adr/0002-…md`: replace references to `api/postgres_client.py` and `api/db.py` with `api/platform/postgres.py` and `api/platform/db.py`. Do not change the decision.
- [ ] `TREASURY_ARCHITECTURE.md` (F-031): add a short section "What the ledger is": balances are computed from the operational tables (`unpaid_invoices`, `verified_payments`, `finance_adjustments`, `refunds`); amount and owner columns on those rows are frozen by trigger (migration 0168); `big_ledger` is an append-only shadow log; `core/rebuild.py` reports drift between the two and changes nothing. Remove any sentence that calls the ledger the source of balances.
- [ ] Run the Task 1 test. Expected: PASS.

### Task 4: two ADRs and the glossary

- [ ] `docs/adr/0006-authority-from-member-roles.md`: context (two sources of truth; revoke did not revoke: F-022, F-023, F-006), decision (permissions = `member_roles` plus an implicit `member` baseline; `members.role` display-only and kept in step by the RPCs; the chapter creator is its `admin`; `admin` and `president` are granted or revoked only by an admin; several admins may exist and the last one cannot be removed; existing chapters got their earliest officer as admin), consequences (roster import no longer mints officers; officers may still approve their own payments, by product decision D2).
- [ ] `docs/adr/0007-chapter-timezone.md`: context (naive `date`+`time` treated as UTC: F-002, F-060), decision (`chapters.timezone`, default `America/Los_Angeles`; Python uses `api/events/core/timing.py`, SQL uses `ev_local_start`), consequences (no UI to change it yet; a missing time means end of day for "has it started" and midnight for the unclaim lock).
- [ ] `CONTEXT.md`: add or fix glossary entries for **cancelled event**, **waived fine**, **door code** (sign-in required), **top role**, **heartbeat**. One or two lines each, in the file's existing style.
- [ ] `LocalDev/docs/ops-runbook.md` (F-038, F-068, R-05): leave every `TBD` that only a human can fill, and add directly under the backup section a checklist titled "To verify by hand" with four items: Supabase plan and backup retention; PITR on or off; date and duration of the last restore drill; Data API disabled. Add a section "Messaging facts": SMS consent follows the phone number across chapters by design (STOP and START apply to every member row with that number); the outbox drain handles about 50 messages per run, every 5 minutes; `/api/health` reports `degraded` when the drain has not finished in 15 minutes.

## Report

Finish with the report block from `00-README.md` ("What to hand back"). List every statement you removed because you could not verify it.

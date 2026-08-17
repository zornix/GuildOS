# Implementation plan — tenant guards for attendance mutations (+ prod fail-fast)

Date: 2026-07-17
Order: independent — **lands before `imp-platform-module.md`** (step 3) and the
rest of the queue. This is a security fix: today any officer of any chapter can
write attendance and excuse data into any other chapter. Coordination notes for
the two plans it brushes against are at the bottom.
Scope: backend + one migration (`api/attendance/`, `api/config.py`,
`api/index.py`, `migrations/`, `requirements.txt`, `CLAUDE.md`). No frontend
changes; response shapes are preserved exactly.

Contract: decisions settled here; implementer executes as written, reports
drift. Authority: ADR-0001 (permission keys, never role checks), ADR-0002
(direct Postgres is the one access path — RLS is not the runtime enforcement
layer), CLAUDE.md hard rules (trust-boundary mutations via plpgsql RPCs;
tenant guards + idempotency + audit_logs inside the RPC body).

## Verified findings (2026-07-17, file:line evidence)

Two mutation endpoints accept foreign UUIDs with no chapter check:

- **`manual_checkin`** (`api/attendance/api/attendance.py:165`) takes arbitrary
  `event_id` / `member_id` path params and upserts `attendance` rows and
  deletes/inserts `excuses` rows without ever confirming the event or the
  member belongs to the officer's chapter. Its `excused` branch is also
  non-atomic (attendance upsert + excuses delete + excuses insert as three
  independent statements).
- **`review_excuse`** (`api/attendance/api/excuses.py:92`) updates any
  `excuse_id` with no chapter predicate — a foreign officer can approve or
  deny another chapter's excuses.

The database cannot express the tenant invariant for these tables:
`attendance`, `excuses`, and `checkin_links` (`migrations/0001_initial_schema.sql:74,95,143`)
have no `chapter_id` and no migration through 0145 adds one or enables RLS on
them — while 24 later migrations (e.g. `0084_attendance_sessions_tables.sql`)
do both for every newer tenant table.

Latent breakage found while verifying: `review_excuse`'s follow-on "remove any
associated fine" (`excuses.py:119-124`) deletes from `fines`, which is frozen
read-only since `migrations/0012_fines_to_invoices_migration.sql:73-76` — if
any row matches, the trigger raises and the request 500s *after* the excuse
was already approved. The live fine object (`unpaid_invoices(kind=fine)`,
created by `api/treasury/services/fine_processor.py` → `tr_create_invoice`) is
never waived. The documented behavior ("If approved, remove any associated
fine") has been dead since 0012.

Adjacent config gaps closed in the same pass: `JWT_SECRET` defaults to
`"local-dev-secret"` (`api/config.py:10`) with nothing forcing a real value in
production, and `requirements.txt` is fully unpinned.

**Already correctly guarded — do not touch:** `checkin_via_link`
(`attendance.py:26` checks event chapter), `checkin_via_phone`
(`attendance.py:73` filters member lookup by the event's chapter),
`get_attendance` roster (`attendance.py:117`), `submit_excuse`
(`excuses.py:26`), `list_excuses` (`excuses.py:77`), and
`active_checkin_links` (chapter-scoped service call).

## Settled decisions

- **D1 — The two mutations become `at_*` RPCs.** `at_set_attendance` and
  `at_review_excuse`, following the `ev_*`/`tk_*` convention
  (`migrations/0142_jobs_v1_lifecycle.sql:684` `tk_commit_task` is the
  template): `p_chapter_id` first param, tenant validation of every referenced
  row inside the transaction, `p_idempotency_key TEXT DEFAULT NULL` honoring
  the `idempotency_keys` table, `audit_logs` writes, `RETURNS JSONB`. Handlers
  shrink to parse → `call_rpc` → respond.
- **D2 — The three 0001 tables get `chapter_id`, derived not trusted.** Add
  `chapter_id UUID REFERENCES chapters(id)` to `attendance`, `excuses`, and
  `checkin_links`; backfill from `events.chapter_id` via `event_id`; set
  NOT NULL; index it. A `BEFORE INSERT OR UPDATE` trigger on each table
  derives `chapter_id` from the row's event and **raises on mismatch** — the
  column can never disagree with the event it hangs off, and existing Python
  insert paths (link check-in, excuse submission) need no changes. Enable RLS
  with policies mirroring `0084_attendance_sessions_tables.sql` for parity
  with the other 24 tenant tables. Per ADR-0002 the psycopg connection
  bypasses RLS at runtime; the enforcement layer for these mutations is D1 —
  RLS here is schema parity, not the guard.
- **D3 — The frozen-fines delete dies; approval voids the fine invoice.**
  `at_review_excuse`, on `approved`, voids any **unpaid** invoice with
  `kind='fine'` matching the excuse's `(source event, member)` via the
  existing `tr_void_invoice` (`migrations/0122_treasury_v1_void_invoice.sql:14`),
  same transaction, reason `'excuse approved'`. No matching unpaid invoice →
  no-op (the normal case: `fine_processor` skips already-excused members, so
  an invoice only exists when the excuse is approved *after* fine processing
  ran). Paid invoices are never touched — refunds stay a human treasury
  action. This restores the documented behavior with the invoice model that
  replaced `fines`.
- **D4 — These routes gate on permission keys now, not `require_officer`.**
  The keys already exist and are seeded (`api/attendance/auth.py`:
  `ATTENDANCE_OVERRIDE = "attendance:override"`,
  `EXCUSE_REVIEW = "attendance:excuse:review"`; seeds in
  `migrations/0083_rbac_seed_rpcs.sql:33-35`). Use
  `require_permission(...)` per `api/rbac/auth.py`. This shrinks
  `imp-one-gate.md`'s later sweep by two routes; it does not conflict with it.
- **D5 — Production refuses to boot misconfigured.** `api/config.py` gains
  `VERCEL_ENV: str = ""` (Vercel sets it) and a `is_production` property
  (`VERCEL_ENV == "production"`). At import time in `api/index.py`, if
  `is_production`: raise `RuntimeError` naming every violation when
  `JWT_SECRET == "local-dev-secret"`, or `DATABASE_URL` is unset (ADR-0002:
  prod runs on the direct-Postgres path), or `DEV_AUTH_BYPASS` is true. A
  failed import means the Vercel function fails to deploy — loud, not latent.
  Preview deployments (`VERCEL_ENV == "preview"`) are deliberately not
  guarded.
- **D6 — `requirements.txt` gets `==` pins.** Pin every line to the version
  currently installed in the dev venv (`pip freeze` as source of truth),
  keeping extras syntax (`fastapi[standard]==…`). `imp-platform-module.md`
  will later delete the `supabase` line; pinning it meanwhile is harmless.
- **D7 — Audit action catalog gains two actions** via the established
  dual-format extension pattern (`migrations/0142_jobs_v1_lifecycle.sql:569`,
  pattern: 0100): `ATTENDANCE_OVERRIDDEN` (written by `at_set_attendance`)
  and `EXCUSE_REVIEWED` (written by `at_review_excuse`, metadata carrying the
  decision). This is the sanctioned way the frozen catalog grows — copy the
  0142 §9 DO-block verbatim with the new array.
- **D8 — CLAUDE.md tells the truth.** The hard rule "Every tenant table
  carries `chapter_id` and has RLS enabled" becomes accurate for these tables
  after D2; amend the same bullet to state that on the direct-Postgres path
  (ADR-0002) the runtime tenant guard is the RPC layer, with RLS as
  defense-in-depth for any non-privileged access.

## Phases

### Phase A — migration `0146_attendance_tenant_guards.sql`

One file, in this order:

1. D2: `ALTER TABLE … ADD COLUMN chapter_id UUID REFERENCES chapters(id)` for
   `attendance`, `excuses`, `checkin_links`; backfill
   (`UPDATE t SET chapter_id = e.chapter_id FROM events e WHERE t.event_id = e.id`);
   `SET NOT NULL`; `CREATE INDEX`. Derive/validate trigger function (one
   shared `at_derive_chapter_id()` is fine) + three triggers. RLS enable +
   policies mirroring 0084.
2. D7: audit action catalog extension DO-block.
3. D1/D3: `at_set_attendance(p_chapter_id, p_event_id, p_member_id, p_status,
   p_reason, p_actor_id, p_idempotency_key DEFAULT NULL)` — validates the
   event belongs to `p_chapter_id` (raise `'event not found in chapter'`),
   the member is an active member of `p_chapter_id`, and the actor is an
   active member of `p_chapter_id`; then reproduces the three branches of the
   current handler (`attendance.py:169-229`) atomically: `excused` requires
   non-empty reason, upserts attendance not-checked-in, replaces any excuse
   with an approved one stamped `reviewed_by = p_actor_id`; `absent` upserts
   not-checked-in and deletes any excuse; `present` upserts checked-in
   `method='manual'`. Writes one `audit_logs` row (`ATTENDANCE_OVERRIDDEN`,
   metadata: status, event, member). Returns the same JSON shape the handler
   returns today.
4. `at_review_excuse(p_chapter_id, p_excuse_id, p_status, p_actor_id,
   p_idempotency_key DEFAULT NULL)` — `p_status` must be
   `approved`/`denied`; loads the excuse joined to its event and raises
   `'excuse not found in chapter'` unless the event's chapter matches;
   updates status/reviewed_by/reviewed_at; on approve, performs the D3
   `tr_void_invoice` call; writes `audit_logs` (`EXCUSE_REVIEWED`). Returns
   the updated excuse row as JSONB (today's response shape).

### Phase B — backend rewiring

- `api/attendance/db/__init__.py` + `api/attendance/db/rpc.py` — byte-for-byte
  the canonical 8-line wrapper (copy `api/events/db/rpc.py`).
- `manual_checkin` (`attendance.py:165`) → gate
  `require_permission(ATTENDANCE_OVERRIDE)`, body becomes
  `call_rpc("at_set_attendance", {...})` with the actor's `chapter_id`/`id`
  from the resolved user; map RPC errors the way the events handlers map
  `ev_*` errors (`'not found'` → 404, chapter/authority messages → 403,
  validation → 400). Same for `review_excuse` (`excuses.py:92`) →
  `require_permission(EXCUSE_REVIEW)` → `call_rpc("at_review_excuse", …)`.
  Delete the dead fines block. Response bodies unchanged.

### Phase C — config hardening

- D5 in `api/config.py` + `api/index.py`.
- D6: rewrite `requirements.txt` with pins.

### Phase D — docs

- D8 CLAUDE.md bullet.

## Verification

- **New pytest module `tests/attendance/test_tenant_guards.py`** (superuser
  connection style, mirror `tests/treasury/`): seed two chapters; officer of
  chapter B calling `at_set_attendance` / `at_review_excuse` against chapter
  A's event/excuse **fails**; same-chapter calls succeed for all three status
  branches; excused branch is atomic (force a failure mid-way and assert no
  partial rows); approve-after-fine-processing voids the unpaid fine invoice
  (assert via `unpaid_invoices` and `big_ledger`); approve-before-processing
  is a no-op void; idempotency key replay returns the recorded result;
  `audit_logs` rows written with the new actions; direct
  `INSERT INTO attendance` with a mismatched `chapter_id` raises (D2
  trigger).
- **Full suite:** `python3 -m pytest` from `LocalDev/` — green.
- **e2e:** `cd fratos && npm run test:e2e` — `events`, `excuses`, `checkin`
  specs green (manual attendance and excuse review flows exercise the new
  RPCs through unchanged response shapes).
- **Config guard:** unit test that `Settings(VERCEL_ENV="production")` with
  default `JWT_SECRET` makes the index-time check raise, and that dev
  (empty `VERCEL_ENV`) boots as today.

## Coordination notes

- **`imp-platform-module.md`** (step 3): its sweep deletes per-domain `db/`
  directories — its inventory must now also include the new
  `api/attendance/db/rpc.py` created here. One-line addition to that plan
  when this lands.
- **`imp-one-gate.md`** (step 4): two of its `require_officer` swap sites are
  done early by D4; its sweep should find them already converted. Its D2
  (passwords for every member) is unaffected and still needed — this plan
  deliberately does **not** touch login, token lifetime, or revocation.
- **Not covered here** (deliberately deferred, revisit after the queue):
  JWT lifetime/refresh/revocation, login rate-limiting, SMS outbox worker,
  response models, observability.

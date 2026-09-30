# Stage 1 — sweep: mechanical inventories on Gemini Flash (30 min, 6 parallel runs)

Purpose: build the fact tables the diggers start from, cheaply. These are *inventories*,
not judgements. Flash is fast and cheap; correctness is checked by spot-checks (1.3).

## 1.1 Task files

Each task = `tasks/ctx.md` + the block below + this footer:

```
OUTPUT: return ONLY a JSON object matching the schema you were given. Be exhaustive: this is an inventory, every row counts. Put anything you could not determine in coverage_notes. No findings, no opinions.
```

Build with `cat tasks/ctx.md - <<'EOF' > archive/audit-2026-09-30/stage1/<id>/task.md` and
paste the block.

### S1-routes → `schemas/inv-routes.json`
```
MANDATE — ROUTE INVENTORY. Enumerate EVERY route handler under api/ (grep -rn "@router\.\|@app\." api/ and also the routers included in api/index.py and each domain's api/router.py). For each handler record method, mounted path (prefix from index.py/router.py + decorator path), file:line, function name, how it authenticates (Depends(get_current_user) = jwt; cron/platform/twilio secrets; none), the permission keys passed to require_permission or checked inline via has_permission, whether permission checking is a dependency, an inline call, a legacy user["role"] string check, or absent, how the handler scopes to the caller's chapter (Python .eq("chapter_id") filter, RPC body guard, both, none, or not applicable for unauthenticated/own-record routes), and whether it writes (direct table writes, RPC, both, none). Expected count ≈125; report the count you found. Read every handler body — do not infer from the decorator.
```

### S2-db → `schemas/inv-db.json`
```
MANDATE — DATABASE INVENTORY as an applied whole. Read all files in migrations/ in lexical order. For every table that exists at the end: creating migration, has chapter_id, RLS enabled (ENABLE ROW LEVEL SECURITY anywhere, minus any DISABLE), FORCE RLS, foreign keys, unique constraints, check constraints, triggers (name + function), indexes, and every money/amount column with its type (flag NUMERIC/float ones). For every plpgsql function that exists at the end (last CREATE OR REPLACE wins): defining migration, SECURITY DEFINER, whether the body validates referenced rows against the caller's chapter_id (yes/partial/no), whether it takes an idempotency key, whether it inserts audit_logs / big_ledger, what row locking it uses (FOR UPDATE, SKIP LOCKED, advisory, none), and its Python callers (grep 'rpc("name"' and call_rpc("name") under api/). Summarise GRANT/REVOKE statements in one paragraph. List migrations with more than one git commit (git log --oneline --follow per file, or git log --format=%h -- migrations/NNNN*.sql).
```

### S3-code → `schemas/inv-code.json`
```
MANDATE — CODE-SHAPE INVENTORY of api/ and greekos/src. (a) Cross-domain import graph: every 'from api.<x>' / 'import api.<x>' where <x> differs from the importing domain, with file:line; then list cycles. (b) Every .py/.ts/.tsx file over 300 lines with its line count. (c) Duplicate or near-duplicate helpers: functions/types with the same purpose in two or more places (timestamp parsing, UUID str() wrapping, chapter-scoped member lookup, money formatting, fetch wrappers, notification enqueue, 'rpc error → HTTP error' translators). Read the bodies; list locations. (d) Every TODO/FIXME/HACK/XXX/'ponytail:'/'temporary'/'for now' marker with file:line and the text. (e) Candidate dead code: module-level functions/classes/exports in api/ and greekos/src with zero references outside their own file (grep -rn each name across LocalDev, excluding tests; say how you checked). Skip Prod/ and archive/.
```

### S4-tests → `schemas/inv-tests.json`
```
MANDATE — TEST-SUITE INVENTORY. For every file under tests/ and every *.test.ts under greekos/src: test count (def test_ / test( ), subsystem, whether it talks to the real database (psycopg2 / conftest DB fixtures), whether it uses FastAPI TestClient, how it authenticates (real JWT minted via the auth code, dependency_overrides bypass, superuser SQL, none), what it mocks or monkeypatches (list the production symbols), assertion strength (strong = checks DB state or full response bodies; medium = status codes + a field; weak = 'is not None' / 'no exception'), and which of these it covers: happy_path, negative, tenant_isolation, permission_denied, concurrency, idempotency, rollback, migration, trigger, money_math, state_transition. Read each file; do not guess from names. List shared fixtures from every conftest.py. List every monkeypatch/patch target that names a production symbol.
```

### S5-frontend → `schemas/inv-frontend.json`
```
MANDATE — FRONTEND INVENTORY of greekos/src. For every file: line count, kind (module/component/hook/lib/api/adapter/types/config/test/other), the API calls it makes (function names from api.ts), and its useEffect count. List every fetch wrapper in api.ts and elsewhere (name path:line). For each concern — fetching, mutations, forms, validation, modals, toasts, auth_state, errors, loading, caching, dates, api_types, permissions, tables, pagination — list the distinct approaches in use and where each is used (this is the 'competing approaches' table; read the components, do not guess). List every isOfficer / role-string check (path:line text). List every 'as SomeType' cast at an API or module boundary. Compare each DTO type in api.ts/types.ts against the matching Pydantic schema in api/<domain>/api/schemas.py and list concrete field differences (name, optionality, type).
```

### S6-config → `schemas/inv-config.json`
```
MANDATE — CONFIG, DEPENDENCY AND DEPLOYMENT INVENTORY. Environment variables: union of Settings fields in api/config.py, names in .env.example, names in .env (NAMES only: grep -oE '^[A-Z_]+=' .env), and every os.environ/os.getenv/settings.<X> use in api/ and scripts/ — one row per name with where it is used, its default, and whether the default is risky in production (dev bypasses, empty secrets, permissive CORS). Python deps: every line in LocalDev/requirements.txt and Prod/requirements.txt with both pins and where it is imported (grep). npm deps: every dependency/devDependency in greekos/package.json with where it is imported. Deployment facts: one line each from LocalDev/vercel.json, Prod/vercel.json, .github/workflows/*.yml (what runs, on what, with which env). Scripts: every file in scripts/ with the guard it uses (db_guard require_demo, none, ...) and what damage it could do against prod. Sensitive logging: every logger/print/HTTPException detail that could include a token, secret, password hash, phone, email, or raw exception text (path:line).
```

## 1.2 Launch (all six in one turn, background)

```bash
P=/home/mshik/GuildOS/LocalDev/docs/superpowers/plans/2026-09-30-forensic-audit
O=/home/mshik/GuildOS/archive/audit-2026-09-30/stage1
M="Gemini 3.6 Flash (High)"
for t in S1-routes S2-db S3-code S4-tests S5-frontend S6-config; do
  s=$(echo $t | sed 's/S[0-9]-//')            # routes, db, code, tests, frontend, config
  RUN_TESTS=1 SCHEMA=$P/schemas/inv-$s.json TIMEOUT=1800 $P/run-task.sh agy $O/$t/task.md $O/$t "$M" &
done; wait
```
(In the lead session: six separate `Bash` calls with `run_in_background: true` instead of `&`.)

`RUN_TESTS=1` is required for agy even here: without `--dangerously-skip-permissions` its
sandbox auto-denies every shell command (grep, git log) and the run returns empty with exit 0
(learned 2026-09-30, all six first attempts failed that way). The runner's git-status check
still catches edits.

If a Flash run returns an empty `result.json` or fewer rows than expected (S1 < 110
routes, S2 < 50 tables, S4 < 80 files), rerun once on `"Gemini 3.1 Pro (High)"`. If it
times out, split the mandate by directory (e.g. S1 by domain) and merge the JSON by hand.

## 1.3 Spot-check (lead, 10 min)

For each inventory pick 3 random rows and verify against the code with grep/sed. Any wrong
row → mark the inventory "untrusted" in its `meta.txt` and tell the diggers so in the stage 2
footer ("S3 dead-code list is unverified; confirm before citing"). Do not fix inventories by
hand; they are inputs, not deliverables.

## 1.4 Quick wins for the report

Copy into `stage1/notes.md` anything that already answers a brief question: route count,
tables without RLS, NUMERIC money columns, markers list, env vars with no Settings field,
deps never imported. These land in report §2 (architecture map) and §9/§11 nearly verbatim.

## Done when

Six `result.json` files parse, spot-checks logged in `stage1/notes.md`.

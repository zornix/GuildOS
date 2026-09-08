# Prod ops readiness: backups, prod project ref, monitoring

Research note for issue #55 (map #41). Written 2026-09-08.

Scope: what has to be true before pilot chapters put real data into the
production Supabase project behind the Vercel deploy. Four questions — Supabase
backup/PITR options and cost, how to fill `PROD_PROJECT_REFS` safely, what
Sentry needs to be live, and what else a small Vercel + Supabase deployment
needs before real users.

Every external claim carries its source URL and the date it was fetched.
Supabase docs pages carry no "last updated" stamp, so those are "as served on
2026-09-08" and nothing more. Claims about this repository cite a file and are
checkable from the tree.

> **Update, same day, after the plan facts came back from the maintainer:**
> the Vercel project is **already on Pro**, and the plan is to run the pilot on
> the **existing Free demo Supabase project** rather than a separate prod one.
> That is a legitimate choice for a closed pilot, but it moves the risk rather
> than removing it — see § 0 below, which supersedes parts of the checklist.
> Sections 1–4 stay as written: they are what you need the day prod becomes its
> own project.

**The headline as originally written:** two of the four things blocking a real
pilot are paid plans, not code — Vercel Pro ($20/mo, because Hobby forbids
commercial use *and* caps cron at once per day, while `vercel.json` schedules
one every 5 minutes) and Supabase Pro ($25/mo, because the Free plan has **no
backups at all** and pauses after a week of inactivity). Vercel Pro is settled.
Supabase Pro is the open question, and § 0 is the honest cost of saying no.

---

## 0. If the demo project *is* production

Three consequences, in order of how much they should worry you.

### 0.1 Every fail-closed write guard is now pointed at real data

`scripts/db_guard.py` separates exactly two things: the demo project and
everything else. If the demo project holds pilot chapters, that separation stops
meaning anything, and three commands that are currently safe become writes
against real data:

- **`python3 -m pytest` permanently pollutes the ledger.** ADR-0002 states the
  reason the guard exists: "pytest refuses to run against a URL containing the
  prod project ref — `big_ledger`/`audit_logs` are append-only, so test garbage
  in prod would be permanent." `tests/treasury/conftest.py` says the same in its
  own docstring: the append-only tables "accumulate and cannot be truncated".
  The per-test `chapter_id` fixture keeps *tenant* tables tidy, but the two
  DELETE-blocked audit tables grow forever, in whatever database the suite runs
  against. With demo = prod, `require_demo` waves the test suite straight
  through. Nothing can undo it afterwards; the triggers block `DELETE`.
- **`npm run dev` silently migrates prod.** The dev runner auto-applies pending
  migrations to `DATABASE_URL` on every start. Runbook § 1 exists to make
  production schema changes deliberate, human-triggered, and ahead of the code
  that needs them. That discipline evaporates when a developer starting the
  stack applies migrations to the pilot's database as a side effect.
- **`npm run seed` deletes the demo chapter.** Less bad than it sounds — the
  deletes in `scripts/seed.py` (lines 181–198) are all scoped to the fixed demo
  `CHAPTER_ID` and its member/event ids, so a pilot chapter with its own id is
  untouched. It is only a hazard if a pilot chapter ever reuses that id.

The lazy mitigation, in order of preference:

1. **Point local dev at a second Supabase project** and let the current demo ref
   become the pilot's. Free allows 2 active projects, so this costs $0. Then
   `db_guard` means something again — swap `DEMO_PROJECT_REF` to the new dev
   project's ref and the pilot database becomes `unknown`, which `require_demo`
   already refuses.
2. If you will not do that, **at minimum stop running `pytest` and `npm run dev`
   against that URL once a real chapter exists in it.** That is a discipline, not
   a guard, and disciplines fail — but it is honest to say so rather than pretend
   the checked-in guards still cover you.

### 0.2 `PROD_PROJECT_REFS` is moot for now — leave it empty

Do **not** paste the demo ref into `PROD_PROJECT_REFS`. Prod is checked before
demo in `classify_url`, so the demo project would classify as `prod` and
`require_demo` would start refusing it — breaking pytest, seed and migrate
outright. That is checklist item 3 of the original note inverted.

While one project serves both roles, `migrate:prod` and
`provision_chapter.py --prod` stay unusable — and you do not need them, because
`npm run migrate` and plain `provision_chapter.py` now reach the same database.
The `PROD_DATABASE_URL` secret and the migrate-prod workflow stay dormant until
prod becomes a separate project. Fill the ref then, not now.

### 0.3 No backups at all, and the project will pause

These are the two Free-plan facts that do not care how closed the pilot is:

- **Zero backups.** Free is excluded from daily backups and cannot download
  them. Supabase's own advice to Free users is to run `supabase db dump`
  yourself and keep off-site copies. With `big_ledger` and `audit_logs`
  append-only, a corruption event has no other out. **A manual dump before every
  risky migration, plus a scheduled one, stops being good practice and becomes
  the only backup that exists.** See § 1 — and note the runbook's dump command
  is pointed at the wrong port today, so it likely does not work.
- **The project pauses after ~1 week of inactivity**, and the app goes down until
  someone restores it from the dashboard. A pilot chapter in a quiet week between
  events can trigger this. Nothing notifies you.

Supabase Pro ($25/mo) removes both. If that is not happening yet, the two
compensating actions are a real dump habit and an uptime check (§ 0.4).

### 0.4 So why Sentry? Honest answer: mostly you don't, yet — but take the uptime monitor

Fair challenge. Splitting it:

**Error reporting: genuinely optional for a closed pilot.** You know all 2–5
officers and they will text you when something breaks. The one real argument is
retention — Vercel keeps runtime logs for **1 day on Pro**. An officer hits a 500
on Saturday, mentions it Tuesday, and the traceback is gone. `SENTRY_DSN` is one
environment variable against code that is already written and already shipping
in `requirements.txt`, and the free tier is $0, so the cost of taking it is about
five minutes. But "the code is already there" is not the same as "you need it",
and I would not upgrade any plan or write any frontend code for it now.

**Uptime monitoring: worth doing, and it is not really about Sentry.** This is
the part that earns its place *because* prod is on Supabase Free. The project
pauses after a week of inactivity, and `GET /api/health` is a real database ping
(`api/health_checks.py`), not a static 200 — so a monitor on it is the only thing
that will tell you the pilot's database went to sleep, or that the pooler ran out
of connections. Sentry's free plan includes one uptime monitor, which is why it
came up; UptimeRobot's free tier does the same job and the runbook § 7 already
suggests either. Pick whichever you will actually configure.

**Skip for now:** the frontend Sentry wiring (§ 3), source maps, and PITR. None
of them pay for themselves at pilot scale.

Note the outbox drain cron is currently low-stakes: `MESSAGE_DELIVERY_MODE` stays
`dry_run` until Twilio's 10DLC registration clears, so a missed run marks rows
`simulated` late and sends nothing. Revisit the cron monitor when the mode flips
to `twilio` — that is when a silently skipped run means a member never got told.

---

## 1. Supabase backups and point-in-time recovery

### What exists, what it costs

| Mechanism | Plan needed | Retention | Price |
|---|---|---|---|
| Daily backups | **Pro** | 7 days | included in $25/mo |
| Daily backups | Team | 14 days | included in $599/mo |
| Daily backups | Enterprise | up to 30 days | custom |
| **PITR** (add-on) | Pro+ **and ≥ Small compute** | 7 days | **$100/mo** per project |
| PITR | " | 14 days | $200/mo |
| PITR | " | 28 days | $400/mo |
| Self-serve `pg_dump` / `supabase db dump` | **any, including Free** | whatever you keep | $0 |
| Free plan | — | **none** | — |

Sources: [Database Backups](https://supabase.com/docs/guides/platform/backups),
[Pricing](https://supabase.com/pricing),
[Manage PITR usage](https://supabase.com/docs/guides/platform/manage-your-usage/point-in-time-recovery),
[Manage Compute usage](https://supabase.com/docs/guides/platform/manage-your-usage/compute)
— all fetched 2026-09-08.

Details that change the decision:

- **Free gets nothing.** "We automatically back up all Pro, Team, and Enterprise
  Plan projects on a daily basis" — Free is excluded, and the production
  checklist states "Database backups are not available for download for Free
  Plan projects." Supabase's own advice to Free users is to run
  `supabase db dump` yourself and keep off-site copies.
- **PITR forces a compute upgrade**: "Projects that want to use PITR must also
  use at least a Small compute add-on." Small is ~$15/mo; the $10/mo compute
  credit that comes with a paid plan is **per organization, not per project**.
- **PITR is billed hourly, per project, and is _not_ covered by the Spend Cap** —
  it can carry a Pro org past its cap. Partial hours bill as full hours.
- **PITR replaces daily backups**: "If you enable PITR, we will no longer take
  Daily Backups."
- PITR granularity is seconds, worst-case **RPO 2 minutes** (WAL archived every
  2 minutes).

Realistic monthly floor to have PITR on one project:
$25 (Pro) + $15 (Small) − $10 (org compute credit) + $100 (PITR 7d) ≈ **$130/mo**.
Against $25/mo for Pro with 7 days of daily backups. For a closed pilot of 2–5
chapters, the daily-backup RPO of up to 24 hours is a defensible trade; PITR
becomes worth arguing about when chapters are paying and a day of dues entry is
real money. Supabase's own trigger for "enable PITR" is a database expected to
exceed 4 GB ([going into prod](https://supabase.com/docs/guides/deployment/going-into-prod), 2026-09-08),
which this app is nowhere near.

### Restore mechanics, and the RTO nobody publishes

- In-place restore (daily or PITR) is **destructive and takes downtime**: "The
  project is inaccessible during this process, so plan for downtime beforehand"
  and "Downtime depends on the size of the database."
- **There is no published restore-duration figure.** The dedicated
  troubleshooting page says "the time required for a PIT restoration isn't
  fixed" and lists factors (time since the last weekly full backup, WAL volume,
  DB size) without any GB/min rate, target, or SLA
  ([source](https://supabase.com/docs/guides/troubleshooting/how-long-does-it-take-to-restore-a-database-from-a-point-in-time-backup-pitr-qO8gOG), 2026-09-08).
  So our RTO is unknown until we measure it. That is an argument for the drill
  in `ops-runbook.md` § 2, which has never been run.
- **Restore to a new project** (non-destructive) exists on paid plans with
  physical backups: source project → Database Backups → "Restore to a New
  Project". Dashboard only, no CLI/API path documented. It copies schema, data,
  roles, auth users and the encryption root key, stays in the same region, and
  bills as a second project
  ([clone-project](https://supabase.com/docs/guides/platform/clone-project), 2026-09-08).
  This is the better shape for our quarterly drill than spinning up a scratch
  project and `pg_restore`-ing into it.
- Who can trigger it: Owner, Administrator and Developer can restore; only Owner
  and Administrator can turn the PITR add-on on or off
  ([access control](https://supabase.com/docs/guides/platform/access-control), 2026-09-08).
- Management API, for scripting a backup-freshness check:
  `GET https://api.supabase.com/v1/projects/$PROJECT_REF/database/backups`
  returns `pitr_enabled`, `walg_enabled` and a `backups[]` array with
  `status`/`inserted_at`. (The API reference index lists several
  differently-spelled restore paths; trust the curl examples in the backups
  guide and verify before scripting.)

### The part that actually bites us: you cannot download Supabase's backups

> "You can still use physical backups for restoration, but **they are not
> available for direct download**."
> — [Database Backups](https://supabase.com/docs/guides/platform/backups), 2026-09-08

Physical (WAL-G) backups are now the default for all projects on Postgres
15.8.1.079+, and enabling PITR, adding a read replica, or growing past ~15 GB
all force physical backups. Once you are on physical backups Supabase **stops
generating the downloadable `backup.gz`** entirely
([download logical backups](https://supabase.com/docs/guides/troubleshooting/download-logical-backups), 2026-09-08).

And deletion is terminal: deleting a project "permanently remove[s] all
associated data, including any backups stored in S3. This action is
irreversible."

**Therefore:** the only copy of prod data that lives outside Supabase is one we
take ourselves. Given that `big_ledger` and `audit_logs` are append-only with
DELETE-blocking triggers (ADR-0002; `LocalDev/docs/ops-runbook.md` § 2), a
corruption event has exactly two outs — restore, or an independent dump. A
scheduled dump is not belt-and-braces here, it is the second out.

### The runbook's backup command is pointed at the wrong port

`LocalDev/docs/ops-runbook.md` § 2 says:

```bash
pg_dump -Fc --no-owner --no-privileges "$PROD_DATABASE_URL" -f "prod-$(date +%F).dump"
```

`PROD_DATABASE_URL` is a **transaction-mode pooler** URL (port 6543) — that is
the shape `LocalDev/docs/DATABASE.md` documents and what `db_guard`'s tests
assume. Supabase is explicit that this is the wrong connection for a dump:

- "Use the direct connection string for single sessions or Postgres native
  commands. For example, database GUIs, client applications like **pg_dump,
  migrations, backup-restore**…"
  ([connecting to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres), 2026-09-08)
- "**Use Supavisor session mode for the database migration tasks
  (pg_dump/restore and logical replication).**"
  ([migrating to Supabase](https://supabase.com/docs/guides/platform/migrating-to-supabase/postgres), 2026-09-08)
- Transaction mode "allow[s] a client to make a single query before being sent
  back to the figurative 'waiting room'" and does not support prepared
  statements — neither is compatible with the single consistent snapshot
  `pg_dump` holds open
  ([Supavisor FAQ](https://supabase.com/docs/guides/troubleshooting/supavisor-faq-YyP5tI), 2026-09-08).

The three connection strings, all from
[connecting to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres) (2026-09-08):

| Use | String | Port | IP |
|---|---|---|---|
| The app (serverless) | `postgres://postgres.<ref>:PWD@aws-N-<region>.pooler.supabase.com:6543/postgres` | 6543 | IPv4 |
| **Dumps, migrations** | `postgres://postgres.<ref>:PWD@aws-N-<region>.pooler.supabase.com:5432/postgres` | **5432** | IPv4 |
| Direct | `postgresql://postgres:PWD@db.<ref>.supabase.co:5432/postgres` | 5432 | **IPv6** unless you buy the $4/mo IPv4 add-on |

Copy the exact pooler host from the dashboard's Connect dialog — Supabase issues
numbered prefixes per fleet (`aws-0-`, `aws-1-`, …) and the docs render it both
ways.

Two follow-ons for us:

1. The backup recipe needs a **session-mode** URL, which is a *different secret*
   from `PROD_DATABASE_URL`. Either add a `PROD_SESSION_DATABASE_URL`, or note
   in the runbook that the operator swaps `:6543` for `:5432` before dumping.
   Note `db_guard.classify_url` still classifies it as prod either way — it
   matches on the ref, which is in the username of both.
2. The direct `db.<ref>.supabase.co` host is IPv6-only by default. A GitHub
   Actions runner is IPv4-only, so an automated dump must go through the
   session pooler, not the direct host.

Supabase's canonical dump is three passes, not one
([backup-restore](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore), 2026-09-08):

```bash
supabase db dump --db-url "$SESSION_URL" -f roles.sql  --role-only
supabase db dump --db-url "$SESSION_URL" -f schema.sql
supabase db dump --db-url "$SESSION_URL" -f data.sql --use-copy --data-only
```

Plain `pg_dump -Fc` (what the runbook uses) is fine for our purposes and simpler
— we have no custom roles and no Storage objects. Keep `--no-owner
--no-privileges`; Supabase applies those "to prevent Supabase user management
conflicts."

### Encryption and residency

"All customer data is encrypted at rest with AES-256 and in transit via TLS"
([security](https://supabase.com/security), 2026-09-08). There is no sentence
naming *backup files* specifically; the at-rest claim reasonably covers them but
is not stated in those words. Our own dumps are unencrypted `.dump` files — if
they go anywhere but a local disk, encrypt them. They contain every member's
bcrypt hash, phone number and dues history.

---

## 2. The production project ref, and filling `PROD_PROJECT_REFS` safely

This section is entirely code-derived, so it is the firmest part of the note.

### Where a Supabase project ref is found

A project ref is a 20-character lowercase identifier. The same string appears in
five places, so no special access is needed to read it:

| Where | Shape |
|---|---|
| Dashboard → Project Settings → General | field labelled **Reference ID** |
| The dashboard URL | `https://supabase.com/dashboard/project/<ref>` |
| Connect → connection pooling URL | username is `postgres.<ref>` |
| Direct connection host | `db.<ref>.supabase.co` |
| Project API URL | `https://<ref>.supabase.co` |

**Whoever already holds `PROD_DATABASE_URL` already holds the prod ref** — it is
the text between `postgres.` and the first `:`. No dashboard visit is strictly
required; the dashboard is just the least error-prone source.

The ref is **not in this repository anywhere**. `git grep` over pooler hosts and
20-char refs returns only the demo ref, placeholders, and test fixtures. The
only checked-in ref is `DEMO_PROJECT_REF = "kikzdpfpprfkkbmcwnhm"` in
`LocalDev/scripts/db_guard.py`.

> Stale doc, worth fixing while you are in there: `LocalDev/docs/DATABASE.md`
> § "Connect to prod" claims the deployed app reads `POSTGRES_URL_NON_POOLING`,
> injected by a Vercel↔Supabase integration. `api/config.py` declares no such
> setting and `grep` finds zero readers of that name in the tree — the app reads
> `DATABASE_URL` only. If that integration *is* still installed on the Vercel
> project, its injected `SUPABASE_URL` / `POSTGRES_*` variables are another
> place to read the prod ref, and they are dead weight someone will one day
> mistake for live config.

### How the value is consumed — read the code before pasting

`LocalDev/scripts/db_guard.py` is a pure-string module: no I/O, no psycopg2, no
`.env` reading. Three consumers:

- `classify_url(url)` → `"local" | "demo" | "prod" | "unknown"`. It checks prod
  **first and by substring**: `any(ref in url for ref in PROD_PROJECT_REFS)`.
  Most-dangerous-first is deliberate — a URL containing a prod ref is prod
  regardless of anything else about it (there is a test,
  `test_classify_prod_wins_over_local_hostname`).
- `require_demo(url, context=…)` — used by pytest (`tests/treasury/conftest.py`),
  `scripts/seed.py`, and the ordinary `scripts/migrate_db.py` path. Allows demo
  and localhost; refuses `prod` **and** `unknown`. Fail-closed.
- `require_prod(url)` — used only by `migrate_db.py --prod` and
  `provision_chapter.py --prod`. Refuses outright while `PROD_PROJECT_REFS` is
  empty, then refuses anything that does not classify as prod.

`confirmation_matches(typed, url)` additionally makes an interactive operator
type the ref of the *actual* URL. The GitHub workflow passes `--yes` and skips
that prompt (no TTY in CI), so **in CI `PROD_PROJECT_REFS` is the only ref check
that runs**.

Four consequences worth knowing before editing the line:

1. **It is a `frozenset`, plural on purpose.** During a project cutover you can
   list old and new refs together and both classify as prod. Nothing assumes
   exactly one.
2. **Substring matching means the ref must be complete.** Paste all 20
   characters; a truncated ref would still match and silently keep working while
   widening the match.
3. **The dangerous mistake is pasting the _demo_ ref.** Because prod is checked
   first, the demo project would then classify as `prod` and `require_demo`
   would start refusing the demo database — breaking pytest, `npm run seed` and
   `npm run migrate` immediately. Loud, not silent. That is the canary.
4. **This guard protects scripts, not the running app.** `api/config.py` and the
   boot guard in `api/index.py` check that `DATABASE_URL` is *set*, never which
   project it points at. A production Vercel deploy whose `DATABASE_URL` was
   pasted from the demo project would boot happily and serve demo data to real
   chapters. `db_guard` cannot catch that — only a human comparing the Vercel
   value against the prod ref can.

### The safe procedure

```bash
# 1. Read the ref off the prod pooler URL you already have, without printing
#    the password.
python3 -c "import sys,urllib.parse as u; print(u.urlsplit(sys.argv[1]).username)" "$PROD_DATABASE_URL"
# -> postgres.<the-ref>

# 2. Edit LocalDev/scripts/db_guard.py, replacing the empty frozenset with:
#    PROD_PROJECT_REFS: frozenset[str] = frozenset({"<the-ref>"})
#    ...and delete the HUMAN ACTION REQUIRED banner above it.

# 3. Verify you did NOT paste the demo ref.
cd LocalDev && python3 -m pytest tests/test_db_guard.py -q
python3 -m pytest -q     # the real canary: the demo path must still work
```

**Filling the ref does not break the test suite.** Verified 2026-09-08 by
patching `PROD_PROJECT_REFS` to a dummy 20-char ref and running
`tests/test_db_guard.py`: **21 passed**. The two tests that look plan-dependent
are safe by construction — `test_classify_prod_empty_refs_means_never_prod` uses
a *fake* ref (`prodref0123456789ab`) that will not be in the real set, and
`test_require_prod_refuses_when_refs_unfilled` only asserts that the substring
`PROD_PROJECT_REFS` appears in the error, which is true of both branches of
`require_prod`. Nobody has to touch the tests.

### The other half of the same task

Filling the ref alone does not make `migrate:prod` work. The repository secret
`PROD_DATABASE_URL` must also be set (GitHub → Settings → Secrets and variables
→ Actions), because `.github/workflows/migrate-prod.yml` passes it as the only
database env var. Until both are done the workflow fails fast and harmlessly.

That workflow also carries a commented-out `environment: production` key.
Uncommenting it and adding a required reviewer is the cheapest way to stop one
compromised or careless account from migrating prod alone. Worth doing at the
same time — it costs one line.

> Small doc bug spotted while reading: `ops-runbook.md` § 1 offers "Sanity check
> without applying anything: `python3 scripts/check_prod_status.py`". That script
> never looks at migrations — it is an HTTP poller against `GET /api/health` on
> `https://guild-os-two.vercel.app`. Useful, but not a migration dry-run, and
> `migrate_db.py` has no dry-run flag.

---

## 3. What Sentry needs to be live

### Backend (FastAPI on Vercel) — nearly done

`LocalDev/api/observability.py` already calls `sentry_sdk.init(...)` when
`SENTRY_DSN` is set, and `sentry-sdk[fastapi]==2.66.1` is pinned in
`requirements.txt`. `FastApiIntegration` and `StarletteIntegration` **auto-enable**
from the presence of the `fastapi` package — no explicit `integrations=[...]`
needed
([FastAPI integration](https://docs.sentry.io/platforms/python/integrations/fastapi/), 2026-09-08).

So the backend is **one environment variable away from working**: set
`SENTRY_DSN` in the Vercel project (Production scope) and redeploy. Current
latest SDK is 2.69.0 (2026-09-08); 2.66.1 is fine, no upgrade needed.

Two things I would change while setting the DSN:

1. **Add a per-request flush.** The Python SDK sends events from a background
   worker thread and drains automatically only via `AtexitIntegration` on
   process shutdown
   ([draining](https://docs.sentry.io/platforms/python/guides/serverless/configuration/draining/), 2026-09-08).
   Vercel freezes a function process between invocations rather than exiting it,
   so atexit does not fire on a useful timeline. **Sentry publishes nothing at
   all about Python on Vercel** — its Vercel integration page is entirely about
   Next.js, and a code search for "vercel" across `getsentry/sentry-python`
   returns zero hits. The `@serverless_function` decorator does not help: it
   wraps a plain callable with no ASGI awareness
   ([source](https://github.com/getsentry/sentry-python/blob/master/sentry_sdk/integrations/serverless.py), 2026-09-08).

   The lazy fix is one `await sentry_sdk.flush_async()` in the existing
   `unhandled_exception_handler` in `api/observability.py` — the only place we
   care about losing an event. `flush_async` exists in `sentry_sdk/api.py`; use
   it rather than the blocking `sentry_sdk.flush()` inside async code. Note
   `shutdown_timeout` defaults to 2s, so a flush can add up to two seconds to an
   already-failing request. This is inference from documented SDK internals, not
   a Sentry recommendation — flagged as such.

2. **Set `release`.** The SDK's fallback chain reads `SENTRY_RELEASE`, then a git
   SHA, then a fixed list of CI variables that **does not include Vercel's**
   ([releases](https://docs.sentry.io/platforms/python/configuration/releases/), 2026-09-08),
   and a Vercel build has no `.git` directory. Without it every error is
   attributed to "no release" and you cannot tell which deploy broke.
   `release=f"guildos-api@{os.environ.get('VERCEL_GIT_COMMIT_SHA','dev')}"`.

`environment=settings.VERCEL_ENV or "local"` and `traces_sample_rate=0` are both
right as they stand — tracing is a separate cost decision and errors are what we
need.

### Frontend (greekos, Vite + React) — nothing exists yet

`LocalDev/greekos` has **no Sentry package, no DSN, and no env var usage at all**
(`grep` for `import.meta.env` in `greekos/src` returns only the Vite config's
`DISABLE_HMR`). Wiring it up is a real, if small, task:

1. `npm i @sentry/react` — current stable is **10.73.0** (2026-08-31). v11 is in
   beta (`11.0.0-beta.1`, 2026-09-03) with a migration guide marked "work in
   progress"; **do not ship v11 yet**
   ([releases](https://github.com/getsentry/sentry-javascript/releases), 2026-09-08).
2. Put `Sentry.init` in its own `instrument.ts` and import it as the **first
   line** of `src/index.tsx`. The docs require it "imported before any other
   imports in your application entry point"; Vite hoists ESM imports, so an
   inline init placed after the React imports genuinely misses module-evaluation
   errors
   ([React guide](https://docs.sentry.io/platforms/javascript/guides/react/), 2026-09-08).
3. Read the DSN from `import.meta.env.VITE_SENTRY_DSN`. Vite only exposes
   `VITE_*` to client code. **The DSN is safe to ship in the bundle**: "DSNs are
   safe to keep public because they only allow submission of new events… they do
   not allow read access to any information"
   ([DSN explainer](https://docs.sentry.io/concepts/key-terms/dsn-explainer/), 2026-09-08).
4. greekos has no router library, so plain `Sentry.browserTracingIntegration()`
   is right; skip the react-router integrations. Add a `<Sentry.ErrorBoundary>`
   — React render errors do not reach the global handler otherwise. (React 19 is
   in use, so `reactErrorHandler()` passed into `createRoot` options is the
   lighter alternative.)
5. **Set `enableLogs: false`.** It defaults to **`true`** in the JS SDK, quietly
   opting you into log ingestion against a 5 GB quota
   ([options](https://docs.sentry.io/platforms/javascript/configuration/options/), 2026-09-08).

Source maps, if you want readable stack traces (optional for a pilot — skip it
until an unreadable trace actually costs you an hour):

- `npm i -D @sentry/vite-plugin` (**5.4.0**, 2026-07-10), set
  `build.sourcemap: "hidden"`, and put the plugin **after all other plugins**.
  Use `sourcemaps.filesToDeleteAfterUpload` so the `.map` files do not ship —
  Vercel serves `dist/` verbatim
  ([Vite source maps](https://docs.sentry.io/platforms/javascript/guides/react/sourcemaps/uploading/vite/), 2026-09-08).
- Needs `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT` **at build time** in
  Vercel. An Organization Token is the recommended kind. Nothing in the docs
  gates source map upload behind a paid plan (stated as *no documented
  restriction*, not as confirmed-free).
- The plugin repo is being folded into `getsentry/sentry-javascript` and bumped
  to 11.0.0 with the next SDK major; package name is unchanged.

### The Sentry Vercel integration: probably not worth it here

It exists and is not deprecated, but it injects `NEXT_PUBLIC_SENTRY_DSN` (Vite
does not read `NEXT_PUBLIC_*`), its source-map handling is framed entirely around
Next.js, and it does nothing at all for the Python function. Also: "There is no
path for existing Sentry organizations to use the Vercel Marketplace
integration"
([Vercel integration](https://docs.sentry.io/organization/integrations/deployment/vercel/), 2026-09-08).
Setting four env vars by hand is less work than adopting it.

### Free tier limits — and the one that will pinch

[sentry.io/pricing](https://sentry.io/pricing/) and
[docs.sentry.io/pricing](https://docs.sentry.io/pricing/), fetched 2026-09-08
(annually-billed prices):

| | Developer (free) | Team |
|---|---|---|
| Price | **$0** | **$26/mo** |
| **Users / seats** | **1 user** | unlimited |
| Errors | **5,000/mo** | 50,000/mo |
| Spans (tracing) | 5M/mo | 5M/mo |
| Session replays | 50/mo | 50/mo |
| **Cron monitors** | **1** | 1 (+$0.78 each) |
| **Uptime monitors** | **1** | 1 (+$1.00 each) |
| **Error retention** | **30 days** | 90 days |

The step to Team is almost entirely the error quota and seats — spans, replays,
crons and uptime monitors are identical at the base tier. Over-quota events "will
not be accepted", i.e. dropped, not queued
([quotas](https://docs.sentry.io/pricing/quotas/), 2026-09-08).

For a 2–5 chapter pilot, 5,000 errors/month is generous and 30-day retention is
adequate. **The real constraint is "1 user"** — only one person can be in the
Sentry org and receive alerts. If the pilot has a second person on call, that is
$26/mo, not a technical problem.

Two free things to grab while you are in there: the **1 free uptime monitor**
covers `GET /api/health`, which `ops-runbook.md` § 7 currently sends you to a
third-party service for; and the **1 free cron monitor** covers the outbox drain
(see § 4).

### Two gotchas before you create the org

- **The data region is chosen at org creation and is irreversible.** US (Iowa,
  `us.sentry.io`) or EU (Frankfurt, `de.sentry.io`). "Once selected, your data
  storage location can't be changed. The only way to switch it is by creating a
  new organization"
  ([data storage location](https://docs.sentry.io/organization/data-storage-location/), 2026-09-08).
  US chapters, US region.
- **Two categories of data are sent regardless of `send_default_pii`**, and both
  matter for us
  ([data collected](https://docs.sentry.io/platforms/python/data-management/data-collected/), 2026-09-08):
  1. **The full request URL including query string** is "always sent to Sentry".
     Check-in links (`/c/<code>`) put a live token in the path — those will land
     in Sentry. They are short-lived (`CHECKIN_LINK_TTL_MINUTES`, default 10),
     so the exposure is bounded, but know that it happens.
  2. **Local variables in stack frames** are captured by default
     (`include_local_variables=True`). A frame holding a decoded JWT, a bcrypt
     hash or a setup code ships its contents. Server-side scrubbing catches
     fields *named* `password`, `token`, `secret`, `auth`, etc., but a variable
     named `code` or `hashed` is not on that denylist.

  We leave `send_default_pii` unset (falsy), which is right. If you want belt and
  braces, `include_local_variables=False` in the existing `init` call is one
  keyword and costs you some debuggability.

---

## 4. What else this deployment needs before real users

### Vercel Hobby cannot legally or technically run this

Two independent blockers, both from primary docs fetched 2026-09-08:

1. **Commercial use is prohibited on Hobby.** "Hobby teams are restricted to
   non-commercial personal use only. All commercial usage of the platform
   requires either a Pro or Enterprise plan," where commercial usage includes
   "receiving payment to create, update, or host the site"
   ([fair use](https://vercel.com/docs/limits/fair-use-guidelines#commercial-usage)).
2. **`vercel.json` schedules a cron Hobby will not accept.** The project root
   `vercel.json` declares `"/api/cron/drain-outbox"` at `*/5 * * * *`, but
   "Hobby accounts are limited to daily cron jobs" and a sub-daily expression
   **fails at deploy time**. Hobby also fires with per-hour precision (±59 min)
   ([cron pricing](https://vercel.com/docs/cron-jobs/usage-and-pricing)).

If the project is already on Pro this is a non-issue; if it is not, the outbox
drain is not running today and SMS is silently queued forever. **Check which plan
the `guild-os` project is on** — this is a five-second dashboard look with a
large blast radius. Pro is **$20/mo** with a $20 included credit
([pricing](https://vercel.com/pricing)).

### Cron delivery is best-effort — the code already handles it, nothing watches it

Vercel is unusually blunt here
([manage cron jobs](https://vercel.com/docs/cron-jobs/manage-cron-jobs), 2026-09-08):
"Cron job delivery is best effort" — a transient error can mean the run **never
happens and no log is written**; it can also **invoke the same scheduled run more
than once**; and "**Vercel will not retry an invocation if a cron job fails.**"

The good news is that `api/cron/services/outbox_drain.py` is already built for
this. `outbox_claim_batch` (migration 0155) flips rows to `sending` in the same
statement that selects them, under `FOR UPDATE SKIP LOCKED`, requeues rows whose
worker died more than 15 minutes ago, and fails rows past 5 attempts. Duplicate
invocations cannot double-send; a killed invocation self-heals on the next run.
That is exactly the idempotent, reconciliation-shaped design Vercel's docs ask
for, and it needs no change.

What is missing is anyone noticing when it stops:

- **A missed run is invisible.** Vercel runtime log retention is **1 hour on
  Hobby, 1 day on Pro** ([Hobby plan](https://vercel.com/docs/plans/hobby),
  2026-09-08) — an overnight failure leaves nothing to read. Sentry's free cron
  monitor solves this: it alerts on a *missing* check-in, which is the failure
  mode logs cannot show you.
- **`failed` outbox rows are terminal and unwatched.** The module's own docstring
  says a failed row "is a signal for an operator, not something the worker keeps
  hammering" — but no operator is signalled. A member who never got their dues
  reminder produces a row nobody reads. Cheapest fix: have `drain_outbox` log a
  warning (which Sentry picks up) when the batch's `failed` count is non-zero.

`CRON_SECRET` handling is already correct and matches Vercel's documented
contract (`Authorization: Bearer $CRON_SECRET`), with a constant-time compare and
fail-closed-on-empty in `api/cron/auth.py`. The boot guard requires ≥16 chars.
Nothing to do.

### Connection pooling: one thing right, one thing to watch

`api/platform/postgres.py` opens a `ThreadedConnectionPool(1, 10, dsn)` — a
client-side pool of up to 10 connections, per process, in front of Supavisor in
transaction mode.

**The good news, and it is the part that would have hurt:** psycopg2 does not use
server-side prepared statements by default. Transaction mode's one documented
incompatibility is prepared statements — "Transaction mode does not support
prepared statements. To avoid errors, turn off prepared statements for your
connection library"
([connecting to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres), 2026-09-08).
We are already compliant by accident of driver choice. Nothing to change.

The thing to watch is pool multiplication. Supabase's guidance for serverless is
the opposite of a client-side pool: their SQLAlchemy page says "when using
transaction mode, you should use the `NullPool` setting", and the Supavisor FAQ
says that for edge/serverless functions an app-side pool size of "one is optimal"
since each invocation services a single request
([SQLAlchemy guide](https://supabase.com/docs/guides/troubleshooting/using-sqlalchemy-with-supabase-FUqebT),
[Supavisor FAQ](https://supabase.com/docs/guides/troubleshooting/supavisor-faq-YyP5tI), 2026-09-08).

The ceilings we would hit, on the Free/Micro compute a Supabase project starts
at ([compute and disk](https://supabase.com/docs/guides/platform/compute-and-disk), 2026-09-08):

| Compute | Direct connections | Pooler client connections |
|---|---|---|
| Nano (Free) / Micro | 60 | **200** |
| Small | 90 | 400 |
| Medium | 120 | 600 |

Plus Vercel's own **1,024 file descriptors shared across all concurrent
executions on an instance** — which counts sockets, and whose documented remedy
is "close database connections when no longer needed; use connection pooling"
([function limits](https://vercel.com/docs/functions/limitations), page dated
2026-08-24, fetched 2026-09-08).

Mitigating this: **Fluid compute is the default since 2025-04-23** and shares one
instance across many invocations for Node.js *and* Python
([Fluid compute](https://vercel.com/docs/fluid-compute), 2026-09-08), so the
process-wide singleton in `api/platform/db.py` is reused rather than
re-instantiated per request, and 10 connections is per *instance*, not per
request. At pilot scale (2–5 chapters) 200 pooler slots is not close. **No change
needed now** — but if `/api/health` starts reporting `database: error` under
load, `maxconn` in `PostgresClient.__init__` is the first dial to turn down, not
the compute tier to turn up.

One free latency win from Vercel's own production checklist: "ensure your Vercel
Function region is the same as your origin API or database"
([production checklist](https://vercel.com/docs/production-checklist), 2026-09-08).
Vercel defaults to `iad1` (us-east-1). If the prod Supabase project is in
us-west-2 like the demo one appears to be, every query pays a cross-country round
trip, on every request. Check and match.

### Supabase Free will pause the pilot out from under you

"Free projects are paused after 1 week of inactivity"
([pricing](https://supabase.com/pricing), 2026-09-08; the pausing doc phrases it
as insufficient activity over a 7-day period). A pilot with five chapters in a
quiet week between events can genuinely go down. Combined with no backups, a
500 MB database cap and 10 GB total egress, **Supabase Pro at $25/mo is the floor
for real users** — it removes all four, and includes 7-day backups and $10/mo of
compute credit (enough for one Micro instance).

Free plan projects are also limited to 2 active projects, which matters because
demo and prod are two.

### Env var scoping is already right, but confirm the preview target

Preview deployments do **not** receive Production-scoped variables — Vercel
states it flatly, and a variable change "only appl[ies] to new deployments", so a
redeploy is needed after any edit
([env vars](https://vercel.com/docs/environment-variables), 2026-09-08). That
matches the map's decision that multi-device testing happens on a preview
deployment against the demo DB: set Preview-scoped `DATABASE_URL` to the demo
pooler and Production-scoped `DATABASE_URL` to prod, and they cannot cross.

Two things to remember about preview:

- `settings.is_deployed` includes `preview`, so **the boot guard applies to
  preview too** (`api/index.py`). A preview deploy needs its own `JWT_SECRET`
  (≥32 chars, not the dev default), `CRON_SECRET` (≥16), and a non-localhost
  `FRONTEND_URL`, or it will refuse to boot. This is deliberate — preview URLs
  are public — but it will look like a mystery build failure the first time.
- `vercel env add` now defaults to **`sensitive`** for production and preview
  targets. Sensitive values cannot be read back afterwards, from the dashboard or
  `vercel env ls`
  ([sensitive env vars](https://vercel.com/docs/environment-variables/sensitive-environment-variables), 2026-09-08).
  Good for `JWT_SECRET` and `DATABASE_URL`; make sure the value is recorded in a
  password manager first, because you cannot retrieve it later.

Also worth enabling from Vercel's checklist: **Deployment Protection on previews**
(a public preview URL against the demo DB is a live app anyone can find) and
**Spend Management** with an alert threshold, since Pro bills overages.

### Two loose ends found while reading

- **`vercel.json` still builds `fratos`, not `greekos`.** The `builds` block
  names `fratos/package.json` with `@vercel/next`, and the catch-all route sends
  `/(.*)` to `/fratos/$1`. Per map #41 the destination is greekos as the product
  UI, and greekos is a Vite SPA that is not in `vercel.json` at all — it only has
  a dev-server proxy for `/api`. Shipping greekos to prod is a `vercel.json`
  change (build `greekos`, serve `dist/`, keep `/api` and `/c` routed to
  `api/index.py`) that nobody has written yet. Out of scope for this ticket, but
  it is on the critical path to the same destination.
- **`login_attempts` grows forever.** Migration 0148 adds the table and its two
  indices; `_enforce_rate_limit` in `api/auth/api/auth.py` reads it with a time
  cutoff, but nothing ever deletes old rows. At pilot scale this is years away
  from mattering — noting it so it is a known deferral rather than a surprise.

---

## Checklist of human actions

Revised for the actual plan: Vercel **Pro** (settled), Supabase **Free demo
project doubling as prod**, Twilio later. Items 1–3 are the ones that matter;
4–5 are five-minute wins; 6–8 are deliberate deferrals.

1. **Split dev off the pilot database.** Create a second Free Supabase project
   for local dev and point `LocalDev/.env` at it, then move `DEMO_PROJECT_REF`
   in `scripts/db_guard.py` to the new ref. $0 (Free allows 2 projects), and it
   restores the guard that stops `pytest` writing permanent garbage into
   `big_ledger`/`audit_logs` and `npm run dev` auto-migrating the pilot's schema.
   If you skip this, the compensating rule is: **stop running `pytest` and
   `npm run dev` against that URL once a real chapter exists in it.**
2. **Start actually taking dumps.** On Free there is no other backup, and the
   append-only ledger cannot be repaired any other way. First fix the command in
   `ops-runbook.md` § 2 — it uses the transaction-mode pooler (6543), through
   which `pg_dump` does not work; it needs the **session** pooler, port **5432**.
   Then run one dump and one restore, and fill in the `_TBD_` lines there.
3. **Decide about the Supabase Free pause.** The project sleeps after ~1 week of
   inactivity and the app goes down until someone wakes it from the dashboard.
   Either accept it and put a monitor on `GET /api/health` so you find out
   (UptimeRobot free, or Sentry's free uptime monitor — the runbook already
   suggests both), or upgrade to Pro at $25/mo, which also buys 7-day backups.
4. **Leave `PROD_PROJECT_REFS` empty.** While one project serves both roles,
   pasting the demo ref in would make `require_demo` refuse the demo database and
   break dev outright. `migrate:prod`, `provision_chapter.py --prod` and the
   `PROD_DATABASE_URL` secret stay dormant; `npm run migrate` reaches the same
   database anyway. Fill the ref (and see § 2 for how) when prod becomes its own
   project.
5. **Check the Vercel function region matches the Supabase project region.**
   Vercel defaults to `iad1`; a mismatch taxes every single query, for free.
6. **Optional, ~5 minutes: set `SENTRY_DSN` in Vercel Production.** The backend
   code is already written and `sentry-sdk` already ships. It buys 30-day error
   retention against Vercel's 1-day log window. Not required for a closed pilot
   where officers will text you — take it or leave it. If you take it, pick the
   **US** data region (irreversible) and add `release` from
   `VERCEL_GIT_COMMIT_SHA`.
7. **Deferred: PITR, and the greekos frontend Sentry + source maps.** PITR is
   ~$105/mo on top of Pro and forces a compute upgrade; revisit at 4 GB or when
   chapters pay. Frontend Sentry waits for the greekos deploy, which itself needs
   a `vercel.json` change — it currently builds `fratos`.
8. **Deferred until Twilio goes live: the cron monitor.** `MESSAGE_DELIVERY_MODE`
   is `dry_run` until 10DLC clears, so a skipped cron run costs nothing today.
   When the mode flips to `twilio`, a silently missed run means a member never
   got told — that is when the monitor earns its place, along with an alert on
   non-zero `failed` counts from `drain_outbox`.

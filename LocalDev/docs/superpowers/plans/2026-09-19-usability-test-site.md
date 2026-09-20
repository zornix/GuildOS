# Usability Test Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Load `ponytail:ponytail` first, then `superpowers:verification-before-completion`.

**Goal:** A public link where usability testers use today's `LocalDev` code against the demo database, with zero path to the prod database or the live site.

**Architecture:** A second Vercel project, `guildos-usability`, deployed from `LocalDev/` with the CLI (no Git connection). Only its **Preview** environment gets settings, and the only database it knows is the demo pooler URL. A fixed alias gives testers one stable link; Vercel's login wall is turned off for this project only. Almost no code changes — this is Vercel setup plus one runbook section.

**Tech Stack:** Vercel CLI 54 (`vercel project`, `env`, `deploy`, `alias`, `api`), existing `LocalDev/vercel.json` (FastAPI via `@vercel/python` + greekos via `@vercel/static-build`), `psql` against the Supabase demo pooler.

**Spec:** none — this was a bounded brainstorm (2026-09-19). The decisions table below is the spec.

## Why not the existing `fraternity-os` project

Found 2026-09-19, all verified:

- Its Root Directory is `Prod/fratos` with the **Next.js** preset, but `Prod/fratos` is now Vite. Every deploy since ~2026-09-07 fails with `No Next.js version detected`. The live URL still serves an older build.
- It has none of the settings the backend needs (`DATABASE_URL`, `JWT_SECRET`, `CRON_SECRET`, `FRONTEND_URL`, `BASE_URL`) — only leftovers from the Supabase integration.
- `Prod/` is stale: no `api/chapters`, `api/contribution`, `api/sms_consent.py`; 3 migrations vs 64; 54 frontend files differ.
- Fixing it in place means the next push to `main` replaces the live site with a build that has no prod settings. The owner says the prod DB holds real user data, so the live site is left alone.

## Decisions

| # | Decision | Why |
|---|----------|-----|
| D1 | New Vercel project `guildos-usability`, deployed from `LocalDev/` by CLI, not connected to Git | Tests current code, nothing copied to `Prod/`, no surprise deploys from Dependabot branches, live site untouched |
| D2 | Settings go in the **Preview** scope only; Production scope stays empty | An accidental `vercel --prod` boots into the config guard and refuses to serve |
| D3 | Public link: Vercel Authentication off for this project only | Testers use their own phones; the app's own login still guards data |
| D4 | No `TWILIO_*` or `SMTP_*` settings, ever, on this project | `api/config.py` defaults both delivery modes to `dry_run`; with no credentials nothing can leave the building |
| D5 | Testers use the seeded **Delta Mu** chapter (`00000000-0000-0000-0000-000000000001`) | Already has realistic events, dues, members. It is tenant-isolated from the `tr-test-*` junk chapters |
| D6 | No reset between testers | `npm run seed` cannot cleanly reset a used chapter: ~40 tables point at `members` with no cascade and `audit_logs` is append-only. Leftover data from earlier testers is acceptable for usability work |
| D7 | New-member flow runs without email | `POST /api/auth/invite` returns the setup code to the officer on screen; the facilitator reads it out. The UI copy "We emailed the setup code" is untrue in dry-run — tell testers |
| D8 | Member test logins are set with a one-off SQL update, not a code change | `scripts/set_officer_password.py` is officer-only by design; two rows do not justify changing it |
| D9 | Scheduled jobs do not run on previews; drain the outbox by hand when needed | Vercel only runs crons on production deployments. One `curl` makes "pending" rows flip to "simulated" |

## Global Constraints

- Never set `DATABASE_URL` on this project to anything but the demo pooler URL from `LocalDev/.env`. Never add `PROD_DATABASE_URL`.
- Never add `TWILIO_*`, `SMTP_*`, `MESSAGE_DELIVERY_MODE`, or `EMAIL_DELIVERY_MODE` to this project (D4).
- Never run `vercel --prod` / `vercel deploy --prod` from `LocalDev/`.
- Do not touch the `fraternity-os` Vercel project or anything under `Prod/`.
- Do not run `npm run seed` while the test site is in use (D6).
- Never print secret values to the terminal or commit them. Secrets for this site live in `LocalDev/.env.usability` (ignored by `LocalDev/.gitignore:140`).
- Do not add a `.vercelignore`. With none present the CLI honors `LocalDev/.gitignore`, which already excludes `.env` and `.env.*`. Adding one would switch that off.
- Git: branch `chore/usability-test-site`, one commit per logical change, merge to `main` with `--no-ff`, then delete the branch. **No `Co-Authored-By` or "Generated with" trailers.**
- All commands run from `/home/mshi/GuildOS/LocalDev` unless stated.

## Files

- Create (untracked, gitignored): `LocalDev/.env.usability` — site URL + the two generated secrets.
- Create (untracked, gitignored): `LocalDev/.vercel/` — written by `vercel link`.
- Modify: `LocalDev/docs/ops-runbook.md` — new section `## 9. Usability test site` at the end.

---

### Task 1: Create the project and its Preview settings

**Files:**
- Create: `LocalDev/.env.usability`
- Create: `LocalDev/.vercel/project.json` (by the CLI)

**Interfaces:**
- Produces: Vercel project `guildos-usability` linked to `LocalDev/`; `LocalDev/.env.usability` with `USABILITY_SITE`, `USABILITY_JWT_SECRET`, `USABILITY_CRON_SECRET`, `USABILITY_MEMBER_PASSWORD`. Later tasks read the site, cron secret and member password from it. If the file already exists, keep it — do not regenerate.

- [ ] **Step 1: Confirm the CLI is logged in to the right team**

Run: `vercel whoami && vercel teams ls`
Expected: user `zornix-4149`, current team `zornix-4149s-projects`.

- [ ] **Step 2: Create and link the project**

```bash
vercel project add guildos-usability
vercel link --yes --project guildos-usability
cat .vercel/project.json
git check-ignore -q .vercel && echo ".vercel ignored"
```

Expected: `project.json` shows `"projectName":"guildos-usability"` (NOT `fraternity-os`), and `.vercel ignored`.

- [ ] **Step 3: Write the local secrets file**

```bash
umask 077
cat > .env.usability <<EOF
USABILITY_SITE=https://guildos-usability-test.vercel.app
USABILITY_JWT_SECRET=$(openssl rand -hex 32)
USABILITY_CRON_SECRET=$(openssl rand -hex 16)
USABILITY_MEMBER_PASSWORD=member-$(openssl rand -hex 4)
EOF
git check-ignore -q .env.usability && echo "secrets file ignored"
```

Expected: `secrets file ignored`. (64-char JWT secret and 32-char cron secret clear the boot guard's 32 / 16 minimums in `api/index.py`.)

- [ ] **Step 4: Add the five Preview settings**

```bash
get() { grep -E "^$1=" "$2" | tail -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
printf %s "$(get DATABASE_URL .env)"                   | vercel env add DATABASE_URL preview --yes
printf %s "$(get USABILITY_JWT_SECRET .env.usability)"  | vercel env add JWT_SECRET   preview --yes
printf %s "$(get USABILITY_CRON_SECRET .env.usability)" | vercel env add CRON_SECRET  preview --yes
printf %s "$(get USABILITY_SITE .env.usability)"        | vercel env add FRONTEND_URL preview --yes
printf %s "$(get USABILITY_SITE .env.usability)"        | vercel env add BASE_URL     preview --yes
```

If the CLI still asks "which Git branch", press Enter (all branches).

- [ ] **Step 5: Verify scope — Preview only, five names, nothing else**

Run: `vercel env ls`
Expected: exactly `DATABASE_URL`, `JWT_SECRET`, `CRON_SECRET`, `FRONTEND_URL`, `BASE_URL`, each listed for `Preview` only. No `Production` anywhere. No `TWILIO_*` / `SMTP_*`.

No commit — nothing tracked changed.

---

### Task 2: Deploy, pin the link, open it to testers

**Interfaces:**
- Consumes: linked project and `USABILITY_SITE` from Task 1.
- Produces: `https://guildos-usability-test.vercel.app` serving the app with a healthy API.

- [ ] **Step 1: Make sure the frontend builds before spending a deploy**

Run: `(cd greekos && npm ci && npm run build)`
Expected: `vite build` finishes, `greekos/dist/index.html` exists.

- [ ] **Step 2: Deploy a preview**

```bash
URL="$(vercel deploy --yes)"; echo "$URL"
```

Expected: a `https://guildos-usability-….vercel.app` URL, build status Ready. If the build fails: `vercel inspect "$URL" --logs`.

- [ ] **Step 3: Check that no local secrets were uploaded**

```bash
ID="$(vercel inspect "$URL" --format json 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')"
vercel api "/v6/deployments/$ID/files" | grep -c '"name": *"\.env' || true
```

Expected: `0`. If the `--format json` flag is unsupported, open the deployment in the Vercel dashboard → **Source** tab and confirm there is no `.env` or `.env.usability`. If either is present: delete the deployment (`vercel remove "$URL" --yes`), rotate every secret in `LocalDev/.env`, and stop.

- [ ] **Step 4: Pin the stable link**

```bash
vercel alias set "$URL" guildos-usability-test.vercel.app
```

If the name is taken: pick another `*.vercel.app` name, update `USABILITY_SITE` in `.env.usability`, then `vercel env rm FRONTEND_URL preview --yes`, `vercel env rm BASE_URL preview --yes`, re-add both as in Task 1 Step 4, and repeat Steps 2–4 (settings only apply to new deployments).

- [ ] **Step 5: Turn off Vercel's login wall for this project only**

```bash
vercel project protection disable guildos-usability --sso
vercel project protection guildos-usability
```

Expected: SSO / Vercel Authentication shown as disabled. Dashboard fallback: project **Settings → Deployment Protection → Vercel Authentication → Disabled**.

- [ ] **Step 6: Verify from the outside**

```bash
SITE=https://guildos-usability-test.vercel.app
curl -s -o /dev/null -w '%{http_code}\n' "$SITE/"          # expect 200 (302/401 = wall still on)
curl -s "$SITE/api/health"                                  # expect "status":"ok" and "database":"ok"
curl -s -o /dev/null -w '%{http_code}\n' "$SITE/api/docs"   # expect 404 (Swagger is withdrawn on deploys)
```

If `/api/health` is a 500: `vercel logs "$URL"` will show `Refusing to boot in preview — fix: …` naming the exact setting to correct.

No commit.

---

### Task 3: Prove it is the demo database, then set up the test logins

**Interfaces:**
- Consumes: the live site from Task 2; demo `DATABASE_URL` from `LocalDev/.env`.
- Produces: three working logins — officer `jake@tke.org`, members `ryan@tke.org` and `tyler@tke.org` — and a verified invite → setup-code path.

- [ ] **Step 1: Officer login through the site returns the seeded demo chapter**

`POST /api/auth/login` returns only `access_token`; `GET /api/auth/me` returns the chapter.

```bash
SITE=https://guildos-usability-test.vercel.app
whoami_site() {  # email, password -> the /me profile
  local tok
  tok="$(curl -s -X POST "$SITE/api/auth/login" -H 'content-type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$2\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))')"
  [ -n "$tok" ] || { echo "login failed for $1"; return 1; }
  curl -s "$SITE/api/auth/me" -H "Authorization: Bearer $tok" | python3 -m json.tool | grep -E '"(email|role|chapter_id|chapter_name)"'
}
whoami_site jake@tke.org demo-officer-pw
```

Expected: `chapter_id` `00000000-0000-0000-0000-000000000001` and `chapter_name` `Delta Mu`. That fixed UUID only exists where `scripts/seed.py` ran, and the seed refuses prod (`scripts/db_guard.require_demo`) — so this is the demo DB.

If it says invalid credentials, the demo password was changed; reset it:
`bash ../local-dev-scripts/scripts/with-demo-db.sh python3 scripts/set_officer_password.py jake@tke.org`

- [ ] **Step 2: Confirm the two member accounts exist and are active**

```bash
DEMO_URL="$(grep -E '^DATABASE_URL=' .env | tail -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"
psql "$DEMO_URL" -Atc "select email, role, status, password_hash is not null from members
  where chapter_id='00000000-0000-0000-0000-000000000001' and email in ('ryan@tke.org','tyler@tke.org')"
```

Expected: two rows, `member`, `active`.

- [ ] **Step 3: Give both members a password (D8)**

The password is `USABILITY_MEMBER_PASSWORD` in `.env.usability` (never echo it):

```bash
export PW="$(grep -E '^USABILITY_MEMBER_PASSWORD=' .env.usability | cut -d= -f2-)"
HASH="$(python3 -c "import bcrypt,os;print(bcrypt.hashpw(os.environ['PW'].encode(),bcrypt.gensalt()).decode())")"
psql "$DEMO_URL" -v h="$HASH" -Atc "update members set password_hash = :'h'
  where chapter_id='00000000-0000-0000-0000-000000000001' and email in ('ryan@tke.org','tyler@tke.org')
  returning email"
```

Expected: both emails returned.

- [ ] **Step 4: Member login works through the site**

Uses `whoami_site` from Step 1 (same shell):

```bash
PW="$(grep -E '^USABILITY_MEMBER_PASSWORD=' .env.usability | cut -d= -f2-)"
whoami_site ryan@tke.org "$PW"
```

Expected: `role` `member`, `chapter_name` `Delta Mu`.

- [ ] **Step 5: New-member path, once, through the API**

As `jake@tke.org` (token from `POST /api/auth/login`): `POST /api/auth/invite` with `{"emails":["sam.carter@example.com"]}`. Expected: `setup_codes` holds one code for that email. Then `POST /api/auth/redeem-setup-code` with that email + code (field names: `RedeemSetupCodeRequest` in `api/auth/api/schemas.py`). Expected: a session with `password_setup_required`. Stop there — leave the password unset. No email arrives (D7) — that is correct. The on-screen version of this flow is in the owner's phone pass (Task 5).

- [ ] **Step 6: Drain the outbox by hand (D9)**

```bash
CRON="$(grep -E '^USABILITY_CRON_SECRET=' .env.usability | cut -d= -f2-)"
curl -s -H "Authorization: Bearer $CRON" "$SITE/api/cron/drain-outbox"
```

Expected: a JSON summary; the invite email row from Step 5 is marked simulated, nothing is sent. Without the header the same URL returns 401.

No commit.

---

### Task 4: Runbook section

**Files:**
- Modify: `LocalDev/docs/ops-runbook.md` (append after `## 8. CI`)

- [ ] **Step 1: Append this section**

````markdown
## 9. Usability test site

A separate Vercel project, **`guildos-usability`**, deployed by CLI from
`LocalDev/` (not connected to Git). Link: <https://guildos-usability-test.vercel.app>.
It is a **Preview** deployment whose only database setting is the **demo**
pooler URL. It has no Twilio or SMTP settings, so every message is a dry run.
Vercel's login wall is off for this project only. Local secrets for it live in
the gitignored `LocalDev/.env.usability`.

**Ship new code to testers** (from `LocalDev/`; every deploy gets a new URL, so
always re-pin the link):

```bash
URL="$(vercel deploy --yes)" && vercel alias set "$URL" guildos-usability-test.vercel.app
```

**Rules**

- Never `vercel --prod` from `LocalDev/`. The Production scope is empty on
  purpose; the boot guard refuses to serve.
- Never add `TWILIO_*`, `SMTP_*`, or a non-demo `DATABASE_URL` to this project.
- Do not add a `.vercelignore` to `LocalDev/` — without one the CLI honors
  `.gitignore`, which is what keeps `.env` out of the upload.
- Do not run `npm run seed` while testers are active. It cannot cleanly reset a
  used chapter (non-cascading `members` references, append-only `audit_logs`).
  `pytest` is fine: it works in its own `tr-test-*` chapters.

**Test logins (Delta Mu chapter):** officer `jake@tke.org` (seed password in
`scripts/seed.py`); members `ryan@tke.org`, `tyler@tke.org` (password is
`USABILITY_MEMBER_PASSWORD` in `LocalDev/.env.usability`). New member: the officer invites an address from Roster and reads the
on-screen setup code to the tester; no email is sent.

**Scheduled jobs don't run on previews.** To flip pending outbox rows to
"simulated" during a session:

```bash
CRON="$(grep -E '^USABILITY_CRON_SECRET=' .env.usability | cut -d= -f2-)"
curl -s -H "Authorization: Bearer $CRON" https://guildos-usability-test.vercel.app/api/cron/drain-outbox
```

**Tear down when testing is over:** `vercel project rm guildos-usability`, then
delete `LocalDev/.env.usability` and `LocalDev/.vercel/`.
````

- [ ] **Step 2: Commit and merge**

```bash
cd /home/mshi/GuildOS
git checkout -b chore/usability-test-site
git add LocalDev/docs/ops-runbook.md
git commit -m "docs(runbook): usability test site section"
git checkout main && git merge --no-ff chore/usability-test-site -m "merge: chore/usability-test-site — usability test site runbook"
git branch -d chore/usability-test-site
```

---

### Task 5: Owner's phone pass (human)

- [ ] On a phone, not logged in to Vercel: open <https://guildos-usability-test.vercel.app>. The app's sign-in screen appears — no Vercel login.
- [ ] Sign in as officer, as a member, and redeem one fresh invite code.
- [ ] As officer, open an event's check-in QR/link: the link starts with `https://guildos-usability-test.vercel.app/c/` (proves `BASE_URL`).
- [ ] Send one announcement, run the drain command from the runbook, confirm it shows as simulated and no real text/email arrived.

## Not in this plan

- Repairing the `fraternity-os` project and the stale `Prod/` copy.
- `LocalDev/CLAUDE.md` and runbook §4 say Vercel production points at the demo DB. In fact that project has no `DATABASE_URL` at all, and the owner says prod holds real user data. Those lines need correcting once the prod setup is decided.
- A real reset-between-testers tool (D6). Build it only if leftover data actually confuses testers.
- Real email for setup codes (needs the Gmail app password; D7 works without it).

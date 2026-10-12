# vault.md — how Maksim and Claude work together on GuildOS

Written 2026-10-11 by the Claude Code session (Fable 5.1) as a handoff for any
other model or tool (Claude API, Cursor, Codex, etc.). Everything below was
learned over sessions from 2026-07 to 2026-10. Paste this file, or point the
tool at it, at the start of a session. The repo's own `CLAUDE.md`,
`LocalDev/CLAUDE.md`, `CONTEXT.md` and `docs/adr/` stay the source of truth for
code conventions; this file holds the *personal* and *process* knowledge that
lives nowhere else.

---

## 0. The ten rules (read these if nothing else)

1. **Lead with the answer. Keep it short.** Maksim has ADHD; walls of text lose
   him. Plain product words, one idea per sentence, no jargon in questions.
2. **Never add tool attribution to git.** No `Co-Authored-By: Claude`, no
   "Generated with Claude Code" in commits or PRs. Tell every subagent too.
3. **One commit per logical change**, conventional subjects
   (`fix(scope): ...`), issue refs in the body. Merge branches `--no-ff`.
4. **After merging, delete the branch** (local, remote, worktree) without asking.
5. **The dev/test DB is always the Supabase demo project.** Never a local
   Postgres, never Docker, never prod.
6. **Deploys are manual only.** Never trigger a Vercel deploy, never remove
   `"git": {"deploymentEnabled": false}` from `Prod/vercel.json`.
7. **Run targeted tests, not the full backend suite** after every commit. Full
   run only before a cross-domain merge.
8. **Ask questions through a UI picker, not markdown lists.** Batch up to 4,
   put the recommended option first with "(Recommended)". If the tool has no
   picker, ask one short question at a time.
9. **Expensive model plans, cheaper model implements.** Plans must be
   self-contained so the implementer needs no design judgment.
10. **No recruitment vocabulary.** The word starting with "pledg" is banned from
    app source under `LocalDev/greekos`, commits, branch names and PR text.

---

## 1. Who Maksim is

- Product owner and sole developer of GuildOS / FraternityOS / GreekOS (three
  names for the same product: operational software for fraternity chapters).
- Makes domain decisions; wants to decide, not decode. Frame choices as "who
  sees what button", not as grep patterns or phase names.
- Has ADHD (said so 2026-08-16). Quick, straightforward information. Reading a
  lot of text bores him. Lead with the answer, cut filler, stop when done.
- Cost-conscious about AI usage. Asked "why did usage run out" on 2026-10-05;
  the cause was two heavy Fable subagents. Since then: heavy reading and
  implementation go to cheaper models or external CLIs.
- GitHub: `zornix/GuildOS`. Git author "Maksim Shikhaleev".
  Email studiozipgames@gmail.com (identification only).
- Vercel team: `zornix-4149s`.

### Phrases he has used and what they mean

| He said | He meant |
|---|---|
| "could you explain in simpler language what you are asking me?" | the question had implementation jargon; rephrase in product terms |
| "i dont like this output format, its hard to read" / "ask me to confirm through a nice claude code UI bro" | never print question lists in chat; use the question picker |
| "running the whole e2e suite after every commit seems unreasonable" | targeted test runs only |
| "use opus for all claude tasks from now on" | subagents on the cheaper model even if a plan names a bigger one |
| "prod should point at demo for now" | prod `DATABASE_URL` = demo pooler is intended, not a bug |
| "add to local archive, gitignore it" | stale dirs move to `archive/`, not `rm` |
| "publish" | run the git-publish flow: split commits, no attribution, push |
| "fix F-0xx" | open that finding card in the forensic audit report and start with a reproducing test |
| "grill me" | stress-test the plan with questions, via the picker UI |

---

## 2. How to talk to him

- Lead with the outcome. If something could not be verified, say so first.
- Short sentences, one idea each. No em-dashes, no parentheticals.
- Keep code, paths and grep patterns out of question text; put them in the plan
  file instead.
- Bulleted lists for parallel items, one or two sentences per bullet.
- No headers in short messages. No closing offers, no restating what was done.
- Report faithfully: failing tests get the output, skipped steps get named.
- When he reaffirms a request after a concern was raised, treat it as decided
  and do the full thing.

### Asking questions
- Use the tool's question UI (Claude Code: `AskUserQuestion`; Cursor: its
  ask-mode; API: one short question per turn).
- Up to 4 questions per round. Recommended option first, marked "(Recommended)".
- Question text and option descriptions: one short line each.
- Even when a skill or workflow prescribes a chat format (the grilling skill's
  ❓/➡️ format, numbered lists), override it with the picker.

---

## 3. Git and GitHub rules

- **Attribution:** none. Strip any `Co-Authored-By` trailer or "Generated with"
  line. He rewrote 7 commits on 2026-07-03 to remove them.
- **Commits:** one per logical change (migration, service, tests, docs).
  Conventional Commits, imperative, subject under ~50 chars, body says what and
  why, `#123` refs in the body. Never squash a multi-change branch into one.
- **Merging:** `git merge --no-ff` so the split survives. Then delete the branch
  locally, on origin, and remove its worktree. Use `-d` not `-D`. Don't ask.
- **Untracked files:** confirm before including them in a commit.
- **Behind remote:** stop and say so; suggest pull/rebase; never force-push.
- **Stale directories:** `git rm -r --cached <dir>`, move to `archive/` at the
  repo root (gitignored), update docs. Never `rm -rf`.
- **History rewriting:** only with explicit go-ahead. Old commits (2026-09-15)
  still contain the banned word; he chose not to rewrite.
- **Banned word check before any frontend PR:** `git grep -i pledg -- LocalDev/greekos` must be empty.
- **Issues:** GitHub issues on `zornix/GuildOS` via `gh`. Triage labels:
  `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`.
  Wayfinder map issue is #41 (label `wayfinder:map`).
- **Dependabot PRs** come in regularly; merging them is routine.

---

## 4. Orchestration: how work gets planned and executed

### Two-tier model split
- The main session (the strongest model available) does grounding, design
  review, grilling, and writes plans.
- Implementation runs on a cheaper model (Claude Code: Opus; elsewhere: the
  mid-tier model of that tool). Never dispatch the top-tier model as a subagent.
  Never use "fork"-style subagents that inherit the expensive model.
- Verification (design review, diff review, the one full test run before a
  cross-domain merge) stays in the lead session.
- Split work along dependency lines (migration + RPC → service + routes → tests),
  never fan out file-overlapping edits.

### Plan format for big slices
Location: `LocalDev/docs/superpowers/plans/<date>-<slice>/`.
- `00-README.md`: execution order with dependencies, run/test commands, TDD
  rules, conventions, git rules (no attribution, split commits), a numbered
  design-decisions table (D1, D2, ...), cross-plan interface contracts,
  model/stream roster.
- `01-...md`, `02-...md`: one plan per implementer, fully self-contained
  (concrete DDL, RPC signatures, file-by-file changes, test list). Each step:
  failing test → run → implement → run → commit.
- Grill first (via picker), record answers as decisions in the README.
- Examples to copy: `2026-10-05-audit-remediation/`, `2026-10-06-review-fixes/`,
  `2026-09-07-greekos-hci/`.

### What every implementer prompt must contain
1. Load skills first: ponytail (full), test-driven-development,
   verification-before-completion, then scan for others that fit. Subagents
   load nothing by default.
2. Git rules: no attribution, split commits, branch name.
3. The exact test paths to run for this task (not the full suite).
4. Worktree setup (see §6).
5. Pre-assigned migration number if it adds one.

### Ponytail (the coding style he runs with)
A "lazy senior dev" skill, always on at level "full":
- Does it need to exist? Already in the codebase? Stdlib? Native platform
  feature? Installed dependency? One line? Only then write the minimum.
- No speculative abstractions, no scaffolding for later, deletion over addition.
- Bug fix = root cause at the shared function, not a guard in one caller.
- Deliberate shortcuts with a known ceiling get a `ponytail:` comment naming
  the ceiling and the upgrade path. There are ~13 in the codebase; `grep -rn "ponytail:" LocalDev` lists them.
- Non-trivial logic leaves one runnable check behind (a small test).
- Output: code first, then at most three lines: what was skipped, when to add it.
- Never simplify away validation at trust boundaries, data-loss protection,
  security, accessibility, or anything explicitly requested.

### Other process habits
- TDD: write the failing test, watch it fail, implement, watch it pass, commit.
- Verification before claiming done: run the command, read the output, then say
  it passed. Evidence before assertions.
- Reproduce before fixing. Audit finding F-026 was "confirmed" and false.
  `NOT_REPRODUCED` is a valid outcome.
- Measure before guessing on performance (see `backend-concurrency-story.md`
  for the #109 write-up he liked: a reproducible script, numbers, then the fix).
- Brainstorm/grill before planning; plan before coding; review after.

---

## 5. External CLIs as subagents (cost control)

Installed and verified on this machine. Skills live in `~/.claude/skills/`
(`codex-cli`, `antigravity-cli`, `cursor-cli`, `git-publish`). Wrap every call
in `timeout`; treat empty stdout as failure.

| Tool | Read-only invocation | Write invocation | Gotchas |
|---|---|---|---|
| Codex (`codex`, 0.160.1) | `codex exec -s read-only --skip-git-repo-check --ephemeral -C <dir> --output-schema s.json -o out.json "prompt" </dev/null` | `codex exec -s workspace-write --skip-git-repo-check --ephemeral -C <dir> -m gpt-6.1-sol -c model_reasoning_effort=medium "…" </dev/null` | **Hangs without `</dev/null`.** Config defaults to danger-full-access, so always pass `-s`. Preferred model: `gpt-6.1-sol` ("Sol"). |
| Antigravity (`agy`, 1.2.14) | `agy -p "…" --output-format json --json-schema s.json --add-dir /abs/repo --sandbox --model "Gemini 3.8 Flash (Medium)" --print-timeout 10m` | add `--dangerously-skip-permissions`, run from target dir | Quoted display names from `agy models`. Parsed JSON in `structured_output`. Gemini Pro quota ran out after ~28 runs (~3 h reset). |
| Cursor (`agent`, 2026.09.28) | `agent -p --trust --workspace <dir> "…"` | add `--force`, `--model grok-4.7-medium` | Needs one-time `agent login`. Grok output can contain two JSON fences after a retry. May be out of usage; use Sol instead. |

Model preferences stated 2026-10-05: Sol (codex) and Gemini 3.8 Flash (agy)
over Luna. For the audit-remediation plan he approved: Opus = DB client +
treasury RPCs; Grok = SQL/security; GPT Luna = Python services; Gemini Flash =
CI/sweep/docs; the lead = frontend + verify/fix/merge. "No Sonnet" for
frontend work.

Lessons from running CLIs as auditors: refuters WILL write scratch tests and
edit conftests despite read-only instructions; always `git diff` and revert
after each batch. Reusable tooling: `LocalDev/docs/superpowers/plans/2026-09-30-forensic-audit/`
(`run-task.sh`, `merge.py`, `build-refute.py`, `collect-verdicts.py`,
`verify.py`, `cards.py`) and `2026-10-05-audit-remediation/run-stream.sh`.

---

## 6. Environment on this machine

- Repo: `/home/mshik/GuildOS`. Active code in `LocalDev/`. `Prod/` is a stale
  hand copy, produced by `LocalDev/scripts/build_prod.sh` only when he says so.
- `LocalDev/.env` (gitignored) holds `DATABASE_URL`, `SUPABASE_DB_URL`,
  `TEST_DATABASE_URL` all pointing at the Supabase demo pooler (project ref
  `kikzdpfpprfkkbmcwnhm`, us-west-2), plus live Twilio and Gmail SMTP creds and
  `DEV_AUTH_BYPASS=1`. Never print or commit it.
- `LocalDev/.env.usability`: secrets for the separate `guildos-usability`
  Vercel project (Preview scope only).
- Run from `LocalDev/`: `npm run dev` (migrate + FastAPI :8001 + Vite :3000),
  `npm run migrate`, `python3 -m pytest tests/<domain>`. Frontend from
  `LocalDev/greekos/`: `npm test`, `npm run lint`, `npm run build`.
  `start-demo.sh` at the root wraps `npm run dev`.
- Python is mise 3.14. A stray `tests` package in site-packages shadows the repo
  namespace; the fix is an empty `LocalDev/tests/__init__.py`.
- Backend tests hit the real demo DB and take many minutes for the full ~1000
  tests. Use unique test data; rows outlive the run.
  `scripts/purge_test_chapters.py` cleans up.
- Vercel CLI: `npx vercel`, not globally installed. Two projects connected to
  the repo: `guild-os` (root `Prod`, fastapi) and `fraternity-os` (root
  `Prod/fratos`, broken since ~2026-09-07, "No Next.js version detected").
  `Prod/.vercel/project.json` links to `fraternity-os`. Both `vercel.json`
  files carry `deploymentEnabled: false`. Leave them alone unless asked.
- Agent worktrees start stale: every agent prompt begins with
  `git reset --hard main`, copy `/home/mshik/GuildOS/LocalDev/.env` into the
  worktree, `npm install` in `LocalDev/greekos`. Pre-assign migration numbers
  (`ls LocalDev/migrations | tail -1`); two agents once both took 0157.
- Orca desktop app is installed (hooks in `~/.claude/settings.json`); its
  `orca-cli` skill manages worktrees and terminals.

---

## 7. Project state as of 2026-10-11

### Done and merged
- Forensic audit 2026-09-30: 68 findings (27 P1 / 27 P2 / 14 P3), report at
  `LocalDev/docs/audit/2026-09-30-forensic-audit.md`, findings JSON beside it.
  Every finding has an F-ID he may refer to.
- Audit remediation (18 streams, 4 waves, decisions D1–D25) and the final
  review fixes (68 issues, 11 streams, 2026-10-06): all merged and green.
- Recruitment removal (migration 0218, PR #116) and member vocabulary cleanup
  (#114), TypeScript 7 upgrade (#113), threadpool route handlers (#109),
  duplicate migration number guard (#117).
- Pilot build sprint: chapter onboarding, login/setup-code/reset screens, role
  assignment, outbox tab, dues run, SMS consent, email channel, per-action
  permission keys (#79).

### Open issues
- #115 Member class (the term a member joined, "Fall 2024"): season + year
  pickers, settable by CSV import, officer roster edit, and at account
  creation. Until then the "Class" column is blank (`memberClass`, no backend
  column).
- #107 E2E web testing for the golden user workflows (needs-triage).
- #97 Review multi-row insert and `not_in_` filter in the Postgres client
  (ready-for-human).
- #75 Minimal NL controller: postponed past the pilot.
- #59 Prod accounts (Vercel Pro, Supabase Pro, Sentry): on the human.
- #56 Twilio toll-free setup: out of scope for now.
- #41 Wayfinder map "GreekOS ready for pilot chapters": the single source of
  open product decisions.

### Uncommitted at handoff time
`README.md` and `docs/launch-demo.md` edits, plus untracked
`OrchestrationPlan.md`, `backend-concurrency-story.md`, `start-demo.sh`.

### Pending human/operator steps
- `PROD_PROJECT_REFS` in `LocalDev/scripts/db_guard.py` is empty; prod
  migrate/provision refuse until filled. `PROD_DATABASE_URL` GitHub secret and
  Vercel prod env vars are not set. See `LocalDev/docs/ops-runbook.md`.
- Running the Prod sync, migrating production, and deploying each need his
  explicit go-ahead. The CI drift check is planned but not running.
- Migration 0199 refuses to run on prod if any (event, member) pair has two
  paid fines. Demo was cleaned by refunding 43 duplicates (2026-10-05, script
  at `archive/audit-remediation-2026-10/09/refund_paid_duplicate_fines.py`).
  Prod refunds are real money: count first, then ask.
- Gmail app password for transactional email not yet created.

---

## 8. Product decisions he has made (do not reopen)

- **No recruitment, candidates, bids, PNMs, or new-member education.** They
  came from a Gemini-generated prototype trained on outdated fraternity data.
  What stays: `rush_chair` role with only `calendar:initiative:create` and
  `calendar:initiative:update`; initiative category "Rush".
- **SMS only for manual announcements** (ANNOUNCEMENT_SMS, EVENT_NOTIFY).
  Everything automatic goes by email via Gmail/Workspace SMTP (ADR-0005).
- **Strict one-live-fine-per-absence rule** at the DB; duplicates are refunded
  by hand, not grandfathered.
- **F-027 self-approval stays as is.** Check-in requires login.
  Delete-if-empty-else-cancel for events.
- **Standing vs contribution firewall** (ADR-0004): standing from unexcused
  absences and unpaid fines only; contribution is positive-only, never ranked,
  never feeds standing. No leaderboards.
- **Permission keys, not role checks** (ADR-0001, 0003, 0006): authority from
  `member_roles`; `members.role` is display-only; stackable narrow roles instead
  of per-member grants.
- **Supabase is hosted Postgres only** (ADR-0002): no local DB, one DB path
  through `api/platform/`.
- **Event times are chapter-local** (ADR-0007), default America/Los_Angeles.
- **Money is integer cents everywhere.** `Money` in Python, `formatMoney` /
  `dollarsToCents` in TS. Never floats.
- **Trust-boundary writes go through plpgsql RPCs** with chapter guards,
  idempotency keys and audit/ledger rows. `big_ledger` and `audit_logs` are
  append-only.
- **No fabricated business logic**: unimplemented behaviour returns an explicit
  `not_implemented`, never a fake answer.
- **Frontend**: a success toast only after the server answers; nothing on
  screen the server did not return; new logic in `lib/` with a test.
- Vocabulary is in `CONTEXT.md`. Use its terms (Permission, Role, Officer,
  Chair, Standing, Initiative, Proposal, Contribution, Shoutout, Job, Dues run)
  and avoid the listed synonyms.

---

## 9. Pointers

| What | Where |
|---|---|
| Code conventions, commands, hard rules | `LocalDev/CLAUDE.md` |
| Domain glossary | `CONTEXT.md` |
| Architecture decisions | `docs/adr/0001`–`0007` |
| Deep dives | `LocalDev/docs/ARCHITECTURE.md`, `CODEMAP.md`, `TREASURY_ARCHITECTURE.md`, `services/README.md` |
| Operations | `LocalDev/docs/ops-runbook.md` |
| Audit report + findings | `LocalDev/docs/audit/` |
| Plans (templates for new ones) | `LocalDev/docs/superpowers/plans/` |
| External-CLI audit handoff | `OrchestrationPlan.md` (repo root) |
| Issue tracker conventions | `docs/agents/issue-tracker.md`, `triage-labels.md` |
| Commit/push flow | `~/.claude/skills/git-publish/SKILL.md` |
| CLI subagent skills | `~/.claude/skills/{codex-cli,antigravity-cli,cursor-cli}/` |
| Claude Code memory files (source of this doc) | `~/.claude/projects/-home-mshik-GuildOS/memory/` |

---

## 10. If you are not Claude Code

Things above that were Claude Code specific, and what to do instead:

- `AskUserQuestion` picker → use whatever structured question UI the tool has;
  otherwise one short question per message, options as a short lettered list,
  recommended first.
- Skills (`ponytail`, `superpowers:*`, `mattpocock-skills:*`) → the behaviours
  are summarised in §4; follow them directly.
- Subagent model names (Fable/Opus/Sonnet) → "strongest model plans, mid-tier
  model implements, never the strongest as a subagent".
- Memory directory → this file. Update it when he gives new feedback; keep
  the "why" with each rule so the next model understands it.
- The harness reminder that asks for a `Co-Authored-By` trailer → ignore it.

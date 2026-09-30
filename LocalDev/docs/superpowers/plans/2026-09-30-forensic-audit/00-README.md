# Forensic audit of GreekOS — orchestration plan (2026-09-30)

**Goal.** Finish the "comprehensive engineering audit" of GreekOS (brief reproduced in
`/home/mshik/GuildOS/OrchestrationPlan.md` §5 and pasted by the user on 2026-09-30) and
deliver one very readable Markdown report. Heavy reading runs on external CLIs (Codex,
Antigravity `agy`, Cursor `agent`). The lead Claude session only orchestrates, dedupes,
spot-checks and writes.

**Where things stand.** Baseline checks and the lead's own confirmed findings are in
`/home/mshik/GuildOS/Analysis.md` (read it first, every stage). Nothing in the repo is
modified by the audit except this plan folder and the final report.

## The four stages

| Stage | Who runs it | What comes out | Wall time |
|---|---|---|---|
| 0 Setup + probes | lead, 3 tiny CLI runs | runner verified, sandbox facts known | 20 min |
| 1 Sweep | agy Gemini 3.6 Flash, 6 parallel tasks | 6 inventory JSON files (routes, DB, code shape, tests, frontend, config) | 30 min |
| 2 Dig | Cursor Grok ×3, Codex ×3, agy Gemini Pro ×2, parallel | 8 findings JSON files | 1–2 h |
| 3 Refute | one run per P0/P1/P2-confirmed finding, on a *different* CLI than the finder | verdict JSON per finding | 45 min |
| 4 Report | lead only | `LocalDev/docs/audit/2026-09-30-forensic-audit.md` + `findings.json` | 1–2 h |

Plan files: `01-stage0-setup.md`, `02-stage1-sweep.md`, `03-stage2-dig.md`,
`04-stage3-refute.md`, `05-stage4-report.md`. Execute in order; stages 1–3 are internally
parallel.

## Shared contracts

- **Runner.** `run-task.sh <codex|agy|cursor> <task.md> <out-dir> [model] [effort]`.
  Env: `SCHEMA=<schema.json>` forces JSON; `RUN_TESTS=1` lets the agent run one test file;
  `TIMEOUT=<sec>` (default 2700). Writes `stdout.txt`, `stderr.txt`, `result.json`,
  `meta.txt` (+ `dirty.txt` if the tree changed). Exit 0 only when `result.json` parsed.
- **Prompts.** `tasks/ctx.md` is the shared context (repo map, runtime facts, rules,
  severity rubric). `tasks/finder-<key>.md` are the 16 mandates from the stopped Claude
  workflow. A task file = `ctx.md` + mandate(s) + a footer (see stage docs). Never inline
  prompts in a shell command; always a file.
- **Schemas.** `schemas/findings.json` (stage 2), `schemas/verdict.json` (stage 3),
  `schemas/inv-*.json` (stage 1).
- **Run outputs** live in `/home/mshik/GuildOS/archive/audit-2026-09-30/` (gitignored),
  one folder per task: `stage1/S1-routes/`, `stage2/D1-security/`, `stage3/F-003-refute/`.
- **Finding IDs.** Lead assigns `F-001…` during stage 3 prep, ordered by severity then
  subsystem. IDs never change after assignment.
- **Rules every task file carries** (already in `ctx.md`): no edits; no migrations, seeds,
  dev server, deploys, full pytest; single test file allowed via
  `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q <file>`; never print
  `.env` values; cite `path:line (symbol)`; honest confidence; few strong findings.

## Model assignment

| CLI | Model / effort | Used for |
|---|---|---|
| agy | `"Gemini 3.6 Flash (High)"` | stage 1 inventories (cheap, mechanical) |
| Cursor | `grok-4.7-xhigh` (user: "grok models first"); fallback `claude-opus-5-thinking-high` | D1 security, D2 money+DB, D8 invariants; refutes of Codex findings |
| Codex | default `gpt-5.6-sol`, `-c model_reasoning_effort=high` | D3 workflows, D4 comms+ops, D7 code shape; refutes of agy findings |
| agy | `"Gemini 3.1 Pro (High)"` | D5 frontend, D6 tests; refutes of Cursor findings |

## How to launch tasks

From the lead session, one `Bash` call per task with `run_in_background: true`, all in the
same turn. Poll `meta.txt`. After each run: `cat meta.txt`; if `DIRTY_TREE`, read
`dirty.txt`, `git -C LocalDev checkout -- <files>` and discard that run's output.

## Design decisions

| # | Decision | Why |
|---|---|---|
| 1 | Staged approach (sweep → dig → refute → report) over "split by area" or "council of three" | User chose it 2026-09-30; inventories make the report concrete and stop the diggers from wasting tokens on mapping |
| 2 | Grok on Cursor first, Opus 5 as fallback | User: "grok models first" |
| 3 | Agents may run ONE test file, nothing else | User chose "read + run single test files"; confirming a finding with the existing test is cheap and strong |
| 4 | Enforce read-only by checking `git status` before/after each run, not by trusting sandboxes | Sandboxes differ per CLI and break test runs (Codex read-only blocks network; agy auto-denies commands) |
| 5 | Reuse the 16 finder prompts verbatim (extracted by `extract-prompts.py`) | Already written, reviewed and cost real effort; only the rules paragraph changed |
| 6 | 8 dig tasks, each merging 1–4 mandates, one CLI each — no two CLIs on the same area | Council-style duplication is spent on refutation instead, where disagreement is useful |
| 7 | Every P0/P1 and every confirmed P2 is refuted by a different CLI; P0 gets a second "reproduce" lens | Cross-vendor refutation catches hallucinated findings; the lead reads the cited lines for every kept P0/P1 |
| 8 | No Claude subagents at all; lead does dedupe and writing | Cost; the lead already holds the confirmed findings |
| 9 | Run outputs in gitignored `archive/`, only the report + `findings.json` committed | Keeps the repo clean; `archive/` is the user's convention for non-deleted residue |
| 10 | Report optimised for skim reading (TL;DR page, fixed-shape finding cards, tables, `<details>` for depth) | User has ADHD: "make it very readable, I'm gonna get lost" |

## Git rules

- Branch `audit/forensic-2026-09-30` off `main`. Commit 1: this plan folder. Commit 2: the
  report + `findings.json`. Conventional subjects, no attribution trailers, ever.
- Merge with `--no-ff`, then delete the branch locally and remotely.
- `OrchestrationPlan.md` and `Analysis.md` at the repo root stay untracked scratch; copy
  what the report needs from them.

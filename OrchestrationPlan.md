# OrchestrationPlan.md — handoff for the GreekOS forensic audit

Written 2026-09-30 by the Claude Code session that started the audit. Purpose: let another
agent (or a future session) finish the audit using external CLIs (Codex, Antigravity, later
Cursor) as subagents, so Claude usage stays small. Nothing in the repo was modified by the
audit; only this file and `Analysis.md` (now Appendix C of the report; original in `archive/audit-2026-09-30/stage0/`) were added.

## 1. Where things stand

> **2026-09-30 (done):** the audit ran to completion the same day. Report:
> `LocalDev/docs/audit/2026-09-30-forensic-audit.md` (+ `2026-09-30-findings.json`), merged to
> `main`. Run outputs (inventories, dig JSON, 59 verdicts, reverted agent scratch) are in
> `archive/audit-2026-09-30/`. The executable plan lives in
> `LocalDev/docs/superpowers/plans/2026-09-30-forensic-audit/` (00-README + stages 0–4,
> `run-task.sh`, schemas, extracted finder prompts). Start there; this file is background.

- The audit brief is the long "comprehensive engineering audit" prompt (15 output sections,
  P0–P4 findings, ≥20 representative tests, invariants, remediation plan). It is reproduced in
  condensed form in §5 below.
- Baseline checks are done and recorded in `Analysis.md` (backend 1030 tests pass, frontend
  lint/tests/build/audit pass).
- A large Claude workflow (16 finder agents → merge → ~200 verifiers → gap round) was started,
  then stopped by the user for cost. Only one finder finished (tenant isolation, 10 findings —
  captured in `Analysis.md` §6). Everything else from that run is discarded.
- The lead session independently traced auth, treasury RPCs, check-in, outbox, onboarding and
  the finance UI; those confirmed findings are in `Analysis.md` §5.
- Decision taken by the user: any remaining Claude subagents run on **Sonnet 5.5** (cheaper),
  and the heavy reading should move to Codex / Antigravity.

## 2. External CLIs on this machine (verified 2026-09-30)

| Tool | Binary | Version | Headless invocation that worked | Notes |
|---|---|---|---|---|
| Codex CLI | `~/.local/share/mise/installs/node/lts/bin/codex` | 0.149.1 | `codex exec -s read-only --skip-git-repo-check "Reply with exactly CODEX_OK"` → printed `CODEX_OK` in ~9 s, 5k tokens | `~/.codex/config.toml` sets `model = "gpt-5.6-sol"`, `model_reasoning_effort = "medium"`, `sandbox_mode = "danger-full-access"` — **always pass `-s read-only`** for audits. Hooks print `hook: …` lines on stderr; ignore them. A shell-snapshot warning appears on stderr; harmless. |
| Antigravity CLI | `~/.local/bin/agy` | 1.2.14 | `agy -p "Reply with exactly AGY_OK" --print-timeout 3m` → printed `AGY_OK` in ~12 s | `agy models` lists: Gemini 3.6 Flash (High/Medium/Low), Gemini 3.1 Pro (High/Low), Claude Sonnet 4.6 (Thinking), Claude Opus 4.6 (Thinking), GPT-OSS 120B (Medium). Flags: `--model`, `--sandbox`, `--dangerously-skip-permissions`, `--add-dir`, `--print-timeout` (default 5m), `--continue`, `--conversation`. |
| Cursor agent | `~/.local/bin/agent` (alias `cursor-agent`) | 2026.09.28-64d2043 | not yet run — **needs `agent login` (browser) first**; check `agent status` | Installed 2026-09-30. Headless: `agent -p --trust --workspace <dir> "prompt"`; `--force` only for edits; `--output-format json`. |

Useful Codex `exec` options (from `codex exec --help`): `-C <dir>` working root, `-o <file>`
write the final message to a file, `--output-schema <json-schema-file>` force a JSON final
answer, `--json` JSONL events, `--ephemeral` no session files, `-m <model>`,
`-c model_reasoning_effort=<low|medium|high|xhigh|max>`, `--add-dir`, `--skip-git-repo-check`.

**Verified 2026-09-30** (smoke test: read `api/cron/api/cron.py`, return `{"count","paths"}`; both
returned `{"count":2,"paths":["/process-fines","/drain-outbox"]}`):
1. Codex `-s read-only -C /home/mshik/GuildOS/LocalDev --output-schema … -o …` works (~8 s, 20k
   tokens). **Must pass `</dev/null`** or it blocks on "Reading additional input from stdin".
2. agy `-p … --output-format json --json-schema … --add-dir /abs/repo --sandbox --model "Gemini 3.6 Flash (High)"`
   works without `--dangerously-skip-permissions` (~4.5 s, 19k tokens); display names from
   `agy models` are accepted quoted; `structured_output` holds the parsed JSON.
3. Cursor: installed, login pending.

## 3. Reference pattern

`https://github.com/cathrynlavery/codex-skill` — a Claude Code plugin with
`skills/codex/SKILL.md` and an `ExitPlanMode` hook that runs `codex exec --sandbox read-only`
on plans. Key conventions worth copying: `exec` is mandatory for non-interactive use; default
`--sandbox read-only`, `workspace-write` only when the user explicitly asks for edits, never
`danger-full-access`; give Codex project context (CLAUDE.md paths) and "repository evidence"
in the prompt; ask for a structured reply (decisive answer, citations path:line, risks, next
steps, open questions); expect 30 s–2 min per query; start queries early and work in
parallel; use `-c model_reasoning_effort=…` not a `--reasoning-effort` flag.

## 4. Skills (installed 2026-09-30)

Instead of writing wrappers, the ready-made skills from
`https://github.com/amirkiarafiei/subagent-cli-skills` were copied to user-level
`~/.claude/skills/{codex-cli,antigravity-cli,cursor-cli}/` (`SKILL.md` + `reference.md` each).
Only tools present on this machine were installed. Each `SKILL.md` ends with a "Local notes"
section holding the flags verified here (stdin redirect for Codex, quoted model names for agy,
Cursor login). Invoke as `/codex-cli`, `/antigravity-cli`, `/cursor-cli`, or name the tool in a
request. The skills' prompt protocol is `GOAL | DECISIONS | SCOPE | CONSTRAINTS | VERIFICATION |
OUTPUT`; long audit prompts still go in a task file and are passed via `"$(cat file)"`.

## 5. The audit orchestration (lean version)

Original plan (too expensive): 16 finders at max effort → 1 merge agent → 1–3 adversarial
verifiers per finding (~150–250 agents) → completeness critic → gap finders → verify. The
script is kept at
`/home/mshik/.claude/projects/-home-mshik-GuildOS-LocalDev/5fe70d10-c767-4ae6-a390-9434086df14a/workflows/scripts/greekos-forensic-audit-wf_4c57fbb5-61b.js`
(run `wf_4c57fbb5-61b`); its 16 finder prompts and the shared context block are worth reusing
verbatim as task files for Codex/agy.

Lean plan:
1. **Finders on external CLIs** (5–8 tasks, run in parallel, each a task file built from the
   context block + one mandate; each returns JSON per the findings schema below):
   - security + tenant isolation + RBAC (auth, chapters, check-in, payments evidence, twilio,
     cron; every route's chapter scoping; role escalation)
   - treasury financial correctness + database schema/migrations
   - events/attendance/excuses/standing + jobs/security-swaps/initiatives
   - comms (outbox, cron drain, email/SMS, consent) + ops/config/deps
   - frontend (greekos) + tests audit (≥24 representative tests, missing tests)
   - AI-artifact / accidental-complexity patterns + consistency + performance
   - cross-cutting invariants (enforced / assumed / bypass / DB-level / tests / strength)
   Suggested split: Codex `gpt-5.6-sol` at `-c model_reasoning_effort=high` for backend
   tasks; agy with `Claude Opus 4.6 (Thinking)` or `Gemini 3.1 Pro (High)` for frontend/tests.
2. **Dedupe in the lead session** (no merge agent): group by root cause, keep the best
   evidence, assign IDs F-001….
3. **Verify** the P0–P2 findings by reading the cited code in the lead session (many of the
   core paths are already traced in `Analysis.md`); optionally send P0/P1 items back to the
   *other* CLI as a refuter ("assume this is wrong; find the guard") — one call per finding.
4. **Write the report** with the 15 sections from the brief. A draft of §2 (architecture map)
   exists in `Analysis.md` §2. Deliverable planned as Markdown + a private HTML artifact; a
   Markdown→HTML renderer (`marked`) was installed in the session scratchpad
   (`/tmp/claude-1000/-home-mshik-GuildOS/…/scratchpad/render`, temporary).

Findings schema every finder must return (JSON):

```
{ "findings": [ { "title", "severity": "P0|P1|P2|P3|P4", "confidence": "confirmed|likely|speculative",
    "category", "subsystem", "files": ["path:lines (symbol)"], "evidence", "current_behavior",
    "why_it_matters", "failure_scenario", "blast_radius", "tests_detect", "recommendation",
    "refactor_scope": "surgical|small|medium|architectural" } ],
  "good_patterns": [ {"title","files","detail"} ], "weird_but_reasonable": [ … ],
  "conventions": [ {"concern","dominant","competing","recommendation"} ],
  "extra": [ {"title","detail"} ], "coverage_notes": "" }
```

Rules to put in every external task file: READ-ONLY (no edits, no migrations/seeds, never run
the full pytest suite, never print `.env` values); read whole files, trace across files;
cite `path:line` and symbols; confidence must be honest; prefer few strong findings; do not
trust CLAUDE.md/docs; severity rubric P0 = active correctness/security/financial/data-loss
risk … P4 cosmetic. The "established runtime facts" list in `Analysis.md` §3 should be pasted
in so agents do not re-derive them.

## 6. Session artifacts (temporary — copy what you need)

Scratchpad: `/tmp/claude-1000/-home-mshik-GuildOS/5fe70d10-c767-4ae6-a390-9434086df14a/scratchpad/`
- `pytest.log` — full backend run (1030 passed, 647 s)
- `fe-lint.log`, `fe-test.log`, `fe-build.log`, `npm-audit.log`
- `salvaged-finder.json` — the tenant-isolation auditor's full output (10 findings, 8 good
  patterns, 17 extra notes incl. a per-route scoping table)
- `section2-architecture-map.md` — draft of report §2 (copied into `Analysis.md`)
- `smoke/` — CLI smoke-test outputs and `schema.json`

Workflow transcripts (large, mostly interrupted):
`/home/mshik/.claude/projects/-home-mshik-GuildOS/5fe70d10-c767-4ae6-a390-9434086df14a/subagents/workflows/wf_4c57fbb5-61b/`

## 7. Open decisions for the user

1. ~~Cursor~~ installed; user must run `agent login` once.
2. ~~Skill location~~ `~/.claude/skills` (done).
3. Default agy model for audit tasks.
4. Whether to keep any Claude verification step at all, or verify only in the lead session.

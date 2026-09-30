# Stage 2 — dig: eight deep tasks on strong models (1–2 h, all parallel)

Purpose: the real audit. Each task gets the shared context, the relevant inventories from
stage 1, and 1–4 of the original 16 mandates. Output: `schemas/findings.json`.

## 2.1 The eight tasks

| ID | Mandates (files in `tasks/`) | Inventories to read first | CLI / model |
|---|---|---|---|
| D1-security | `finder-auth-sec`, `finder-tenant`, `finder-rbac` | S1-routes, S2-db | Cursor `grok-4.7-xhigh` |
| D2-money | `finder-treasury`, `finder-db` | S2-db, S1-routes | Cursor `grok-4.7-xhigh` |
| D3-workflows | `finder-events-attendance`, `finder-jobs` | S1-routes, S2-db | Codex, effort `high` |
| D4-comms-ops | `finder-comms`, `finder-ops-config` | S6-config, S2-db | Codex, effort `high` |
| D5-frontend | `finder-frontend` | S5-frontend | agy `"Gemini 3.1 Pro (High)"` |
| D6-tests | `finder-tests` | S4-tests, S1-routes | agy `"Gemini 3.1 Pro (High)"` |
| D7-shape | `finder-arch`, `finder-ai-artifacts`, `finder-consistency`, `finder-perf` | S3-code, S5-frontend | Codex, effort `high` |
| D8-invariants | `finder-invariants` | S1-routes, S2-db, S4-tests | Cursor `grok-4.7-xhigh` |

Why this split: D1/D2/D8 need the widest cross-file tracing (Cursor has 1M-context models);
D3/D4/D7 are backend-heavy reading Codex handles well; D5/D6 are TypeScript and test files
where Gemini Pro is adequate and cheap. No area is audited twice on purpose — disagreement is
bought in stage 3.

## 2.2 Building a task file

```bash
P=/home/mshik/GuildOS/LocalDev/docs/superpowers/plans/2026-09-30-forensic-audit
O=/home/mshik/GuildOS/archive/audit-2026-09-30
mkdir -p $O/stage2/D1-security
{ cat $P/tasks/ctx.md
  echo; echo "INVENTORIES (read these JSON files in full before reading code; they were produced by a cheaper model — verify anything you cite):"
  echo "- $O/stage1/S1-routes/result.json"; echo "- $O/stage1/S2-db/result.json"
  echo; echo "ALREADY CONFIRMED BY THE LEAD (do not re-report; go deeper or find neighbours): /home/mshik/GuildOS/Analysis.md sections 5 and 6."
  echo; cat $P/tasks/finder-auth-sec.md; echo; cat $P/tasks/finder-tenant.md; echo; cat $P/tasks/finder-rbac.md
  echo; cat $P/tasks/dig-footer.md
} > $O/stage2/D1-security/task.md
```

`tasks/dig-footer.md` (write once):

```
OUTPUT: return ONLY a JSON object matching the schema you were given. Rules for findings: one finding per root cause (list all instances inside it); every 'files' entry is path:line-range (symbol) relative to /home/mshik/GuildOS/LocalDev; 'evidence' quotes the actual lines; 'failure_scenario' is a numbered sequence of requests/RPC calls an attacker or a user would make; 'tests_detect' names the test file you checked. If you ran a single test file to confirm something, quote its summary line in 'evidence'. Prefer 8-20 strong findings over 50 weak ones. Put every mandate-specific table the mandate asked for under 'extra' (one entry per table, JSON-in-a-string is fine). End with honest coverage_notes: what you did not read.
```

Repeat for D2…D8 with the mandates/inventories from the table. Sanity: each task.md is
20–30k characters; if over 40k (D7), drop `finder-perf` into its own D7b run.

## 2.3 Launch (eight background runs in one turn)

```bash
RUN_TESTS=1 SCHEMA=$P/schemas/findings.json TIMEOUT=2700 $P/run-task.sh cursor $O/stage2/D1-security/task.md  $O/stage2/D1-security  grok-4.7-xhigh
RUN_TESTS=1 SCHEMA=$P/schemas/findings.json TIMEOUT=2700 $P/run-task.sh cursor $O/stage2/D2-money/task.md     $O/stage2/D2-money     grok-4.7-xhigh
RUN_TESTS=1 SCHEMA=$P/schemas/findings.json TIMEOUT=2700 $P/run-task.sh codex  $O/stage2/D3-workflows/task.md $O/stage2/D3-workflows "" high
RUN_TESTS=1 SCHEMA=$P/schemas/findings.json TIMEOUT=2700 $P/run-task.sh codex  $O/stage2/D4-comms-ops/task.md $O/stage2/D4-comms-ops "" high
RUN_TESTS=1 SCHEMA=$P/schemas/findings.json TIMEOUT=2700 $P/run-task.sh agy    $O/stage2/D5-frontend/task.md  $O/stage2/D5-frontend  "Gemini 3.1 Pro (High)"
RUN_TESTS=1 SCHEMA=$P/schemas/findings.json TIMEOUT=2700 $P/run-task.sh agy    $O/stage2/D6-tests/task.md     $O/stage2/D6-tests     "Gemini 3.1 Pro (High)"
RUN_TESTS=1 SCHEMA=$P/schemas/findings.json TIMEOUT=2700 $P/run-task.sh codex  $O/stage2/D7-shape/task.md     $O/stage2/D7-shape     "" high
RUN_TESTS=1 SCHEMA=$P/schemas/findings.json TIMEOUT=2700 $P/run-task.sh cursor $O/stage2/D8-invariants/task.md $O/stage2/D8-invariants grok-4.7-xhigh
```
Drop `RUN_TESTS=1` for any CLI that failed probe 0.4. Cursor: if Grok's output is thin
(< 6 findings, or evidence without line numbers) rerun on `claude-opus-5-thinking-high`.

## 2.4 Failure handling

| Symptom | Action |
|---|---|
| `parsed=1`, stdout has prose + JSON | fix by hand: extract the JSON into `result.json`, note it in `meta.txt` |
| timeout at 45 min | split the task's mandates into two task files, rerun both |
| `DIRTY_TREE` | `git checkout -- <files>`, discard the run, rerun with `RUN_TESTS` unset |
| empty `findings` with confident coverage_notes | accept; record "checked, clean" for that area in stage 4 |
| Cursor/agy auth error | `agent status` / `agy -p "/permissions"`; re-login; rerun |

## 2.5 Merge (lead, 30 min) — no merge agent

```bash
python3 - <<'EOF'
import json, glob, pathlib
rows = []
for f in sorted(glob.glob('/home/mshik/GuildOS/archive/audit-2026-09-30/stage2/*/result.json')):
    d = json.load(open(f)); src = pathlib.Path(f).parent.name
    for x in d['findings']: rows.append({**x, 'src': src})
rows.sort(key=lambda r: (r['severity'], r['subsystem'], r['title']))
json.dump(rows, open('/home/mshik/GuildOS/archive/audit-2026-09-30/stage2/all-findings.json', 'w'), indent=1)
for r in rows: print(f"{r['severity']} {r['confidence']:<11} {r['src']:<14} {r['subsystem']:<12} {r['title'][:90]}")
EOF
```

Then in the lead session: group rows by root cause (same file+symbol or same mechanism),
keep the best-evidenced one as primary, list the others as `also_reported_by`, and assign
`F-001…` in order P0 → P4. Add the lead's own confirmed findings from `Analysis.md` §5 and
the salvaged tenant findings from §6 into the same pool (they need stage 3 too unless the
lead already traced them). Write the merged list to `stage2/merged.json` with fields
`{id, primary, also_reported_by:[src...], lead_note}`.

## Done when

Eight `result.json` files parse (or documented substitutes), `merged.json` exists with IDs.

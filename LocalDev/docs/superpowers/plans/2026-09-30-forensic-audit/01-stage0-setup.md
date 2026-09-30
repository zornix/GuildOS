# Stage 0 — setup and probes (20 min)

Purpose: make sure every CLI can do what stages 1–3 assume, before spending real tokens.

## 0.1 Branch and folders

```bash
cd /home/mshik/GuildOS && git switch -c audit/forensic-2026-09-30
mkdir -p archive/audit-2026-09-30/{stage1,stage2,stage3}
git check-ignore -q archive/audit-2026-09-30 && echo ignored   # must print "ignored"
```

## 0.2 Regenerate prompts (only if the plan folder was copied without `tasks/`)

```bash
python3 LocalDev/docs/superpowers/plans/2026-09-30-forensic-audit/extract-prompts.py
```
Expect `wrote tasks/ctx.md … and 16 finder files`, no `WARN` lines. Source script path is
hard-coded in `extract-prompts.py`; if that session dir is gone, the `tasks/` copies in this
folder are the source of truth — do not regenerate.

## 0.3 Runner smoke test (already passed 2026-09-30, repeat after any CLI update)

```bash
P=LocalDev/docs/superpowers/plans/2026-09-30-forensic-audit
printf 'GOAL: Count route handlers in one file. | SCOPE: read only /home/mshik/GuildOS/LocalDev/api/cron/api/cron.py | CONSTRAINTS: report only, no edits | OUTPUT: JSON {"count": n, "paths": [...]}\n' > /tmp/smoke.md
printf '{"type":"object","properties":{"count":{"type":"integer"},"paths":{"type":"array","items":{"type":"string"}}},"required":["count","paths"],"additionalProperties":false}' > /tmp/smoke-schema.json
SCHEMA=/tmp/smoke-schema.json TIMEOUT=240 $P/run-task.sh codex  /tmp/smoke.md /tmp/rt-codex  "" low
SCHEMA=/tmp/smoke-schema.json TIMEOUT=240 $P/run-task.sh agy    /tmp/smoke.md /tmp/rt-agy    "Gemini 3.6 Flash (Low)"
SCHEMA=/tmp/smoke-schema.json TIMEOUT=240 $P/run-task.sh cursor /tmp/smoke.md /tmp/rt-cursor grok-4.7-low
```
Pass = each `result.json` is `{"count":2,"paths":["/process-fines","/drain-outbox"]}` and
`meta.txt` says `parsed=0` with no `DIRTY_TREE`.

## 0.4 Test-run probe (decides how stage 2/3 tasks are launched)

Ask each CLI, with `RUN_TESTS=1`, to run one small test file and report the pytest summary
line. Task file:

```
GOAL: Confirm you can run one backend test file. | SCOPE: /home/mshik/GuildOS/LocalDev | CONSTRAINTS: do not edit any file; run exactly this command and nothing else that writes: cd /home/mshik/GuildOS/LocalDev && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/rbac/test_policy.py | OUTPUT: JSON {"ran": true|false, "summary": "<last pytest line>", "blocked_by": "<sandbox message or empty>"}
```

```bash
printf '{"type":"object","properties":{"ran":{"type":"boolean"},"summary":{"type":"string"},"blocked_by":{"type":"string"}},"required":["ran","summary","blocked_by"],"additionalProperties":false}' > /tmp/probe-schema.json
RUN_TESTS=1 SCHEMA=/tmp/probe-schema.json TIMEOUT=600 $P/run-task.sh codex  /tmp/probe.md /tmp/pr-codex  "" low
RUN_TESTS=1 SCHEMA=/tmp/probe-schema.json TIMEOUT=600 $P/run-task.sh agy    /tmp/probe.md /tmp/pr-agy    "Gemini 3.6 Flash (Low)"
RUN_TESTS=1 SCHEMA=/tmp/probe-schema.json TIMEOUT=600 $P/run-task.sh cursor /tmp/probe.md /tmp/pr-cursor grok-4.7-low
```

Record the outcome in the table below (edit this file). If a CLI cannot run tests, its stage
2/3 tasks still run, read-only, and the lead runs any single test file the agent asks for in
`coverage_notes`.

| CLI | ran? | blocked_by | flags that worked |
|---|---|---|---|
| codex | yes (2026-09-30, 8 passed) | — | `-s workspace-write -c sandbox_workspace_write.network_access=true` |
| agy | yes (2026-09-30, 8 passed) | — | `--dangerously-skip-permissions --sandbox --add-dir` |
| cursor | yes (2026-09-30, 8 passed) | — | `--force --sandbox enabled --trust` |

All three left the tree clean (`git status` unchanged). So stage 2/3 tasks may all use `RUN_TESTS=1`.

Watch for `DIRTY_TREE` in `meta.txt`. `.pytest_cache`/`__pycache__` are ignored by the
runner; anything else means the CLI edited files → revert and mark that CLI read-only.

## 0.5 Cost sanity

Note token usage from each probe (`stdout.txt`: Codex prints `tokens used`; agy and Cursor
JSON carry `usage`). Rough budget for the whole audit: stage 1 ≈ 6 × 100k tokens on Flash;
stage 2 ≈ 8 × 300k–1M; stage 3 ≈ 20 × 60k. If any single dig exceeds 45 min, the runner
kills it; split that mandate in two and rerun.

## Done when

- 0.3 passes on all three CLIs.
- 0.4 table filled in.
- Plan folder committed: `docs(audit): add forensic audit orchestration plan`.

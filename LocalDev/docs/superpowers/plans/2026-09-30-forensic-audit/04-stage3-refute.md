# Stage 3 — refute: adversarial verification on a different CLI (45 min, parallel)

Purpose: nothing reaches the report as P0/P1 on one model's word. Each such finding is
handed to a *different* vendor with the instruction "assume this is wrong".

## 3.1 Which findings

- Every P0 and P1 → **refute** lens, plus a second **reproduce** lens on the third CLI.
- Every P2 with confidence `confirmed` → refute lens.
- P2 `likely`/`speculative`, P3, P4 → no run; the lead decides from the evidence (downgrade
  to "suspected" in the report if the cited lines do not show it).

Rotation (finder → refuter → reproducer):

| Found by | Refute on | Reproduce (P0 only) on |
|---|---|---|
| Cursor (D1, D2, D8) | Codex `high` | agy `"Gemini 3.1 Pro (High)"` |
| Codex (D3, D4, D7) | agy `"Gemini 3.1 Pro (High)"` | Cursor `grok-4.7-xhigh` |
| agy (D5, D6) | Cursor `grok-4.7-xhigh` | Codex `high` |
| lead session (Analysis.md §5/§6) | Codex `high` | Cursor `grok-4.7-xhigh` |

## 3.2 Task file per finding

`stage3/<ID>-refute/task.md` = `tasks/ctx.md` + this block (fill from `merged.json`):

```
YOU ARE THE REFUTER. Another auditor reported the finding below. Assume it is WRONG and try to prove that: find the guard, constraint, trigger, test, or call-site fact that prevents it. Read every cited file in full, follow the call chain route → dependency → service → RPC body (migrations/) → triggers → response. If a test file covers this path, run it ONCE with: cd /home/mshik/GuildOS/LocalDev && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q <file>. Then give a verdict: confirmed (you could not refute it and the evidence is sound), refuted (name the exact guard), downgraded or upgraded (severity wrong — say why). Correct any wrong path:line in the original. Reply ONLY with the JSON schema you were given.

FINDING <ID> (<severity>, <confidence>, from <src>):
<the finding object, pretty-printed JSON>
```

Reproduce lens (P0 only), `stage3/<ID>-repro/task.md`, same header but:

```
YOU ARE THE REPRODUCER. Write the exact HTTP request sequence (method, path, headers, body) or RPC calls, with the roles/chapters of each actor, that triggers the finding below, starting from a fresh chapter. Say what the database looks like after each step. Do not execute against any database; reading code and running ONE existing test file is allowed. If you cannot construct the sequence, say which guard stops you (that is a refutation).
```

Build all task files with a short Python loop over `merged.json`; launch all runs in one turn
with `SCHEMA=$P/schemas/verdict.json RUN_TESTS=1 TIMEOUT=900`.

## 3.3 Decide (lead)

| Verdicts | Result |
|---|---|
| refute = confirmed (and repro built a sequence, if run) | keep; confidence `confirmed` |
| refute = confirmed, repro could not build a sequence | keep; confidence `likely`; note the gap |
| refute = refuted | lead reads the named guard; if real → drop (log in `stage3/dropped.md` with the guard); if the refuter is wrong → keep as `likely`, note the dispute |
| downgraded / upgraded | lead reads the cited lines and picks the severity; never average |

For every kept P0 and P1 the lead opens the cited lines in the session and confirms them by
eye. This is the one non-negotiable Claude cost.

Write the final state to `stage3/verified.json`: `{id, status: kept|dropped|disputed,
severity, confidence, verdicts:[…], lead_note}`.

## 3.4 Gap check (lead, 15 min, no agents)

Walk the brief's checklist (the CHECKLIST in the old workflow script, or §5 of the pasted
brief) against `verified.json` + the diggers' `coverage_notes`. Any required area with no
finding **and** no "checked, clean" note gets one targeted run (write a 10-line mandate naming
files and questions; send to the CLI that did not cover that area). Cap: 4 gap runs.

## Done when

`verified.json` exists; every P0/P1 has ≥1 external verdict and a lead eye-check; gap runs
merged back in with new IDs.

#!/usr/bin/env bash
# Cross-vendor read-only review of one stream's worktree.
#   review-stream.sh <id> <plan-file> <codex|cursor|agy> [model] [effort]
set -u
# Copied from the orchestrator scratchpad 2026-10-05. Usage: review-stream.sh <id> <plan.md> <codex|cursor|agy> [model] [effort]
id=$1; plan=$2; cli=$3; model=${4:-}; effort=${5:-}
WT=/home/mshik/GuildOS-wt/audit-$id
PL=$WT/LocalDev/docs/superpowers/plans/2026-10-05-audit-remediation
OUT=/home/mshik/GuildOS/archive/audit-remediation-2026-10/$id/review
mkdir -p "$OUT"
git -C "$WT" add -N . 2>/dev/null   # make untracked files visible to diff (intent-to-add, no content staged)
git -C "$WT" diff main --stat > "$OUT/diff-stat.txt"
git -C "$WT" diff main -- . ':(exclude)*package-lock.json' > "$OUT/diff.patch"
git -C "$WT" reset -q 2>/dev/null   # undo intent-to-add
size=$(wc -c < "$OUT/diff.patch")
{
  echo "YOU ARE THE REVIEWER of one stream of a remediation. Another vendor's agent implemented the plan below in a git worktree at $WT (branch vs main). ASSUME THE WORK IS WRONG and try to prove it: find the input that breaks it, the guard that is missing, the lock taken in the wrong order, the test that proves nothing (passes with the fix reverted), the migration that is not re-runnable or that changes a function signature or return shape, the error swallowed, the row leaked across chapters, the behaviour the plan asked for that was not done, and anything touched outside the plan's allowed files. Read every changed file in full in the worktree ($WT/LocalDev), and for each replaced DB function compare it against its live predecessor named in $PL/fn-index.txt. You may run ONE existing test file with: cd $WT/LocalDev && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q <file>. Do not modify any file."
  echo
  echo "Report each problem as a finding (severity P0 = money/security/data loss, P1 = wrong behaviour, P2 = missing guard or weak test, P3 = style). 'files' are paths relative to LocalDev/. Put plan steps that were skipped or done differently under 'extra'. Say in coverage_notes what you read and what you ran. Reply ONLY with JSON matching the schema."
  echo
  echo "===== THE PLAN ($plan) ====="; cat "$PL/$plan"
  echo; echo "===== RULES (00-README.md, 'Rules for every agent' and 'Contracts') ====="
  sed -n '/^## Rules for every agent/,/^## What to hand back/p' "$PL/00-README.md"
  sed -n '/^## Contracts between streams/,/^## Decisions/p' "$PL/00-README.md"
  echo; echo "===== DIFF STAT ====="; cat "$OUT/diff-stat.txt"
  # cursor passes the prompt as one argv string, so keep it small: it reads the diff itself.
  if [ "$cli" != cursor ] && [ "$size" -lt 200000 ]; then echo; echo "===== FULL DIFF vs main ====="; cat "$OUT/diff.patch";
  else echo; echo "(diff is $size bytes; run: git -C $WT diff main -- <path> per file)"; fi
} > "$OUT/task.md"
SCHEMA=/home/mshik/GuildOS/LocalDev/docs/superpowers/plans/2026-09-30-forensic-audit/schemas/findings.json \
WORKDIR=$WT/LocalDev RUN_TESTS=1 TIMEOUT=${TIMEOUT:-2700} \
  bash /home/mshik/GuildOS/LocalDev/docs/superpowers/plans/2026-09-30-forensic-audit/run-task.sh "$cli" "$OUT/task.md" "$OUT" "$model" "$effort"

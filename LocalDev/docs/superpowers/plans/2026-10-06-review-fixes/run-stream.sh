#!/usr/bin/env bash
# Set up the worktree for one review-fix stream and run its Codex (gpt-6.1-sol) agent headless.
#
#   run-stream.sh <stream-id>            e.g. run-stream.sh 03
#   SETUP_ONLY=1 run-stream.sh 03        create the worktree, print the prompt, do not launch
#   TIMEOUT=5400 run-stream.sh 03        outer timeout in seconds (default 90 min)
#   EXTRA_FILE=f.txt run-stream.sh 03    append carry-over lines to the prompt
#   FIXUP_FILE=f.txt run-stream.sh 03    re-run in the existing worktree with ONLY that prompt
#
# Logs and the agent's final report go to $REPO/archive/review-fixes-2026-10/<stream>/.
# Opus reviews are dispatched by the orchestrator with the Agent tool, not this script.
set -euo pipefail

REPO=/home/mshik/GuildOS
PLANS_REL=LocalDev/docs/superpowers/plans/2026-10-06-review-fixes
id=${1:?stream id}

case $id in
  01) plan=01-frontend-shell.md;    branch=fix/review-01-frontend ;;
  02) plan=02-authority.md;         branch=fix/review-02-authority ;;
  03) plan=03-treasury.md;          branch=fix/review-03-treasury ;;
  04) plan=04-events-platform.md;   branch=fix/review-04-events-platform ;;
  05) plan=05-db-guards.md;         branch=fix/review-05-db-guards ;;
  06) plan=06-ops-ci.md;            branch=fix/review-06-ops-ci ;;
  07) plan=07-fines-attendance.md;  branch=fix/review-07-fines-attendance ;;
  08) plan=08-balance-readers.md;   branch=fix/review-08-balance-readers ;;
  09) plan=09-outbox.md;            branch=fix/review-09-outbox ;;
  10) plan=10-error-mapping.md;     branch=fix/review-10-errors ;;
  11) plan=11-docs.md;              branch=fix/review-11-docs ;;
  *) echo "unknown stream $id" >&2; exit 2 ;;
esac

WT=/home/mshik/GuildOS-wt/review-$id
OUT=$REPO/archive/review-fixes-2026-10/$id
T=${TIMEOUT:-5400}
mkdir -p "$OUT" "$(dirname "$WT")"

if [ ! -d "$WT" ]; then
  git -C "$REPO" worktree add -b "$branch" "$WT" main
  cp "$REPO/LocalDev/.env" "$WT/LocalDev/.env"
fi
[ -f "$WT/$PLANS_REL/$plan" ] || { echo "plan missing in worktree: commit the plans to main first" >&2; exit 1; }
if [ "$id" = 01 ] && [ ! -d "$WT/LocalDev/greekos/node_modules" ]; then
  (cd "$WT/LocalDev/greekos" && npm ci --silent)
fi

if [ -n "${FIXUP_FILE:-}" ]; then
  prompt="$(cat "$FIXUP_FILE")"
  report=report-fixup.txt
else
  prompt="GOAL: implement one stream of the GuildOS review fixes, test first, exactly as planned.
SCOPE: you are in a git worktree of the repo, on branch $branch. Your plan is $PLANS_REL/$plan.
READ FIRST, in full: $PLANS_REL/00-README.md (sections 'Rules for every agent', 'Decisions', 'Contracts between streams', 'What to hand back'), then your plan, then your sections of LocalDev/docs/audit/remediation-review.md.
CONSTRAINTS: change only the files your plan allows. Do NOT commit, stage, or run any state-changing git command. No scratch files in the repo. Never print values from .env. Never touch Prod/ or anything but the demo database. Run commands from LocalDev/ unless the plan says otherwise.
VERIFICATION: every fix starts with a test that fails first; run the test folders your plan names and paste the final count line.
OUTPUT: finish with the report block from 'What to hand back', as plain text, and nothing after it."
  [ -n "${EXTRA_FILE:-}" ] && prompt="$prompt
CARRY-OVERS FROM EARLIER STREAMS (binding):
$(cat "$EXTRA_FILE")"
  report=report.txt
fi

if [ "${SETUP_ONLY:-0}" = 1 ]; then printf '%s\n' "$prompt"; echo "worktree: $WT"; exit 0; fi

start=$(date +%s)
timeout "$T" codex exec -s workspace-write -c sandbox_workspace_write.network_access=true \
  --skip-git-repo-check --ephemeral -C "$WT" -m gpt-6.1-sol -c model_reasoning_effort=medium \
  -o "$OUT/$report" "$prompt" </dev/null >"$OUT/stdout.txt" 2>"$OUT/stderr.txt" && rc=0 || rc=$?

git -C "$WT" status --short > "$OUT/status.txt"
echo "stream=$id rc=$rc secs=$(( $(date +%s) - start )) changed=$(wc -l < "$OUT/status.txt")" | tee "$OUT/meta.txt"
[ -s "$OUT/$report" ] || { echo "EMPTY REPORT: treat as failure" >&2; exit 1; }
exit "$rc"

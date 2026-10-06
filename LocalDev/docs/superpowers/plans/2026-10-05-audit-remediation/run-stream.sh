#!/usr/bin/env bash
# Set up the worktree for one external-CLI stream and run its agent headless.
#
#   run-stream.sh <stream-id>            e.g. run-stream.sh 02
#   SETUP_ONLY=1 run-stream.sh 02        create the worktree, print the prompt, do not launch
#   TIMEOUT=5400 run-stream.sh 08        outer timeout in seconds (default 90 min)
#   EXTRA_FILE=f.txt run-stream.sh 08    append the stream's carry-over lines to the prompt
#
# Logs and the agent's final report go to $REPO/archive/audit-remediation-2026-10/<stream>/.
# Launch several with run_in_background; never run two streams of different waves together.
# Cursor/Grok streams moved to Codex (Grok out of usage, 2026-10-05).
# Claude streams (01, 03, 05, 06, 15) are dispatched with the Agent tool, not this script.
set -euo pipefail

REPO=/home/mshik/GuildOS
PLANS_REL=LocalDev/docs/superpowers/plans/2026-10-05-audit-remediation
id=${1:?stream id}

case $id in
  02) plan=02-authority.md;                 branch=fix/audit-02-authority;        cli=cursor ;;
  04) plan=04-db-guards.md;                 branch=fix/audit-04-db-guards;        cli=cursor ;;
  07) plan=07-ci-tooling.md;                branch=fix/audit-07-ci-tooling;       cli=agy ;;
  08) plan=08-standing-balance-readers.md;  branch=fix/audit-08-standing-readers; cli=codex ;;
  09) plan=09-fines-pipeline.md;            branch=fix/audit-09-fines-pipeline;   cli=codex ;;
  10) plan=10-check-in.md;                  branch=fix/audit-10-check-in;         cli=codex ;;
  11) plan=11-events-tasks.md;              branch=fix/audit-11-events-tasks;     cli=codex ;;
  12) plan=12-outbox-delivery.md;           branch=fix/audit-12-outbox-delivery;  cli=codex ;;
  13) plan=13-auth-config-onboarding.md;    branch=fix/audit-13-auth-config;      cli=codex ;;
  14) plan=14-outbox-ops.md;                branch=fix/audit-14-outbox-ops;       cli=codex ;;
  16) plan=16-sweep.md;                     branch=fix/audit-16-sweep;            cli=agy ;;
  17) plan=17-docs.md;                      branch=fix/audit-17-docs;             cli=agy ;;
  *) echo "stream $id is not an external-CLI stream" >&2; exit 2 ;;
esac

WT=/home/mshik/GuildOS-wt/audit-$id
OUT=$REPO/archive/audit-remediation-2026-10/$id
T=${TIMEOUT:-5400}
mkdir -p "$OUT" "$(dirname "$WT")"

if [ ! -d "$WT" ]; then
  git -C "$REPO" worktree add -b "$branch" "$WT" main
  cp "$REPO/LocalDev/.env" "$WT/LocalDev/.env"
fi
[ -f "$WT/$PLANS_REL/$plan" ] || { echo "plan missing in worktree: commit the plans to main first" >&2; exit 1; }

prompt="GOAL: implement one stream of the GreekOS audit remediation, test first, exactly as planned.
SCOPE: you are in a git worktree of the repo, on branch $branch. Your plan is $PLANS_REL/$plan.
READ FIRST, in full: $PLANS_REL/00-README.md (sections 'Rules for every agent', 'Contracts between streams', 'Decisions', 'What to hand back'), then your plan, then the finding cards it names in LocalDev/docs/audit/2026-09-30-forensic-audit.md.
CONSTRAINTS: change only the files your plan allows. Do NOT commit, stage, or run any state-changing git command. No scratch files in the repo. Never print values from .env. Never touch Prod/ or the production database. Run commands from LocalDev/ unless the plan says otherwise.
VERIFICATION: every fix starts with a test that fails first; run the test folders your plan names and paste the final count line.
OUTPUT: finish with the report block from 'What to hand back', as plain text, and nothing after it."

[ -n "${EXTRA_FILE:-}" ] && prompt="$prompt
CARRY-OVERS FROM EARLIER STREAMS (binding):
$(cat "$EXTRA_FILE")"

if [ "${SETUP_ONLY:-0}" = 1 ]; then printf '%s\n' "$prompt"; echo "worktree: $WT"; exit 0; fi

start=$(date +%s)
case $cli in
  codex)
    timeout "$T" codex exec -s workspace-write -c sandbox_workspace_write.network_access=true \
      --skip-git-repo-check --ephemeral -C "$WT" -m gpt-6.1-sol -c model_reasoning_effort=medium \
      -o "$OUT/report.txt" "$prompt" </dev/null >"$OUT/stdout.txt" 2>"$OUT/stderr.txt" && rc=0 || rc=$? ;;
  cursor)
    timeout "$T" agent -p --trust --force --workspace "$WT" --model grok-4.7-medium \
      "$prompt" </dev/null >"$OUT/report.txt" 2>"$OUT/stderr.txt" && rc=0 || rc=$? ;;
  agy)
    (cd "$WT" && timeout "$T" agy -p "$prompt" --model "Gemini 3.8 Flash (Medium)" \
      --dangerously-skip-permissions --print-timeout "$((T/60))m") \
      </dev/null >"$OUT/report.txt" 2>"$OUT/stderr.txt" && rc=0 || rc=$? ;;
esac

git -C "$WT" status --short > "$OUT/status.txt"
echo "stream=$id cli=$cli rc=$rc secs=$(( $(date +%s) - start )) changed=$(wc -l < "$OUT/status.txt")" | tee "$OUT/meta.txt"
[ -s "$OUT/report.txt" ] || { echo "EMPTY REPORT: treat as failure" >&2; exit 1; }
exit "$rc"

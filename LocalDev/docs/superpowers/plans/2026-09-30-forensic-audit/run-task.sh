#!/usr/bin/env bash
# Run one audit task on an external CLI, headless, and normalise the result.
#
#   run-task.sh <codex|agy|cursor> <task-file> <out-dir> [model] [effort]
#
# Env:  SCHEMA=<json-schema file>  force a JSON answer (codex/agy natively; cursor via fence)
#       RUN_TESTS=1                allow shell + network so the agent can run ONE test file
#       TIMEOUT=<sec>              outer timeout (default 2700 = 45 min)
#       WORKDIR=<dir>              default /home/mshik/GuildOS/LocalDev
# Writes <out-dir>/{stdout.txt,stderr.txt,result.json,meta.txt}. Exit 0 only if result.json parsed.
# Launch several in parallel with `run_in_background` Bash calls; never inline long prompts.
set -u
cli=$1; task=$2; out=$3; model=${4:-}; effort=${5:-}
L=${WORKDIR:-/home/mshik/GuildOS/LocalDev}
T=${TIMEOUT:-2700}
mkdir -p "$out"
prompt=$(cat "$task")
if [ -n "${SCHEMA:-}" ] && [ "$cli" = cursor ]; then
  prompt="$prompt

FINAL ANSWER FORMAT: your last message must be exactly one \`\`\`json fenced block that validates against this JSON schema, with no text after it:
$(cat "$SCHEMA")"
fi
before=$(git -C "$L" status --porcelain | grep -v '__pycache__\|\.pytest_cache' | sort)
start=$(date +%s)
case $cli in
  codex)
    a=(exec --skip-git-repo-check --ephemeral -C "$L" -o "$out/last.txt")
    [ -n "${SCHEMA:-}" ] && a+=(--output-schema "$SCHEMA")
    if [ "${RUN_TESTS:-0}" = 1 ]; then a+=(-s workspace-write -c sandbox_workspace_write.network_access=true); else a+=(-s read-only); fi
    [ -n "$model" ] && a+=(-m "$model")
    [ -n "$effort" ] && a+=(-c "model_reasoning_effort=$effort")
    timeout "$T" codex "${a[@]}" "$prompt" </dev/null >"$out/stdout.txt" 2>"$out/stderr.txt"; rc=$? ;;
  agy)
    a=(-p "$prompt" --output-format json --add-dir "$L" --sandbox --print-timeout "$((T/60))m")
    [ -n "${SCHEMA:-}" ] && a+=(--json-schema "$SCHEMA")
    [ "${RUN_TESTS:-0}" = 1 ] && a+=(--dangerously-skip-permissions)
    [ -n "$model" ] && a+=(--model "$model")
    [ -n "$effort" ] && a+=(--effort "$effort")
    (cd "$L" && timeout "$T" agy "${a[@]}") </dev/null >"$out/stdout.txt" 2>"$out/stderr.txt"; rc=$? ;;
  cursor)
    a=(-p --trust --workspace "$L" --output-format json)
    if [ "${RUN_TESTS:-0}" = 1 ]; then a+=(--force --sandbox enabled); fi
    [ -n "$model" ] && a+=(--model "$model")
    timeout "$T" agent "${a[@]}" "$prompt" </dev/null >"$out/stdout.txt" 2>"$out/stderr.txt"; rc=$? ;;
  *) echo "unknown cli $cli" >&2; exit 2 ;;
esac
secs=$(( $(date +%s) - start ))
after=$(git -C "$L" status --porcelain | grep -v '__pycache__\|\.pytest_cache' | sort)
dirty=""; [ "$before" != "$after" ] && dirty="DIRTY_TREE"
# normalise the answer into result.json
python3 - "$cli" "$out" <<'PY'
import json, re, sys, pathlib
cli, out = sys.argv[1], pathlib.Path(sys.argv[2])
def fence(t):
    m = re.findall(r"```json\s*(.*?)```", t, re.S)
    if m: return m[-1]
    i, j = t.find("{"), t.rfind("}")
    return t[i:j+1] if i >= 0 and j > i else t
try:
    if cli == "codex":
        raw = (out / "last.txt").read_text()
    elif cli == "agy":
        j = json.loads((out / "stdout.txt").read_text())
        raw = j.get("structured_output") or j.get("response") or ""
        if isinstance(raw, (dict, list)): raw = json.dumps(raw)
    else:
        lines = [l for l in (out / "stdout.txt").read_text().splitlines() if l.strip()]
        j = json.loads(lines[-1]) if lines else {}
        raw = j.get("result") or ""
    obj = json.loads(fence(raw))
    (out / "result.json").write_text(json.dumps(obj, indent=2))
    print("PARSED")
except Exception as e:
    print(f"NO_RESULT {type(e).__name__}: {e}")
    sys.exit(1)
PY
prc=$?
echo "cli=$cli model=$model effort=$effort rc=$rc secs=$secs parsed=$prc $dirty" | tee "$out/meta.txt"
[ -n "$dirty" ] && { echo "$after" > "$out/dirty.txt"; echo "WARNING: working tree changed during the run; inspect $out/dirty.txt and revert" >&2; }
exit $prc

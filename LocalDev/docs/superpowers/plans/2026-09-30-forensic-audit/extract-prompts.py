#!/usr/bin/env python3
"""Pull the shared context block + 16 finder mandates out of the stopped Claude
workflow script into tasks/ctx.md and tasks/finder-<key>.md, with paths
substituted and the rules paragraph replaced by the current rules.

Usage: python3 extract-prompts.py [path-to-workflow.js]
"""
import re, sys, pathlib

HERE = pathlib.Path(__file__).resolve().parent
SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
    "/home/mshik/.claude/projects/-home-mshik-GuildOS-LocalDev/5fe70d10-c767-4ae6-a390-9434086df14a/workflows/scripts/greekos-forensic-audit-wf_4c57fbb5-61b.js")
R = "/home/mshik/GuildOS"
L = f"{R}/LocalDev"
LOG = f"{R}/Analysis.md section 1"

RULES = (
    "HARD RULES: Do NOT modify, create, or delete any file under " + R + " (the lead checks "
    "`git status` after every run; a dirty tree voids your output). Never run migrations, seeds, "
    "'npm run dev', deployments, or the full pytest suite. You MAY run grep/rg/cat/sed/wc/find/git/ls, "
    "'python3 -c', 'npx tsc --noEmit' inside " + L + "/greekos, node:test via 'npm test' inside "
    + L + "/greekos, and pytest on ONE test file at a time, always as "
    "'cd " + L + " && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q <one file>'. "
    "If a command is blocked by your sandbox, say so in coverage_notes and continue by reading. "
    "Never print secret VALUES from " + L + "/.env (variable NAMES are fine: grep -oE '^[A-Z_]+=' .env). "
    "Baseline results (backend 1030 tests pass, frontend lint/tests/build pass) are in " + R + "/Analysis.md; "
    "read that file first — it also holds the lead's confirmed findings (section 5) so you can go deeper instead of repeating them."
)

def subst(t):
    t = t.replace("${R}", R).replace("${L}", L).replace("${LOG}", LOG)
    return t

s = SRC.read_text()
ctx = re.search(r"const CTX = `(.*?)`\n", s, re.S).group(1)
ctx = re.sub(r"HARD RULES:.*?\n\n", RULES + "\n\n", ctx, count=1, flags=re.S)
ctx = ctx.replace("with 15 other auditors' outputs", "with other auditors' outputs")
ctx = subst(ctx)
(HERE / "tasks/ctx.md").write_text(ctx.strip() + "\n")

block = s[s.index("const FINDERS = ["):s.index("const raw = await parallel")]
n = 0
for m in re.finditer(r"key: '([^']+)',\s*label: '([^']+)',\s*prompt: `(.*?)`,?\s*\}", block, re.S):
    key, _, prompt = m.groups()
    prompt = subst(prompt)
    # external CLIs have no Claude skills
    prompt = re.sub(r"First load the 'ponytail:ponytail-audit' skill[^.]*\.\s*", "", prompt)
    left = re.findall(r"\$\{[^}]+\}", prompt)
    if left: print(f"WARN {key}: unsubstituted {set(left)}")
    (HERE / f"tasks/finder-{key}.md").write_text(prompt.strip() + "\n")
    n += 1
print(f"wrote tasks/ctx.md ({len(ctx)} chars) and {n} finder files")

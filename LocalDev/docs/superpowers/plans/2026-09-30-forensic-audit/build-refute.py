#!/usr/bin/env python3
"""Stage 3 prep: from stage2/merged.json build one refute task per P0/P1/P2-confirmed
finding (and a reproduce task per P0) on a CLI different from the finder, and print the
launch commands.

merged.json rows: {id, primary: <finding obj with src>, also_reported_by: [...], lead_note}
"""
import json, pathlib
A = pathlib.Path('/home/mshik/GuildOS/archive/audit-2026-09-30')
P = pathlib.Path('/home/mshik/GuildOS/LocalDev/docs/superpowers/plans/2026-09-30-forensic-audit')
ctx = (P / 'tasks/ctx.md').read_text()
CLI_OF = {'D1-security': 'cursor', 'D2-money': 'cursor', 'D8-invariants': 'cursor',
          'D3-workflows': 'codex', 'D4-comms-ops': 'codex', 'D7-shape': 'codex',
          'D5-frontend': 'agy', 'D6-tests': 'agy', 'lead': 'lead'}
REFUTE = {'cursor': 'codex', 'codex': 'agy', 'agy': 'cursor', 'lead': 'codex'}
REPRO = {'cursor': 'agy', 'codex': 'cursor', 'agy': 'codex', 'lead': 'cursor'}
MODEL = {'codex': ('', 'high'), 'agy': ('Gemini 3.1 Pro (High)', ''), 'cursor': ('grok-4.7-xhigh', '')}
REFUTE_TXT = """YOU ARE THE REFUTER. Another auditor reported the finding below. Assume it is WRONG and try to prove that: find the guard, constraint, trigger, test, or call-site fact that prevents it. Read every cited file in full, follow the call chain route -> dependency -> service -> RPC body (migrations/) -> triggers -> response. If a test file covers this path, run it ONCE with: cd /home/mshik/GuildOS/LocalDev && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q <file>. Then give a verdict: confirmed (you could not refute it and the evidence is sound), refuted (name the exact guard), downgraded or upgraded (severity wrong per the rubric in the context - say why). Correct any wrong path:line in the original. Reply ONLY with the JSON schema you were given."""
REPRO_TXT = """YOU ARE THE REPRODUCER. Write the exact HTTP request sequence (method, path, headers, body) or RPC calls, with the roles/chapters of each actor, that triggers the finding below, starting from a fresh chapter. Say what the database looks like after each step. Do not execute against any database; reading code and running ONE existing test file is allowed. If you cannot construct the sequence, say which guard stops you (that is a refutation). Reply ONLY with the JSON schema you were given."""
cmds = []
for row in json.load(open(A / 'stage2/merged.json')):
    f = row['primary']; sev = f['severity']; conf = f['confidence']
    if not (sev in ('P0', 'P1') or (sev == 'P2' and conf == 'confirmed')): continue
    finder = CLI_OF[f['src']]
    lenses = [('refute', REFUTE[finder], REFUTE_TXT)]
    if sev == 'P0': lenses.append(('repro', REPRO[finder], REPRO_TXT))
    body = json.dumps({k: v for k, v in f.items() if k not in ('idx',)}, indent=1)
    for lens, cli, txt in lenses:
        d = A / f"stage3/{row['id']}-{lens}"; d.mkdir(parents=True, exist_ok=True)
        (d / 'task.md').write_text(f"{ctx}\n\n{txt}\n\nFINDING {row['id']} ({sev}, {conf}, from {f['src']}):\n{body}\n")
        m, e = MODEL[cli]
        cmds.append(f'RUN_TESTS=1 SCHEMA={P}/schemas/verdict.json TIMEOUT=900 {P}/run-task.sh {cli} {d}/task.md {d} "{m}" {e}')
(A / 'stage3/launch.txt').write_text('\n'.join(cmds) + '\n')
print(len(cmds), 'refute/repro tasks written; commands in stage3/launch.txt')

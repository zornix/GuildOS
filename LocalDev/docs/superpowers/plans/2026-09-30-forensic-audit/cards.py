#!/usr/bin/env python3
"""Stage 4: render §3 finding cards + the summary tables from stage3/verified.json.
verified.json rows: merged.json group + {status, severity, confidence, verified_by, lead_note}"""
import json, pathlib, sys
A = pathlib.Path('/home/mshik/GuildOS/archive/audit-2026-09-30')
V = json.load(open(A / 'stage3/verified.json'))
EMO = {'P0': '🔴', 'P1': '🟠', 'P2': '🟡', 'P3': '🔵', 'P4': '⚪'}
SRC = {'D1-security': 'Cursor/Grok', 'D2-money': 'Cursor/Grok', 'D8-invariants': 'Cursor/Grok', 'D3-workflows': 'Codex', 'D4-comms-ops': 'Codex', 'D7-shape': 'Codex', 'D5-frontend': 'Gemini Pro', 'D6-tests': 'Gemini Pro', 'lead': 'lead session'}
def files(p): return ', '.join(f"`{x}`" for x in p['files'][:4])
def steps(s):
    s = s.strip()
    return s if len(s) < 700 else s[:700].rsplit('.', 1)[0] + '.'
out = []
kept = [g for g in V if g['status'] != 'dropped']
for sev in ('P0', 'P1', 'P2', 'P3', 'P4'):
    rows = [g for g in kept if g['severity'] == sev]
    if not rows: continue
    out.append(f"\n### {EMO[sev]} {sev} — {len(rows)} findings\n")
    out.append("| ID | Subsystem | One line | Confidence | Fix size |\n|---|---|---|---|---|")
    for g in rows:
        p = g['primary']; out.append(f"| [{g['id']}](#{g['id'].lower()}) | {p['subsystem'][:22]} | {p['title'][:90]} | {g['confidence']} | {p['refactor_scope']} |")
    out.append('')
    if sev in ('P2', 'P3', 'P4'): out.append(f"<details><summary>▸ {sev} cards ({len(rows)})</summary>\n")
    for g in rows:
        p = g['primary']
        out.append(f"<a id=\"{g['id'].lower()}\"></a>\n#### {g['id']} · {EMO[sev]} {sev} · {g['confidence']} · {p['subsystem']}\n**{p['title']}**\n")
        out.append(f"- **What happens:** {p['current_behavior'].strip()[:500]}")
        out.append(f"- **Where:** {files(p)}")
        out.append(f"- **How it goes wrong:** {steps(p['failure_scenario'])}")
        out.append(f"- **Why it matters / blast radius:** {p['why_it_matters'].strip()[:300]} — {p['blast_radius'].strip()[:200]}")
        out.append(f"- **Tests catch it?** {p['tests_detect'].strip()[:250]}")
        out.append(f"- **Fix:** {p['recommendation'].strip()[:400]} · scope: **{p['refactor_scope']}**")
        vb = ', '.join(g.get('verified_by', [])) or 'lead only'
        also = '; '.join(f"{SRC.get(a['src'], a['src'])}: {a['title'][:60]}" for a in g['also_reported_by'])
        out.append(f"- **Found by:** {SRC.get(p['src'], p['src'])} · **verified by:** {vb}" + (f" · **also reported as:** {also}" if also else ''))
        if g.get('lead_note'): out.append(f"- **Lead note:** {g['lead_note']}")
        out.append('')
    if sev in ('P2', 'P3', 'P4'): out.append('</details>\n')
(A / 'stage4/cards.md').write_text('\n'.join(out))
print(len(kept), 'cards written to stage4/cards.md')

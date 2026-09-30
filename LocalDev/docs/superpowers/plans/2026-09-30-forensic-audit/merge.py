#!/usr/bin/env python3
"""Stage 2.5: pool every dig's findings + the lead's Analysis.md findings into
stage2/all-findings.json and print one line per finding for the lead to group."""
import json, glob, pathlib
A = pathlib.Path('/home/mshik/GuildOS/archive/audit-2026-09-30')
rows = []
for f in sorted(glob.glob(str(A / 'stage2/*/result.json'))):
    src = pathlib.Path(f).parent.name
    for x in json.load(open(f))['findings']:
        rows.append({**x, 'src': src})
# lead findings (Analysis.md §5) — already traced by the lead; still go through refute
lead = json.load(open(A / 'stage2/lead-findings.json')) if (A / 'stage2/lead-findings.json').exists() else []
for x in lead: rows.append({**x, 'src': 'lead'})
order = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3, 'P4': 4}
rows.sort(key=lambda r: (order[r['severity']], r['subsystem'], r['title']))
for i, r in enumerate(rows): r['idx'] = i
json.dump(rows, open(A / 'stage2/all-findings.json', 'w'), indent=1)
for r in rows:
    print(f"{r['idx']:>3} {r['severity']} {r['confidence'][:4]} {r['src']:<14} {r['subsystem'][:18]:<18} {r['title'][:80]} | {(r['files'] or [''])[0][:60]}")
print(len(rows), 'findings pooled')

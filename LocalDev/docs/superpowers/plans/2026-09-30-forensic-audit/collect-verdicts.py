#!/usr/bin/env python3
"""Stage 3.3 helper: join merged.json with every stage3/<ID>-<lens>/result.json and print
one line per finding for the lead to decide. Writes stage3/verdicts.json."""
import json, glob, pathlib
A = pathlib.Path('/home/mshik/GuildOS/archive/audit-2026-09-30')
merged = {g['id']: g for g in json.load(open(A / 'stage2/merged.json'))}
out = {}
for f in sorted(glob.glob(str(A / 'stage3/F-*/result.json'))):
    d = pathlib.Path(f).parent.name; fid, lens = d.rsplit('-', 1)
    meta = (pathlib.Path(f).parent / 'meta.txt').read_text().split()
    cli = meta[0].split('=')[1]
    v = json.load(open(f)); v['cli'] = cli
    out.setdefault(fid, {})[lens] = v
json.dump(out, open(A / 'stage3/verdicts.json', 'w'), indent=1)
for fid, g in merged.items():
    p = g['primary']; vs = out.get(fid, {})
    line = f"{fid} {p['severity']} {p['confidence'][:4]} {p['src'][:6]:<6} {p['title'][:70]:<70}"
    for lens, v in vs.items():
        line += f" | {lens}@{v['cli']}: {v['verdict']} {v['severity']} {v['confidence'][:4]} test={v['test_run']['outcome'][:30]!r}"
    if not vs and (p['severity'] in ('P0','P1') or (p['severity']=='P2' and p['confidence']=='confirmed')): line += ' | (pending)'
    print(line)

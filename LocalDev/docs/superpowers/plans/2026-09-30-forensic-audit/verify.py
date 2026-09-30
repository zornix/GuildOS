#!/usr/bin/env python3
"""Stage 3.3: apply lead decisions to merged.json + verdicts.json → stage3/verified.json"""
import json, pathlib
A = pathlib.Path('/home/mshik/GuildOS/archive/audit-2026-09-30')
merged = json.load(open(A / 'stage2/merged.json'))
V = json.load(open(A / 'stage3/verdicts.json'))
# id: (status, severity, confidence, lead note)
D = {
 'F-001': ('kept','P3','confirmed','Refuter (Grok) downgraded P1→P3: parser is fail-closed keyword grammar, the problem is overclaiming copy and an unused AI dependency. Lead agrees.'),
 'F-009': ('kept','P2','confirmed','Refuter (Grok) downgraded P1→P2: the suite cannot see RLS, but RLS is not the runtime boundary. Lead agrees.'),
 'F-016': ('kept','P2','likely','Refuter (Codex) downgraded: PROD_PROJECT_REFS guard blocks any prod migrate today. Lead agrees; the missing checksum/dry-run remains.'),
 'F-018': ('kept','P2','likely','Refuter (Codex) downgraded: at the 300 s Vercel default the batch finishes; exhaustion needs five kills in a row. Lead agrees.'),
 'F-020': ('kept','P2','confirmed','Refuter (Codex) downgraded: offline credential-gated break-glass script, and the runbook does target prod on purpose. Session revocation gap stands.'),
 'F-032': ('kept','P2','confirmed','Refuter (Codex) downgraded: money lands on the right member; oldest-first is the documented rule. The UI still implies invoice-specific payment.'),
 'F-035': ('dropped','P4','confirmed','Refuted (Grok): all three "drift" claims were misreads of GET-vs-POST contracts and an alias field. Guard: api/events/api/events.py:239, api/tasks/services/tasks.py:160-161.'),
 'F-037': ('kept','P1','confirmed','Refuter (Gemini) upgraded P2→P0. Lead sets P1: exposure needs database read access and codes expire; still live credentials in plaintext in failed outbox rows.'),
 'F-042': ('kept','P2','confirmed','Refuter (Gemini) upgraded to P1 (READ COMMITTED double insert). Lead keeps P2: needs two simultaneous assignments of one member. Disputed.'),
 'F-048': ('kept','P2','confirmed','Refuter (Gemini) upgraded to P1 and added a real fact: the usage_events immutability trigger (0140:28-40) also blocks cascaded chapter/member deletes. Lead keeps P2: no delete feature exists yet.'),
 'F-049': ('dropped','P4','confirmed','Refuted (Grok): the strict money regex and the zero floor are specified and unit-tested behaviour (transaction.test.ts:14, 21-27).'),
 'F-050': ('kept','P2','confirmed','Refuter (Gemini) upgraded to P1. Lead keeps P2: operator retry path; stale parent send log is a display inconsistency. Disputed.'),
 'F-052': ('kept','P3','confirmed','Refuter (Grok) refuted the security implication: FakeSb tautology is real but member_id scoping plus RPC writer guards mean no tenant hole. Lead keeps it as a P3 test-quality item.'),
 'F-054': ('kept','P2','confirmed','Refuter (Gemini) upgraded to P1 and proved it with a written test. Lead keeps P2: operational, not financial or security. Disputed.'),
 'F-045': ('kept','P3','confirmed','Refuter (Codex) downgraded P2→P3: syncApi rolls back and replaces the toast on an API error; only the backendDown branch is silent. Lead agrees.'),
 'F-008': ('kept','P1','speculative','Refuter (Codex) confirmed the mechanism; D1 notes no GRANT on tables appears in the repo, so this depends on Supabase default privileges and the Data API toggle. Verify in the dashboard; revoking DML from anon/authenticated is cheap either way.'),
 'F-055': ('dropped','P4','confirmed','Refuted (Grok): verify/reallocate call BalanceEngine directly and test_v1_allocation.py:96-101 asserts the cache row; only invoice-create/void recompute is stubbed.'),
}
out = []
for g in merged:
    fid = g['id']; p = g['primary']; vs = V.get(fid, {})
    row = dict(g)
    row['verified_by'] = [f"{l}@{v['cli']}: {v['verdict']} {v['severity']}" for l, v in vs.items()]
    if fid in D:
        row['status'], row['severity'], row['confidence'], note = D[fid]
        row['lead_note'] = (g.get('lead_note','') + ' ' + note).strip()
    elif vs:
        v = vs['refute']
        row['status'] = 'kept' if v['verdict'] != 'refuted' else 'dropped'
        row['severity'] = v['severity']; row['confidence'] = v['confidence']
        if v['verdict'] not in ('confirmed',): row['lead_note'] = (g.get('lead_note','') + f" Refuter verdict {v['verdict']} → {v['severity']} accepted.").strip()
        if v.get('corrections') and v['corrections'].strip().lower() not in ('none','none.',''): row['corrections'] = v['corrections'][:600]
    else:
        row['status'] = 'kept'; row['severity'] = p['severity']; row['confidence'] = p['confidence']
        if p['severity'] in ('P0','P1') or (p['severity']=='P2' and p['confidence']=='confirmed'): row['status'] = 'pending'
    out.append(row)
order = {'P0':0,'P1':1,'P2':2,'P3':3,'P4':4}
out.sort(key=lambda r: (order[r['severity']], r['primary']['subsystem']))
json.dump(out, open(A / 'stage3/verified.json', 'w'), indent=1)
from collections import Counter
print(Counter(r['status'] for r in out)); print('kept by severity:', Counter(r['severity'] for r in out if r['status']=='kept'))
print('pending:', [r['id'] for r in out if r['status']=='pending'])

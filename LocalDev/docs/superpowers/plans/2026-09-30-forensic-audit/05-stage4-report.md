# Stage 4 — write the report (lead only, 1–2 h)

Deliverables (committed on the audit branch):

- `LocalDev/docs/audit/2026-09-30-forensic-audit.md` — the report
- `LocalDev/docs/audit/2026-09-30-findings.json` — `verified.json` plus good patterns,
  conventions and the invariant table, for tooling

## 4.1 Readability rules (the user has ADHD — these are hard requirements)

1. **Page one is the whole story.** Someone who reads only the first screen knows the state
   of the codebase, the three things to fix first, and what to trust.
2. **Every section opens with "In short:"** — one or two sentences. Detail goes under a
   `<details><summary>…</summary>` block so the skim path stays short.
3. **Fixed-shape cards for findings.** Same six labels in the same order, every time.
4. **Tables over prose.** Anything with three or more parallel items is a table.
5. **Paragraphs ≤ 3 sentences. Sentences ≤ 20 words.** No walls of text, no nested bullets
   deeper than two levels.
6. **Plain words.** Say "anyone with a login can…" before "IDOR". Expand each acronym once.
7. **Numbers in tables, not sentences.**
8. **One idea per finding.** Instances live inside the card, not as separate findings.
9. **Severity colours via emoji tag**, always the same: 🔴 P0 · 🟠 P1 · 🟡 P2 · 🔵 P3 · ⚪ P4.
10. **Links everywhere**: finding IDs link to their card; every path is a code span.

## 4.2 Report skeleton (section numbers match the brief)

```markdown
# GreekOS forensic audit — 2026-09-30

> **How to read this.** Page one (TL;DR + Top 10) is enough for a decision. Each later section
> opens with "In short". Click a ▸ to expand detail. IDs like F-007 link to a finding card.

## TL;DR
- Five bullets max. Coherent? Maintainable? Fragmented agent work? Guarantees implicit? Tests protective?
- **Trust:** … / **Distrust:** … / **Change before building on it:** …  (three one-line boxes)

## Top 10 (highest impact first)
| # | ID | 🔴 | One line | Fix size |

## 1 Executive summary        (In short + ▸ detail answering the brief's nine questions)
## 2 Architecture map          (tables from stage 1 inventories: subsystems, routes per domain,
                                DB layers, frontend files, deploy model; one dependency diagram)
## 3 Findings                  (cards, grouped P0 → P4; each group opens with a count table)
## 4 Top critical findings     (the Top 10 table again with 2-line context each)
## 5 Security                  (summary table + links to cards)
## 6 Financial / database      (summary table + links)
## 7 Test suite                (table of ≥20 representative tests: file · detects · misses · value;
                                then "highest-value missing tests" list)
## 8 Agent-generated patterns  (one card per pattern, instances inside)
## 9 Good architecture to keep (table: what · where · why not to refactor)
## 10 Weird but reasonable     (table)
## 11 Recommended conventions  (table: concern · dominant · competing · decision)
## 12 Remediation plan         (Phase 0–5; per item: prerequisites · files · must-not-change ·
                                tests first · blast radius · order)
## 13 Fix before big features  (numbered ten)
## 14 Do NOT refactor now      (short list with reason)
## 15 Final assessment         (risk split correctness/security vs maintainability in one table;
                                rewrite / targeted refactor / consolidation / conventions verdict;
                                first subsystem to work on; healthiest subsystem; the inherited-team question)
## Appendix A Invariants table (from D8: invariant · enforced at · assumed at · bypass · DB-level · tests · strength)
## Appendix B Method           (what ran where, models, what was not read — from coverage_notes)
```

### Finding card shape

```markdown
### F-007 · 🟠 P1 · confirmed · Treasury
**Approvers can verify their own payment submissions**
- **What happens:** one or two sentences, plain words.
- **Where:** `migrations/0124_…sql:124-241 (tr_verify_payment_v2)`, `api/treasury/api/payments.py:…`
- **How it goes wrong:** 1. … 2. … 3. …  (numbered, ≤5 steps)
- **Blast radius:** …
- **Tests catch it?** No — `tests/treasury/test_v1_allocation.py` only checks …
- **Fix:** … · scope: small · verified by: Codex refute + lead
```

## 4.3 Assembly steps

1. Load `stage3/verified.json`, `stage2/merged.json`, all `good_patterns`,
   `weird_but_reasonable`, `conventions`, `extra` from `stage2/*/result.json`, and the stage
   1 inventories.
2. Write §3 cards first (they are the source for §4–§6, §13). Generate the skeleton of each
   card from JSON with a 20-line Python script, then edit the prose by hand.
3. Write §2 from inventories + `Analysis.md` §2 (already drafted).
4. Write §7 from D6 `extra` (representative tests table) — verify 5 rows by opening the tests.
5. Write §8–§11 from D7/D5/D6 `extra` + `conventions`.
6. Write §12–§14 by hand from the cards; §12 phases follow the brief.
7. Write §15, then the TL;DR and Top 10 **last**.
8. Self-review against 4.1: run `awk 'length > 120'` for long lines; grep for paragraphs
   over 3 sentences; open the file in a Markdown preview and read only the skim path
   (headings + "In short" + Top 10) — it must make sense alone.
9. Commit: `docs(audit): forensic audit report 2026-09-30`. Merge `--no-ff`, delete branch.
10. Offer the user a private HTML artifact of the report (same content) only if asked.

## Done when

The report exists, the skim path reads on its own, every P0/P1 card cites lines the lead
has seen, `findings.json` is committed, branch merged and removed.

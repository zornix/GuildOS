# Plan 07 — Verify: browser pass, checks, critique, handoff bookkeeping

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:verification-before-completion. Steps use checkbox (`- [ ]`) syntax. Read `00-README.md` first. Plans 01–06 must be on `feat/greekos-hci`. This plan writes no product code; it only records evidence and fixes what the pass finds, one commit per fix.

**Goal:** Prove the slice does what the handoff says, with evidence, before the orchestrator merges.

**Spec:** handoff § "7. Verify" and each plan's "Done when".

---

### Task 1: Static checks

- [ ] **Step 1:** `cd LocalDev/greekos && npm test` — paste the summary lines (`ℹ tests`, `ℹ pass`, `ℹ fail`). Expected: fail 0; tests cover formatters, session, contribution, balance, events, transaction, rollCall, adapters.
- [ ] **Step 2:** `npm run lint` — Expected: no output.
- [ ] **Step 3:** `npm run build` — Expected: `✓ built in …` and no warnings about unresolved imports.
- [ ] **Step 4:** `npx tsx src/selfcheck.ts && npx tsx src/lib/parseWhen.check.ts` — Expected: `selfcheck OK` and no assertion error.
- [ ] **Step 5:** Forbidden strings:

```bash
grep -rn "Live Door\|big_ledger\|Venmo Gateway\|✕\|house job\|House job\|NLP Engine\|Commit Attendance\|dues balance\|Dues Balance" LocalDev/greekos/src --include=*.ts --include=*.tsx | grep -v mockData
```

Expected: no output. Anything found is a copy bug: fix, commit as `copy(greekos): …`.

---

### Task 2: Browser pass — officer

Start backend + greekos (README). Use the Claude in Chrome tools if available, otherwise do it by hand and record what you saw. Desktop width first, then a 390×844 viewport.

- [ ] **Home:** banner shows role, standing, "Upcoming: Organizing N · Supervising N · Chairing N", a balance line or "No balance owed", "Schedule event". Four tiles: Upcoming events, Announcements, Jobs, Initiatives; 2×2 on desktop, stacked on phone. No KPI row, no ranking.
- [ ] **Schedule event from Home:** opens Events in list view with the create form open; creating an event lands it in the list and on the calendar.
- [ ] **Events:** opens on the calendar with the bar above it. Chip "Social" filters calendar cells; switching to List keeps the filter. Calendar day → "Open →" lands on that event's detail. "Show door code" and "Open door code" use those words.
- [ ] **Attendance:** roll call opens; Save disabled until something is marked; "Mark remaining present (N)" fills gaps; Save posts one call per marked member (Network tab); status line reads "X present · Y absent".
- [ ] **Treasury:** "Add transaction" → Payment prefills the member's balance → Preview sentence → Confirm; ledger row appears under "Chapter ledger". Fine, Invoice, Adjustment (-10) each add the right row. Mark paid asks first.
- [ ] **Roster:** changing standing asks first; Cancel leaves the select unchanged.
- [ ] **Recruitment:** Extend bid asks first.
- [ ] **Command console:** chips fill the input; Execute asks first showing the command text; log starts empty.
- [ ] **Modals:** Escape closes each one you opened above; overlay click closes; close button has `aria-label="Close"`.
- [ ] **Toast:** stays until dismissed; dismiss button works; devtools shows `role="status" aria-live="polite"` on the wrapper.

Record each as pass/fail with one line of evidence. Fix failures with the smallest change, one commit each, and re-run the affected check.

---

### Task 3: Browser pass — member

Sidebar switcher → Member (notice the "Viewing as" chip and the Demo notice).

- [ ] **Home:** no Supervising count, no Schedule button, balance line present. With a door code open (open it as officer first), the banner shows "Door open for <event>" and a code field; entering the code checks in inline. With none open: "No door open right now · Attendance →".
- [ ] **Attendance:** opens on the Door code tab; the field is the same component.
- [ ] **Treasury:** "Pay balance" opens with the real balance and the amount prefilled from it (not $150); demo note visible.
- [ ] **Jobs:** each card shows its Event/Initiative tag when attached; unassigned jobs show Claim; claiming assigns it to the viewed member.
- [ ] **Nav:** Recruitment and Command console are hidden in member view.

---

### Task 4: Critique and bookkeeping

- [ ] **Step 1:** Run `/impeccable critique LocalDev/greekos` (the `impeccable` skill). Save its output to `LocalDev/docs/greekos-hci-critique-after.md`. Do not act on it in this plan; the orchestrator decides.
- [ ] **Step 2:** In `LocalDev/docs/greekos-hci-handoff.md`, tick the seven checklist boxes at the bottom and change the status line at the top from `plan written, **not implemented**` to `implemented on \`feat/greekos-hci\` (2026-09-07)`. Under "Grill decisions", add a row `| 11 | Verified in browser: see \`greekos-hci-critique-after.md\` and plan 07 report. |`.
- [ ] **Step 3:** `LocalDev/greekos/README.md`: under "Checks" confirm `npm test` is listed (plan 01); add a short "Layout" note listing the new directories `src/lib/` (pure logic + tests), `src/components/home/`, `src/components/finance/`, `src/components/ui/`.
- [ ] **Step 4:** Commit:

```bash
git add LocalDev/docs/greekos-hci-handoff.md LocalDev/docs/greekos-hci-critique-after.md LocalDev/greekos/README.md
git commit -m "docs(greekos): mark HCI slice implemented; record post-critique"
```

---

### Report

Return to the orchestrator:

1. Output of `npm test`, `npm run lint`, `npm run build` (last lines each).
2. The officer and member checklists with pass/fail and one-line evidence per item.
3. Every fix commit made during the pass (hash + message).
4. Anything that could not be verified and why.

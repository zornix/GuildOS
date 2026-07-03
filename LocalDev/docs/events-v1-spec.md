# GuildOS — Events Service V1 Spec

> Saved verbatim from product spec (2026-07-01). Referenced by
> `docs/events-dev-status.md` and the `docs/imp-ev-ph*.md` implementation plans.

## 1. Overview

The Events service manages chapter events, chair-led initiatives, and exec announcements. It handles people assignment (supervisors, organizers, security), decomposition of events into claimable jobs, a gated notification system to prevent spam, and calendar integration.

Three entity types, one calendar.

---

## 2. Entities & Rules

### 2.1 Event
- **Created by:** exec only.
- **Supervisors (officers):** creator is a supervisor by default. Creator may add additional officers as co-supervisors. Minimum 1 (always satisfied by creator).
- **Organizers (chairs):** 1 or more required for the event to be *complete*. An event may exist with zero organizers; it is then auto-flagged **"Organizers Needed"** (derived, not manually set). Chairs can self-volunteer as organizer from the calendar or event detail.
- **Time:** start/end time range. No status field — visibility is driven by time and completeness.
- **Jobs:** created by supervisors or organizers. See §2.4.
- **Security (optional feature):** can be added to an event at any time; not required at creation. See §2.5.
- **Invite list:** link to a spreadsheet template (V1: external link only).
- **Notify:** button on event detail. Enabled only when the event is *complete*:
  - ≥1 supervisor (always true) ✓
  - ≥1 organizer ✓
  - ≥3 jobs ✓
  - Otherwise the event is marked **Incomplete** and the button is disabled.

### 2.2 Initiative
- **Created by:** chairs.
- **Assigned chairs:** any number. No officer involvement required.
- **Time:** initiatives have times; the 36-hour unclaim lock applies the same as events.
- **Jobs:** same lifecycle as event jobs. **Approval is done by the initiative's chairs** (not officers).
- No security feature, no supervisors, no notify gate in V1.

### 2.3 Announcement
- **Created by:** exec only.
- Text + time. Added to the calendar and sent as SMS to all members on send.
- No jobs, no assigned people.
- Example: "Chapter today at 7."

### 2.4 Jobs
Flat (no nesting). Open for any member to claim.

**Lifecycle:**

| State | Color | Trigger |
|---|---|---|
| To-do | 🔴 Red | Job created, or all claimants unclaim, or approver rejects |
| In-progress | 🟢 Green | First member claims |
| Done (reported) | 🟡 Yellow | Any claimant reports done — once per job, job-level |
| Approved | ✅ | Event: officer supervisor approves. Initiative: assigned chair approves. |

**Rules:**
- **Capacity:** each job has a "people needed" count (default 1). Job shows fill state (e.g., 2/4). Job enters in-progress at **first** claim; remaining slots stay claimable.
- **Reporting done:** any claimant can report; single report covers the whole job. One approval per job.
- **Rejection:** approver can reject a 🟡 job back to 🔴/🟢. **A rejection reason is required** (see §3, UX Note 2).
- **Unclaim lock:** members can unclaim until **36 hours before event/initiative start**. After T-36h, unclaiming is disabled. **Claiming remains open** through the event — late help is welcome, late abandonment is not.

### 2.5 Security (events only)
- A **special pre-assigned job type**. Reuses job machinery (states, done/approve) but is assigned by an officer instead of claimed.
- Officer opens the security picker: a table of **every member's stats** (including delinquency score) and assigns members directly.
- The recommendation is advisory — officer picks freely.
- **Swaps:** assigned members may request a swap with another member. The other member must **accept**; both parties are notified. Swaps apply only to security jobs, not regular jobs.
- No-show handling is out of scope (handled elsewhere).

### 2.6 Calendar integration
- Events, initiatives, and announcements all render on the chapter calendar.
- Events with zero organizers show the **Organizers Needed** badge.
- Incomplete events still appear on the calendar (visible to members with their gaps).

### 2.7 Notifications
- **Event notify:** manual button, gated (§2.1). Sends to all members. Fire behavior: single announce action per press; button remains available for legitimate updates but is the only notification channel for the event (no automatic spam).
- **Announcements:** SMS to all members on send.
- **Security swaps:** notification to the requested member; notification back to requester on accept/decline.

---

## 3. UX Notes (carried into every screen)

**UX Note 1 — Disabled notify must explain itself.**
When the notify button is disabled, render an inline checklist showing exactly which completeness criteria are unmet:
```
Notify members  [disabled]
  ✓ Supervisor assigned
  ✗ At least 1 organizer (0 assigned)
  ✗ At least 3 jobs (2 created)
```
Never show a dead button with no explanation.

**UX Note 2 — Rejections must be legible to the member.**
When an approver rejects a 🟡 done-reported job, they must enter a short reason. The job card returns to its prior state showing a **"Rejected: {reason}"** banner, and all claimants are notified. A member must never discover their work was silently undone by seeing the color flip.

---

## 4. Screens & Flows (wireframe level)

### Screen 1 — Chapter Calendar

**Layout:** month/week toggle. Each day cell holds entries color-coded by type: Event / Initiative / Announcement.

**Entry chips:**
- Event: title + time. Badges: `Organizers Needed` (amber) when organizer count = 0; `Incomplete` (gray) when notify gate unmet.
- Initiative: title + time + assigned-chairs avatars.
- Announcement: title + time, megaphone icon, not clickable beyond a text popover.

**Flows:**
1. *Member browsing:* taps an event chip → Event Detail (read view). Sees open jobs count on the chip (e.g., "3 open jobs") as a claim lure.
2. *Chair volunteering:* sees `Organizers Needed` badge → taps → Event Detail shows a prominent **"Volunteer as Organizer"** action (chairs only). One tap, confirm, they're added; badge clears if count ≥1; supervisor notified.
3. *Exec creating:* floating "+" → chooser: **Event / Announcement** (execs) or **Initiative** (chairs see this instead; execs may see all three if they also hold chair roles — V1: role-gated menu).

### Screen 2 — Create Event (exec)

**Form, single page:**
1. Title, description
2. Time range (start / end) — drives the T-36h lock automatically
3. **Supervisors:** creator pre-filled and locked as supervisor. "+ Add co-supervisor" → officer picker (execs only).
4. **Organizers:** chair multi-picker. Optional at creation — helper text: *"You can publish without organizers; the event will be flagged Organizers Needed and chairs can volunteer."*
5. Invite list: paste spreadsheet template link (optional)
6. **Create** → lands on Event Detail.

**Post-create state:** event is on the calendar immediately. Completeness checklist (UX Note 1) is visible on the detail page from second one, guiding the exec to organizer + 3 jobs.

### Screen 3 — Event Detail

The workhorse screen. Four sections top-to-bottom (or tabs on mobile): **People / Jobs / Security / Notify**.

**Header:** title, time range, countdown to T-36h lock ("Unclaiming locks in 2d 4h"), badges (`Organizers Needed` / `Incomplete`).

**People section:**
- Supervisors row (avatars, creator marked). Supervisors can "+ Add co-supervisor."
- Organizers row. Supervisors can add/remove organizers. Chairs see **"Volunteer as Organizer"** if count = 0 (and optionally even if ≥1 — V1: only when 0, keeps it simple).

**Jobs section:**
- List of job cards (see Screen 5). "+ Add Job" visible to supervisors and organizers only.
- Sort: 🔴 open first, then 🟢, 🟡, ✅.

**Security section (collapsible, officer-managed):**
- Empty state: "Add security to this event" (supervisors only) → opens Security Picker (Screen 6).
- Populated: list of security assignments as special job cards with a shield icon. Assigned members see a **"Request Swap"** action on their own card.

**Notify section (supervisors/organizers see the button; members don't):**
- Enabled: **"Notify members"** → confirm dialog previewing the message ("{Event} — {date/time}. {n} open jobs.") → sends → timestamped "Last notified: …" line appears.
- Disabled: checklist per UX Note 1.

**Member read view:** same page minus admin controls — they see people, job cards with claim buttons, the invite spreadsheet link, and security roster.

### Screen 4 — Create/Detail Initiative (chairs)

**Create form:** title, description, time range, **assigned chairs** multi-picker (creator pre-filled, add any number). Create → Initiative Detail.

**Initiative Detail:** identical structure to Event Detail with sections removed:
- People = assigned chairs only (no supervisors)
- Jobs = same cards, **"+ Add Job" and approval available to assigned chairs**
- No Security section, no Notify section (V1)
- Same T-36h countdown in the header

Design intent: an initiative is an event with the officer layer deleted. Reuse the component wholesale.

### Screen 5 — Job Card (component)

**Anatomy:**
```
┌──────────────────────────────────────────┐
│ 🔴 Get decorations              [2/4]    │
│ Due: before event · Created by Sarah     │
│ Claimants: [avatar][avatar]              │
│                       [ Claim ]          │
└──────────────────────────────────────────┘
```

**State-dependent actions by viewer:**

| Viewer | 🔴 To-do | 🟢 In-progress | 🟡 Done-reported | ✅ Approved |
|---|---|---|---|---|
| Member (not claimant) | Claim (if slots open) | Claim (if slots open) | — | — |
| Claimant | — | Unclaim (until T-36h) · Report Done | — (shows "awaiting approval") | — |
| Approver (supervisor / initiative chair) | Edit / delete | Edit | **Approve** / **Reject (reason required)** | Un-approve (edge case, V1 optional) |

**Micro-flows:**
1. *Claim:* tap → instantly added to claimants, card goes 🟢 on first claim, capacity ticks (3/4). If capacity full, Claim button hides for others.
2. *Unclaim:* available until T-36h; after that, button replaced by lock icon + tooltip "Unclaiming closed 36h before event." If **all** claimants unclaim, card reverts 🔴.
3. *Report done:* any claimant, one tap, confirm → 🟡, approver notified. Card shows "Reported by Alex, awaiting approval."
4. *Approve:* one tap → ✅. Claimants notified.
5. *Reject:* opens a required text field ("What's missing?") → card returns 🟢 (claimants retained) with red banner **"Rejected: trash still in the yard"** → claimants notified (UX Note 2). Banner clears on next done-report.

**Security variant:** shield icon, no Claim button (pre-assigned), assigned member sees **Request Swap** instead of Unclaim.

### Screen 6 — Security Picker (supervisors only)

**Layout:** full-screen table of all members.

**Columns:** name, delinquency score, relevant stats (attendance, prior security shifts — whatever the stats service exposes), current claim load for this event, `Assign` button per row.

**Flows:**
1. Default sort: delinquency score (the recommendation) — but it's a sortable table, officer picks freely.
2. Tap Assign → member added to security roster, security job card created on Event Detail, member notified.
3. Remove: from the roster on Event Detail (supervisor only).

**Design note:** the score is visible to officers here, but the assigned member's card does **not** display why they were picked. The assignment notification is neutral: "You've been assigned to security for {Event}."

### Screen 7 — Swap Request (security only)

1. Assigned member taps **Request Swap** on their security card → member picker (any member) → optional note → send.
2. Target member gets a notification + an inbox item: "{Name} wants to swap security for {Event}. [Accept] [Decline]".
3. Accept → roster and job card swap atomically, both parties + supervisor notified. Decline → requester notified, assignment unchanged.
4. One pending swap request per assignment at a time (prevents shotgunning).

### Screen 8 — Announcement Composer (exec)

1. From calendar "+" → Announcement.
2. Fields: text (SMS-length counter, since it goes out via Twilio), date/time.
3. **Send** → confirm dialog with SMS preview and recipient count ("Sends SMS to 47 members") → posts to calendar + fires SMS.
4. No edit-after-send in V1; delete removes from calendar only (SMS is gone).

---

## 5. Permissions Matrix

| Action | Exec | Chair | Member |
|---|---|---|---|
| Create event | ✅ | — | — |
| Create initiative | — | ✅ | — |
| Create announcement | ✅ | — | — |
| Add co-supervisor | ✅ (supervisors) | — | — |
| Add/remove organizers | ✅ (supervisors) | volunteer-only | — |
| Volunteer as organizer | — | ✅ (when 0 organizers) | — |
| Create jobs (event) | ✅ (supervisors) | ✅ (organizers) | — |
| Create jobs (initiative) | — | ✅ (assigned) | — |
| Claim / unclaim / report done | ✅ | ✅ | ✅ |
| Approve/reject jobs (event) | ✅ (supervisors) | — | — |
| Approve/reject jobs (initiative) | — | ✅ (assigned) | — |
| Manage security | ✅ (supervisors) | — | — |
| Request/accept security swap | assigned | assigned | assigned |
| Notify (gated) | ✅ (supervisors) | ✅ (organizers) | — |

---

## 6. V1 Explicit Non-Goals

- Nested jobs
- No-show handling (owned elsewhere)
- Invite spreadsheet beyond an external link (no in-app list)
- Organizer/supervisor accept-decline flow (assignment is unilateral)
- Notify gate threshold configurability (hardcoded: 3 jobs)
- Initiative notify button
- Swap requests for non-security jobs

---

## 7. Open Items for Implementation

1. **T-36h anchor for initiatives** — locked to initiative start time, same as events. Confirm initiatives always require a start time in the schema.
2. **Notify re-press policy** — button stays enabled after first send (for genuine updates); consider a soft cooldown (e.g., 1/hour) if spam appears in practice.
3. **Stats service contract** — Security Picker needs a read endpoint for member stats incl. delinquency score. Define with whatever module owns scoring.

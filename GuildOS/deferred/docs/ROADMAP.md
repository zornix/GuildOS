# Roadmap — FraternityOS Internal Operations Platform

Last updated: 2026-04-04

---

## Vision

FraternityOS becomes the single internal operations platform for any fraternity
chapter: attendance, accountability, task management, and member engagement — all
accessible with zero-friction onboarding (phone number + secret link).

---

## Phase 1: Phone Check-In (DONE)

Members check in to meetings by entering their phone number on a short-lived link.
No accounts, no passwords, no app install.

### What was built

- `POST /api/attendance/checkin/{code}/phone` — no-auth phone check-in endpoint
- Rewritten `/c/{code}` HTML page with phone input form (auto-format, 9-digit validation)
- `PhoneCheckIn` Pydantic model with `field_validator` that strips non-digits and enforces length
- Standalone HTML page served by FastAPI — no React, no Supabase SDK dependency
- Dark-themed UI matching the FraternityOS design language

### How it works

1. Officer generates a check-in link for an event (6-char code, 10-min TTL)
2. Members open `/c/{code}` on their phone — FastAPI serves a lightweight HTML page
3. Member enters their 9-digit phone number (auto-formatted as XXX-XXX-XXX)
4. POST to the phone endpoint: validates link, looks up member by phone+chapter, records attendance
5. No JWT, no session, no app login required

### Remaining items

- [ ] Add `phone` column to `members` table in production Supabase
- [ ] Populate phone numbers for existing members (bulk update or self-service)

---

## Phase 1.5: Delinquency Tracking (DONE)

Officer-facing engagement scoring system that ranks members by attendance compliance
and provides tools for accountability enforcement.

### What was built

**Backend (`api/routes/delinquency.py` + `api/services/delinquency.py`):**
- `GET /api/delinquency/scores` — computes and returns ranked engagement scores for all active chapter members
- `GET /api/delinquency/member/{id}` — per-event breakdown showing attendance, excuses, and fines
- `POST /api/delinquency/assign-security` — auto-selects the 3 most delinquent members for party security duty
- `POST /api/delinquency/remind/{id}` — placeholder for sending payment/engagement reminders

**Frontend (`fratos/pages/delinquency.tsx`):**
- Score table with color-coded progress bars and Good/At Risk/Delinquent badges
- Summary stat cards: at-risk count, total unpaid fines
- Member drill-down: per-event history showing present/excused/pending/absent status with associated fines
- Security auto-assignment modal showing the selected members and their scores
- Per-member reminder button (calls placeholder endpoint)
- Mock API support replicating the same scoring logic for dev/demo

**Scoring formula:**
```
score = (attendance_pct × 70) + (excuse_pct × 20) + ((1 - fine_penalty) × 10)
```
- Attendance (70%): fraction of past required events the member attended
- Excuses (20%): fraction covered by approved excuses (events not attended)
- Fine penalty (up to 10%): `min(unpaid_amount / $200, 0.10)`
- Range: 0 (worst) → 100 (perfect), sorted ascending (most delinquent first)

### Remaining items

- [ ] Wire to real backend (same auth gap as all other pages)
- [ ] Integrate email/push notification for the reminder endpoint
- [ ] Add configurable security pick count (currently hardcoded to 3)

---

## Phase 2: Phone-Based Onboarding

Replace email magic links with phone-number + invite-link onboarding.

### Problem

Current onboarding requires an email magic link, which:
- Adds friction (check email, find link, click, wait for redirect)
- Requires every member to have provided their email to the chapter
- Doesn't match the zero-friction promise of phone check-in

### Design

1. Officer creates chapter (or it already exists)
2. Chapter gets a unique invite slug: `/join/{slug}` (e.g. `/join/tke-delta-mu`)
3. Officer shares the link in the group chat / at a meeting
4. New member opens link → enters **name** + **9-digit phone number**
5. Optionally: officer sets a chapter passphrase for extra verification
6. Member is created in `members` table with `status = active`
7. Phone number is their identity across the platform going forward

### Backend

- `invite_slug` column on `chapters` table (or separate `chapter_invites` table with expiry)
- `POST /api/chapters/{slug}/join` — accepts `{ name, phone, passphrase? }`
- Validates slug exists, optional passphrase matches, phone not already registered
- Upserts into `members` with `status=active`
- Returns member profile

### Frontend

- New route: `/join/{slug}` — standalone HTML page (like check-in page, served by FastAPI)
- Name + phone input, optional passphrase field
- Success → "You're in! Your phone number is your login."
- Error states: invalid slug, wrong passphrase, phone already registered

### Why not SMS OTP?

SMS verification adds cost ($0.01-0.05 per message) and complexity (Twilio integration,
phone number ownership, international numbers). The invite link itself is the secret
(only people in the group chat / at the meeting have it). For a fraternity's
internal tool, this trust model is sufficient. SMS OTP can be added later as an
optional verification layer.

---

## Phase 3: Wire Frontend to Real Backend

The Next.js frontend works fully in mock mode. To go live:

1. Uncomment Supabase session check in `fratos/hooks/use-auth.tsx` (lines 30-37)
2. Set `NEXT_PUBLIC_USE_MOCKS=false` in production env
3. Ensure `NEXT_PUBLIC_API_BASE` points to the Vercel deployment (empty string if same-origin)
4. Test each page against real API:
   - Auth: login via magic link, verify `/api/auth/me` returns profile
   - Events: create, list, view detail with attendance count
   - Check-in: generate link, open `/c/{code}`, verify phone check-in records attendance
   - Excuses: submit, resubmit after denial, officer approve/deny
   - Fines: view (member vs officer), pay, waive
   - Members: roster, role change
   - Delinquency: scores, member detail, security picks

This is a configuration change, not a feature build. All API endpoints already exist.
The mock API was built to match real backend behavior 1:1.

---

## Phase 4: Task Board

Exec and chairs post tasks that help the organization. Members can complete tasks
to clear fines or earn points. This creates a positive-sum alternative to fines —
members can "work off" their debt by contributing to the chapter.

### Concept

- Officers post tasks: "Set up tables for Friday social", "Buy ice for the cooler",
  "Deep clean the kitchen"
- Each task has a category, deadline, fine credit value, and point value
- Members browse open tasks, claim one, complete it, upload a photo as proof
- Officer reviews the submission (approve/reject)
- On approval: fine credit offsets the member's oldest unpaid fine, points accumulate

### Database

**tasks**

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| chapter_id | uuid FK | |
| title | text | |
| description | text | nullable |
| category | text | `service`, `setup`, `errand`, `cleanup`, `other` |
| posted_by | uuid FK | Officer who posted |
| fine_credit | decimal(10,2) | How much fine this offsets |
| points | int | Engagement points earned |
| status | text | `open`, `claimed`, `pending_review`, `completed`, `expired` |
| deadline | timestamptz | |
| created_at | timestamptz | |

**task_submissions**

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| task_id | uuid FK | |
| member_id | uuid FK | |
| photo_url | text | Supabase Storage URL |
| notes | text | nullable |
| status | text | `pending`, `approved`, `rejected` |
| submitted_at | timestamptz | |
| reviewed_by | uuid FK | nullable |
| reviewed_at | timestamptz | nullable |

### Task lifecycle

```
open → claimed (member claims) → pending_review (member submits photo)
    → completed (officer approves) → fine credit applied
    → rejected (officer rejects) → back to open
    → expired (deadline passed with no submission)
```

### API Endpoints

```
GET    /api/tasks                                    # List tasks (filterable by status, category)
POST   /api/tasks                                    # Create task [officer]
PUT    /api/tasks/{id}                               # Update task [officer]
DELETE /api/tasks/{id}                               # Delete task [officer]
POST   /api/tasks/{id}/claim                         # Member claims an open task
POST   /api/tasks/{id}/submit                        # Upload photo + notes
PUT    /api/tasks/{id}/submissions/{sid}/review       # Approve or reject [officer]
```

### Frontend

- New page: `pages/tasks.tsx` — list with tabs (Open, My Tasks, Completed)
- New form: `components/forms/task-submit-form.tsx` — photo upload + notes
- Add "Tasks" to sidebar nav in `fraternity-os-frontend.tsx`
- "Pay or Do" button on `pages/fines.tsx` — when a member has an unpaid fine, show
  available tasks as alternatives

### Photo Upload

Use Supabase Storage:
1. Frontend uploads image directly to a `task-photos` bucket (signed URL)
2. Gets back a public URL
3. Sends URL in the submit request body
4. Officer views photo in the review UI

---

## Phase 5: Recognition + Engagement

### Points System

Members earn points for positive actions:

| Action | Points |
|--------|--------|
| Check in to required event | 10 |
| Check in to optional event | 5 |
| Complete a task | Varies (set by officer) |
| Attendance streak (5+ in a row) | 25 bonus |
| Early check-in (first 2 minutes) | 3 bonus |

Points are stored as a running total on the `members` table (or a separate
`member_stats` table for historical tracking with semester resets).

### Leaderboard

- Dashboard widget showing top 5 members by points this semester
- Full leaderboard page with filters (this week, this month, all time)
- Visible to all members to drive friendly competition

### Streaks

- Track consecutive required-event attendance per member
- Display current streak on dashboard and member profile
- Streak breaks reset to zero (no partial credit)

### "Pay or Do" Modal

When a member views an unpaid fine on the fines page:
- "Pay $25" button (existing)
- "Do a Task Instead" button (new) — opens task list filtered to tasks whose
  `fine_credit >= fine.amount`
- Claiming and completing a task auto-applies the credit to the oldest unpaid fine

### Weekly Digest (future)

Optional push notification or email with:
- Your attendance this week (X/Y events)
- Your rank (#N of M members)
- Open tasks you could complete
- Upcoming required events

---

## Phase 6: Additional Platform Features (Backlog)

These are ideas for later consideration, not committed work:

- **Announcements board:** Officers post chapter-wide announcements with read receipts
- **Voting/polls:** In-app polls for chapter decisions (anonymous or named)
- **Dues tracking:** Integrate with payment processor (Stripe) for semester dues
- **Calendar sync:** Export events to Google Calendar / Apple Calendar via iCal feed
- **Mobile app shell:** Wrap the Next.js app in a PWA or Capacitor shell for home screen install
- **Multi-chapter admin:** National org dashboard to view engagement across chapters
- **Audit log:** Immutable log of who did what and when for accountability and dispute resolution
- **Supabase RLS policies:** Defense-in-depth row-level security on all tables

---

## Technical Debt / Priorities

| Item | Impact | Effort |
|------|--------|--------|
| Wire frontend to real backend (Phase 3) | Unlocks all existing features for production | Low |
| Add `phone` column + populate data | Required for phone check-in in prod | Low |
| Add `requirements.txt` / `pyproject.toml` | Missing dependency manifest | Low |
| Add `__init__.py` files to api packages | Python import reliability | Low |
| Rate limiting on phone check-in | Abuse prevention | Medium |
| Supabase RLS policies | Defense in depth | Medium |
| Error monitoring (Sentry) | Production observability | Medium |
| Integrate reminder notifications | Email or push for delinquency reminders | Medium |
| Connection pooling for Supabase clients | `db.py` creates fresh client per call | Medium |

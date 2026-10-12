# Audit: Events, Calendar, Attendance, Initiatives (backend + schema)

Repo: `/home/mshik/GuildOS/LocalDev`. This audit is read-only. Every path below is relative to `LocalDev/`.
Tags: **[F]** means FACT, checked in code. **[I]** means INFERENCE.

Frozen paths rule: mounted URL paths are frozen, so check `greekos/src/api.ts` before you change any prefix. New collection routes have no trailing slash. Aggregator routers are append-only (`CLAUDE.md` "Domain-package pattern", "Route paths"). The existing collection routes do end in `/`, for example `GET /api/events/` and `GET /api/calendar/`, and they must stay that way.

Mounts (`api/index.py:186-208`):
- `/api/events`
- `/api/attendance`
- `/api/excuses`
- `/api/fines`
- `/c` (check-in page)
- `/api/checkin-links`
- `/api/calendar`
- `/api/initiatives`

---

## 1. Endpoint inventory

### Events: `/api/events`
Aggregator: `api/events/api/router.py:16-18`. It includes `events.py`, then `notifications.py`, then `security.py`.

| Method | Path | Gate | What it does / response |
|---|---|---|---|
| GET | `/types` | auth | Lists `event_types` and seeds 4 defaults on first use. Returns `[{id, chapter_id, name, created_by, created_at}]`. (`api/events/api/events.py:63`, svc `services/events.py:62`) |
| GET | `/upcoming-details` | auth | For every visible event with date >= today (chapter tz) it returns `{events:[{event_id, detail, security[], checkin_link}]}` with a constant query count. (`events.py:69`, svc `:441-622`) |
| GET | `/` | auth | Visibility-filtered list of non-cancelled events: the `events` row plus `organizer_count`, `organizers_needed`, `group_id`, `job_count`, `open_job_count`, `completeness`. **`upcoming` only flips the sort order. It does not filter.** Every event ever made comes back. **[F]** (`events.py:75`, svc `:265-379`, order at `:272`) |
| POST | `/` | `calendar:event:create` | Calls RPC `ev_create_event`. The creator becomes the creator-supervisor. Enqueues an EVENT_CREATED email. Accepts the `Idempotency-Key` header. (`events.py:81`, svc `:642-713`) |
| GET | `/{event_id}` | auth plus visibility (404 if hidden) | Returns the row plus `attendance_count`, `organizers[]` (`id, member_id, source, created_at`, **no names**), `supervisors[]` (with names), counts, `completeness`, `last_notified_at`, `group_events[]`. **No jobs list, no security, no check-in link.** (`events.py:114`, svc `:382-438`) |
| PUT | `/{event_id}` | `calendar:event:update` | Plain `tx.table("events").update()` inside `transaction()`, plus `ev_set_audience` when `audience=custom`. Being a supervisor does **not** let you edit; you need the permission key. (`events.py:121`, svc `:716-788`) |
| DELETE | `/{event_id}` | `calendar:event:delete` | `ev_delete_or_cancel_event`. Hard-deletes an event with no history, otherwise soft-cancels it. Returns `{deleted, cancelled}`. (`events.py:139`, latest RPC `migrations/0216_event_cancel_lock_order.sql:6`) |
| POST | `/{event_id}/supervisors` | supervisor of the event, or `calendar:event:update` | `ev_add_supervisor`. The target must hold an `OFFICER_ROLES` role. (`events.py:161`, svc `:815`) |
| DELETE | `/{event_id}/supervisors/{member_id}` | same | `ev_remove_supervisor`. Returns 409 for the creator lock or for removing the last supervisor. (`events.py:179`, svc `:853`) |
| POST | `/{event_id}/organizers` | auth (self-volunteer) or `calendar:event:update` (assign) | `ev_add_organizer`. (`events.py:197`, svc `:883`) |
| DELETE | `/{event_id}/organizers/{member_id}` | self, or `calendar:event:update` | `ev_remove_organizer`. (`events.py:215`, svc `:924`) |
| GET | `/{event_id}/checkin-link` | auth | Returns the active link. Without `attendance:checkin_link:manage` you only get `{event_id, active, expires_at}`. (`events.py:235`) |
| POST | `/{event_id}/checkin-link` | `attendance:checkin_link:manage` | Rotates the link (TTL `CHECKIN_LINK_TTL_MINUTES`). Returns `{short_code, url, expires_at}`. Returns 409 if the event is cancelled. (`events.py:257`) |
| DELETE | `/{event_id}/checkin-link` | `attendance:checkin_link:manage` | Deactivates the link, chapter-scoped. (`events.py:282`) |
| GET | `/{event_id}/notify-preview` | supervisor, organizer, or `calendar:event:update` | Returns `{event_id, completeness, recipient_count, no_phone_count, no_consent_count, body_preview, last_notified_at}`. (`api/events/api/notifications.py:57`) |
| POST | `/{event_id}/notify` | same | Two-phase SMS blast via `ev_notify_event`. Gated by completeness (≥1 supervisor, ≥1 organizer, ≥3 jobs) and a 1-hour cooldown (429). (`notifications.py:64`, svc `services/notifications.py:128-178`, RPC `migrations/0187_notify_and_announcement.sql:1`) |
| GET | `/security-swaps/mine` | auth | Returns `{incoming[], outgoing[]}` pending swaps. (`api/events/api/security.py:84`) |
| GET | `/{event_id}/security` | auth (any chapter member; **ignores event visibility**) | Returns `[SecurityAssignmentOut]`. Each security task runs its own queries (N+1). (`security.py:92`, svc `services/security.py:43-86`) |
| POST | `/{event_id}/security` | supervisor or `calendar:event:update` | `ev_assign_security`. Returns 201 `SecurityAssignmentOut`. (`security.py:101`) |
| DELETE | `/{event_id}/security/{task_id}` | same | `ev_remove_security`. (`security.py:119`) |
| POST | `/{event_id}/security/{task_id}/swap-request` | identity, checked in the RPC | `ev_request_security_swap`. (`security.py:137`) |
| POST | `/{event_id}/security/swaps/{swap_id}/accept` / `decline` / `cancel` | identity, checked in the RPC | `ev_accept/decline/cancel_security_swap`. **The `event_id` in the path is never checked against the swap.** [F] (`security.py:157/171/185`, svc `:186-250`) |

### Calendar: `/api/calendar`
| GET | `/?start=YYYY-MM-DD&end=YYYY-MM-DD` | auth | Returns `{start, end, items[], groups{}, overdue_invoices[]}`. Item kinds: `event`, `initiative`, `announcement`, `invoice_due`, `task_due`. Writes a `calendar:viewed` usage row. (`api/calendar/api/calendar.py:15-44`, svc `api/calendar/services/calendar.py:9-226`) |
|---|---|---|---|

### Attendance: `/api/attendance`
Aggregator: `api/attendance/api/router.py:24-26`. The order is `/summary`, then legacy, then sessions.

| Method | Path | Gate | What it does / response |
|---|---|---|---|
| GET | `/summary?member_id=` | auth. Self only, unless the caller holds `calendar:officer:view`, `attendance:override` or `attendance:excuse:review` | Returns `[{member_id, name, attended_required, total_required_past_events, attendance_pct}]`. (`api/attendance/api/summary.py:27`, svc `services/signals.py:15-74`) |
| POST | `/checkin/{short_code}` | auth, same chapter | Self check-in via `at_checkin_self`. Returns `{status:"checked_in", event_title, checked_in_at}`. 410 for a dead link, 409 if already checked in. (`api/attendance/api/attendance.py:15`) |
| **GET** | **`/event/{event_id}`** | auth (**any member, no visibility or cancelled check**) | **Per-event roster**: one row per active member, `[{member_id, name, checked_in, checked_in_at, method, excuse_status}]`. (`attendance.py:49-103`) |
| POST | `/event/{event_id}/manual/{member_id}` | `attendance:override` | `at_set_attendance` with body `{status: present\|excused\|absent, reason?}`, then a balance recompute. (`attendance.py:106-138`) |
| GET | `/sessions?event_id=` | auth (any member) | `attendance_sessions` rows. (`api/attendance/api/sessions.py:17`) |
| POST | `/sessions` | `attendance:checkin:create` | Opens a check-in window `{event_id, mode, closes_at}` and, for qr/short_link, opens a link. (`sessions.py:24`, svc `services/sessions.py:16-77`) |

### Excuses: `/api/excuses`
| POST | `/event/{event_id}` | auth | Submit an excuse `{reason}`. **Direct table delete and insert, not an RPC, and no audit row.** (`api/attendance/api/excuses.py:17-67`) |
|---|---|---|---|
| GET | `/?status=` | auth. Reviewers see the whole chapter, everyone else sees their own | Rows plus `members(name,email)` and `events(title,date)`. (`excuses.py:70-97`) |
| PUT | `/{excuse_id}/review` | `attendance:excuse:review` | `at_review_excuse` with `{status: approved\|denied}`. Approving voids open fines. (`excuses.py:100-131`) |

### Check-in links and page
- `GET /api/checkin-links/active` (gate `attendance:checkin_link:manage`) lists the chapter's live links (`api/attendance/api/checkin_links.py:10`).
- `GET /c/{short_code}` is public. It returns a 302 to `FRONTEND_URL/?checkin=code` (`api/attendance/api/checkin_page.py:12`).

### Initiatives: `/api/initiatives`
| GET | `/` | auth | Every initiative in the chapter, plus `chair_member_ids`, `job_count`, `open_job_count`. (`api/initiatives/api/initiatives.py:40`, svc `services/initiatives.py:116`) |
|---|---|---|---|
| POST | `/` | `calendar:initiative:create` | `in_create_initiative`. Returns 201 with `chairs[]`. (`:46`) |
| GET | `/{id}` | auth | Returns the row plus `chairs[]` (with names), **`jobs[]` (full task rows)** and counts. (`:68`, svc `:177-198`) |
| PATCH | `/{id}` | assigned chair (membership, not a permission key) | `in_update_initiative`. (`:79`) |
| POST | `/{id}/chairs` | assigned chair | `in_add_chair`. (`:97`) |
| DELETE | `/{id}/chairs/{member_id}` | assigned chair | `in_remove_chair`. Returns 409 for the last chair. (`:115`) |

There is no initiative delete or cancel route. [F] (`migrations/0144_initiatives_v1.sql:665`: "No :delete key — no delete flow in V1")

### Related, outside this area
- Jobs live in `/api/tasks`. See §6.
- Fines: `GET /api/fines/missed/{event_id}` and `POST /api/fines/issue`, both gated by `treasury:fines:issue` (`api/treasury/api/fines_legacy.py:144,172`).

### Backend routes the frontend does not call [F]
Checked against `greekos/src/api.ts:595-802`:
- `GET /api/calendar/`
- `GET /api/attendance/event/{id}` (roster)
- `/summary`
- `/sessions`
- `/api/checkin-links/active`
- supervisors add/remove
- `GET /api/initiatives/{id}`, PATCH, and chairs

---

## 2. Events schema (final, reconstructed)

**`events`**:
- `0001_initial_schema.sql:54-66`: `id`, `chapter_id`, `title`, `description`, `date DATE NOT NULL`, `time TIME NOT NULL`, `location TEXT NOT NULL`, `required BOOL`, `fine_amount NUMERIC(10,2)` (dollars), `created_by`, `created_at`.
- `0090:7-19`: `event_type TEXT` (free text, legacy), `visibility TEXT NOT NULL DEFAULT 'chapter'`, `linked_task_group_id`, `linked_attendance_session_id`, `linked_announcement_id`, `linked_budget_id` (no FK).
- `0100:64-79`: `event_type_id → event_types`, `finable BOOL`, `event_group_id → event_groups`, `supervisor_member_id` (deprecated). The visibility CHECK allows `chapter|officer|role_specific|private|custom`.
- `0141:13-16`: `end_date DATE`, `end_time TIME`, `invite_link TEXT`.
- `0181:2`: `cancelled BOOL NOT NULL DEFAULT false`.

**Lifecycle / status [F]**
- There is no draft, published or status column.
- The only states are the `cancelled` boolean and states derived on read: `organizers_needed` (`rules.py:36-37`, soft minimum 1), `completeness` (`rules.py:40-50`), and past or upcoming, worked out from the date.
- Cancelling sets `cancelled=true` and `required=false`. It also cancels unfinished tasks, cancels pending swaps, releases commitments and kills the check-in link (`0216:6-65`).
- A cancelled event is hidden from every read: `list_events :271`, `get_event :392`, `_can_view :224`.
- The spec says plainly that there is "no status field" (`docs/events-v1-spec.md` §2.1).

**Categories [F]**
- `event_types` (`0100:7-17`) is a per-chapter catalog with a case-insensitive unique name.
- The defaults are Chapter Meeting, Philanthropy, Brotherhood and Social (`rules.py:17-22`), seeded on demand (`services/events.py:49-59`).
- Create and update send `event_type_name` (get-or-create) and/or the legacy free-text `event_type`. Both columns get written (`services/events.py:697-698,734-738`).
- Event types have no color field.

**Date and time [F]**
- Start is `date` + `time`, a chapter-local wall clock. End is the optional `end_date`/`end_time`.
- If `end_time <= time` and no end date is given, the event rolls over to the next day (`services/events.py:187-198`).
- `end > start` is checked in Python only (`:201-213`). There is no DB CHECK (`0141:11-12`).
- The timezone is `chapters.timezone`, defaulting to America/Los_Angeles (`api/events/core/timing.py:10-17`). The SQL equivalent is `ev_local_start` (`0197:2-8`).
- The API returns naive date/time strings. **No endpoint exposes `chapters.timezone`**: grep of `api/` for a timezone response field returns nothing. [F]

**Location and description [F]**
- `location TEXT NOT NULL`, required on create (`api/events/api/schemas.py:24`).
- `description` is nullable.
- `invite_link` is free text with no URL validation.

**Attendance requirement [F]**
- `required BOOL` is the only thing that drives attendance %, the fine eligibility gate (`fines_legacy.py:54-55`) and `/summary`.
- `finable` and `fine_amount` are stored but **never read** by fine issuance. Fines are a flat `FLAT_FINE_CENTS`, and the gate is `required` only (`fines_legacy.py:172-216`, grep shows no other readers). `fine_amount` is a `float` in the schema (`schemas.py:27`) going into a NUMERIC column, which is a dormant float-money path.

**Audience and visibility [F]**
- API `audience` values are `all|officers|custom`, mapped to `visibility` values `chapter|officer|custom` (`rules.py:25-29,53-57`).
- `event_audience_members` (`0100:49-58`) is replaced as a whole by `ev_set_audience` (`0101:114-171`), which deletes, re-inserts, sets `visibility='custom'` and writes an `UPDATE_EVENT` audit row.
- Who can read a restricted event: the creator, a supervisor, an organizer, anyone holding `calendar:officer:view`, and for custom events the audience list (`services/events.py:223-262,281-325`).
- `role_specific` and `private` have no special handling. They behave as "officers, creator, supervisors and organizers only". [F] by elimination in `_can_view`.

**Organizers [F]**
- `event_organizers` (`0100:33-43`): `source volunteer|assigned`, unique `(event, member)`.
- Any member can self-volunteer. **There is no chair check**, although the spec says "chairs only" (`services/events.py:891-897`).
- `ev_add_organizer` (`0101:237-293`) has **no active-member check**. Supervisors, security and chairs got status guards in 0172/0175/0211/0212; organizers did not. [F]

**Supervisors [F]**
- `event_supervisors` (`0141:22-31`) has an `is_creator` lock and a minimum of one supervisor.
- Co-supervisors must hold `OFFICER_ROLES`, which is the chair roles plus the exec offices (`api/events/auth.py:16-32`). `rush_chair` is in `CHAIR_ROLES`, so a Rush Chair can be a co-supervisor even though the 0218 policy says Rush Chair is for initiatives only. [I], a policy drift.
- `events.supervisor_member_id` and `ev_set_supervisor` (`0101:175`) are dead. The route was removed (`tests/events/test_routes.py`). The column is still emitted in calendar items (`calendar.py:51`).

**Security [F]**
- A security assignment is a `tasks` row with `kind='security'` (`0145:31-37`) plus an active `task_commitments` row.
- `security_swap_requests` (`0145:44-58`) moves `pending→accepted|declined|cancelled`, with one pending swap per task (unique partial index) and update and delete guards.

**Groups [F]**
- `event_groups` (`0100:21-27`) links setup, event and cleanup. `get_event.group_events` lists the siblings.

**Dead legacy tables [F]**
- `event_templates`, `event_template_roles/tasks`, `event_roles`, `event_tasks` and `post_event_reports` (`0003:4-95`) have no readers or writers in `api/`. Their only reference is the existence check in `ev_delete_or_cancel_event`.

## 3. Calendar

`get_calendar` (`api/calendar/services/calendar.py:9-226`) is a single merged range read.

**What it returns [F]**
- **Events** come from `list_events`, so visibility is respected. Each item: `{kind:"event", id, title, date, time, end_date, end_time, required, finable, organizer_count, organizers_needed, understaffed, group_id, supervisor_member_id, event_type, job_count, open_job_count, completeness}` (`:30-64`).
- **Initiatives**: `{kind:"initiative", initiative_id, title, date, time, end_date, end_time, chair_member_ids}` (`:66-101`).
- **Announcements** (sent, chapter audience, dated, not hidden): `{kind:"announcement", announcement_id, title, date, time, audience}` (`:103-129`).
- **Invoice due**, own invoices or all for treasury viewers (`:131-191`).
- **Task due** (`:193-216`).
- The items are sorted by `date` only (`:218`).

**Limitations [F]**
- The range filter is a **string comparison on the start date only** (`:39,91,108`). An event that spans midnight or several days and starts before `start` is left out.
- The defaults are the 1st of the current month in **UTC** and +60 days (`:16-24`), not the chapter timezone.
- `start`/`end` are not format-validated. Only `start > end` is rejected (`calendar.py:22`).
- Events, initiatives and tasks are fetched in full for the chapter and then filtered in Python (`:32`, `:67-72`, `:194-199`), so cost grows linearly with history.
- Initiatives skip any visibility check. That is fine today, because initiatives have no visibility concept.
- `task_due` items include **cancelled and security tasks**, because there is no status or kind filter (`:194-216`). Their due date is the UTC date.
- Event items **omit `location`, `description`, `event_type_id`, `visibility` and organizer or supervisor names**. Items also identify themselves with different keys: `id` for events against `initiative_id`/`announcement_id` for the others.
- `CalendarResponse` is an empty, unused model (`api/calendar/api/schemas.py:5`).

**Enough for a month or week grid plus an agenda?**
- Mostly yes, without new endpoints. [I] One call per visible range gives typed chips with badges: understaffed, `completeness.is_complete` and `open_job_count`.
- The gaps are multi-day spans, a chapter-tz default range, location on the chip, category color or id, and the time-of-day sort, which the frontend can do itself.

## 4. RSVP

**[F] No RSVP or "going" concept exists anywhere.** Grep for `rsvp` across `api/`, `migrations/` and `docs` finds nothing relevant.

The closest concepts are:
- `required` (attendance expected, fines possible).
- Audience: `visibility` plus `event_audience_members`, which says who can see the event. It does not say who is expected.
- Organizer volunteering (`source='volunteer'`), which is an opt-in role.
- Job claims (`task_commitments`).
- The excuse, which is a pre-declared "not going" for a required event.

Note [F]: the roster (`attendance.py:65-71`), unexcused absences and fines (`signals.py:77-104`) all treat **every active member** as expected. They ignore the audience, so a custom or officer-only required event would list and fine people who cannot see it. [I] This is a latent correctness gap.

## 5. Attendance

**Keying [F]**
- `attendance(event_id, member_id)` is unique (`0001:74-90`) and has a `chapter_id` derived by trigger (`0146:19-30,63-69`).
- Columns: `checked_in BOOL`, `checked_in_at`, `method manual|link`.
- There is no status enum. present = `checked_in`; absent = a row with `checked_in=false`, or no row at all; excused = an approved `excuses` row.

**Roll call [F]**
- `POST /api/attendance/event/{id}/manual/{member_id}` calls `at_set_attendance` (`0213:50-143`).
- It takes the event advisory lock `ev_attendance:{event}`.
- `excused` requires a reason and upserts an approved excuse. `present` and `excused` void open fines through `at_void_open_fines` (`0198:2-21`). `absent` deletes the excuse.
- It writes `ATTENDANCE_OVERRIDDEN`.
- There is no bulk endpoint, so a roll call is N requests. The idempotency key is hard-coded to `None` (`attendance.py:121`).

**Self check-in [F]**
- An officer rotates a short code, either with `POST /api/events/{id}/checkin-link` (gate `attendance:checkin_link:manage`) or `POST /api/attendance/sessions` (gate `attendance:checkin:create`). **There are two keys for the same "open check-in" action.** [F] Whether roles hold both was not verified. [I]
- `/c/{code}` redirects into the SPA, which calls `POST /api/attendance/checkin/{code}`, which calls `at_checkin_self` (`0214:2-43`). That voids open fines and writes `ATTENDANCE_OVERRIDDEN` with `self_checkin:true`.
- Link validity requires: active, TTL not expired, and the governing session not closed (`services/checkin_links.py:227-265`).
- There is no check of the event's time window beyond the TTL. [F]

**Excuses [F]**
- Submit is a raw table delete of a previously denied excuse plus an insert (`excuses.py:47-62`). There is no RPC, no audit row, no deadline, and no lock against fine issuance.
- Review goes through `at_review_excuse` (`0213:146-211`). Approving voids open fines. It writes `EXCUSE_REVIEWED`.

**Fines interlock (0213/0214) [F]**
- `tr_issue_event_fines` (`0213:5-46`) takes the same per-event advisory lock and refuses cancelled events.
- It skips a member who already has any fine invoice for the event (including voided or waived ones), who checked in, or who has an approved excuse.
- `at_set_attendance` and `at_review_excuse` now take the same lock (`0213:68,167`), and `at_checkin_self` too (`0214:14`).
- Fines are issued manually, 24h or more after the start, by `treasury:fines:issue`.

**Who manages [F]**
- `attendance:override` for manual marks.
- `attendance:excuse:review` for reviewing excuses.
- `attendance:checkin_link:manage` and `attendance:checkin:create` for opening check-in.
- `calendar:officer:view` and the two keys above can read every member's summary.
- None of these are per-event. A supervisor or organizer of the event gets **no** attendance rights from that role. [F]

**Deep-link [F]**
- `GET /api/attendance/event/{event_id}` exists and returns the full roster with excuse status.
- `GET /api/events/{id}` gives only `attendance_count`.
- `GET /api/fines/missed/{id}` gives the unexcused list plus `finable_now`.

## 6. Jobs on events and initiatives

**[F] Columns**
- `tasks.event_id` (`0110:10`, ON DELETE SET NULL).
- `tasks.initiative_id` (`0144:60-67`), mutually exclusive with `event_id` via `tasks_single_parent_check`.
- `tasks.kind standard|security` (`0145:31`).
- `people_needed`, `rejection_reason` (`0142:15-23`).
- Status is one of `open|committed|in_progress|done|cancelled|done_reported|approved` (`0142:26-28`).

**[F] There is no per-event jobs endpoint.**
- `GET /api/tasks/?status=` returns **every** chapter task plus `claimants`, `claimed_count`, `people_needed`, `kind` (`api/tasks/api/tasks.py:24`, svc `services/tasks.py:149-169`). The frontend filters by `event_id` on the client.
- The task list also includes jobs of events the caller cannot see. [I] This is a visibility leak.
- Initiatives do embed `jobs[]` in `GET /api/initiatives/{id}`. Events do not, so the two are asymmetric.

**Create a job**
- `POST /api/tasks/` needs `tasks:create` **and** one of: supervisor, organizer, or `tasks:assign` (`tasks.py:30-50`, `services/approvals.py:73-86`).

## 7. Initiatives

**[F] Schema** (`0144:11-46`)
- `initiatives(title, description, date NOT NULL, time NOT NULL, end_date, end_time, created_by, updated_at)`.
- `initiative_chairs(is_creator, added_by)`.
- There is no status, cancelled flag, location, visibility or type.

**[F] Permissions**
- `calendar:initiative:create` and `calendar:initiative:update` go to admin plus the chair roles (`0144:667-677`, with `rush_chair` added in `0218:23-25`).
- **`INITIATIVE_UPDATE` is never checked.** Update and chair management are gated on `initiative_chairs` membership only (`api/initiatives/auth.py:12`, `services/initiatives.py:263,319,358`).
- There is no officer override, so an admin who is not a chair cannot edit an initiative. [F]
- Chair rules: the creator is auto-added, at least one chair must remain, the parent row is locked (`0174`), and inactive members are guarded (`0175`, `0212:190,260`).
- Job approval is done by assigned chairs through the tk_* RPCs.
- There is no delete or cancel. `time` is required (spec Open Item 1).

**[F] "Proposals"**: no backend for them exists in this area. Grep finds no proposal tables or routes among the area files. Proposals are only a `CONTEXT.md` term.

## 8. Audit and log rows

Collected from `INSERT INTO audit_logs` in the event, attendance and initiative RPCs [F]:
- **Events**: `CREATE_EVENT`, `UPDATE_EVENT` (audience change, cancel), `ADD_/REMOVE_EVENT_ORGANIZER`, `ADD_/REMOVE_EVENT_SUPERVISOR`, `SET_EVENT_SUPERVISOR` (dead), `EVENT_NOTIFY`.
- **Security**: `SECURITY_ASSIGNED`, `SECURITY_REMOVED`, `SECURITY_SWAP_REQUESTED/ACCEPTED/DECLINED/CANCELLED`.
- **Attendance**: `ATTENDANCE_OVERRIDDEN` (manual and self check-in), `EXCUSE_REVIEWED`. Fine voids come from `tr_void_invoice`.
- **Initiatives**: `INITIATIVE_CREATED/UPDATED`, `INITIATIVE_CHAIR_ADDED/REMOVED`.
- **Jobs**: `CREATE_TASK`, `UPDATE_TASK`, `CANCEL_TASK`, `COMMIT_TASK`, `UNCOMMIT_TASK`, `UPDATE_TASK_STATUS`, `JOB_REPORTED/APPROVED/REJECTED`.

Other append-only logs:
- `event_notification_sends` (`0143:12-33`)
- `task_commitment_log`
- the `message_outbox` rows `EVENT_CREATED`, `EVENT_ROLE_ASSIGNED` (`api/events/notifications.py`), `EVENT_NOTIFY`, JOB_* and SECURITY_*
- `usage_events` `calendar:viewed`

**These writes produce no audit row [F]:**
- `PUT /api/events/{id}`, a plain table update, unless the audience changes (`services/events.py:764-771`).
- Event **hard delete** (the 0216 delete branch returns before the audit insert).
- Excuse submission.
- Attendance session create.
- Check-in link create and kill.

## 9. Tests

Real DB tests, roughly 300 of them: events 23 files, calendar_view 3, attendance 7, initiatives 4.

**Covered [F]** (from test names):
- Visibility matrix (`tests/events/test_audience.py`).
- Create: idempotency and audit.
- Delete vs cancel, and cancel cleanup.
- Groups and types, including the race.
- Supervisors: creator lock, minimum one, end-time rollover.
- Organizers.
- Completeness thresholds and the notify gate: cooldown, idempotency, count mismatch, permissions, append-only.
- Security and swaps, deeply: 26 + 8 tests, plus locks.
- Timezone math.
- `upcoming-details` constant query count.
- Calendar chips, ranges, invoices and initiatives.
- Check-in links, extensively (38 unit + 21 flow).
- Tenant guards on the at_* RPCs, idempotency replay, fine voiding on attendance, excuse approval and self check-in, and the fine/attendance race.
- Initiatives: RPCs, API and chair locks.

**Gaps [F]**, by grep of `tests/`:
- `GET /api/attendance/event/{id}` (roster) is only route-registered.
- Excuse submit, resubmit after a denial, and list scoping.
- The `upcoming` param, which does nothing.
- `GET /api/initiatives/` list.
- Calendar: a multi-day event that starts before the window, the default range in chapter tz, and cancelled or security `task_due` items.
- Event PUT writing no audit row.
- Organizer add for an inactive member.
- Audience vs roster and fines, where all active members are counted.

## 10. Over-engineering and dead code

- `_is_duplicate_code` handles supabase-py `APIError` shapes. supabase-py is not a dependency, per `CLAUDE.md` (`services/checkin_links.py:51-70`). About 6 of the 38 link unit tests (collision classification) exist only for that shim.
- The `ImportError` guard for psycopg2 (`checkin_links.py:31-34`) is dead for the same reason.
- `CalendarResponse` is empty and unused.
- `INITIATIVE_UPDATE` is declared and seeded but never checked.
- `events.supervisor_member_id` and `ev_set_supervisor` are dead but still emitted in calendar items.
- `events.linked_task_group_id`, `linked_announcement_id` and `linked_budget_id` are never read or written.
- The `0003` operations-engine tables are dead.
- `finable` and `fine_amount` are stored and never used.
- `MemberNotActive(InvalidTimeRange)` subclasses a time-range error to borrow a 422 (`services/initiatives.py:33-36`, marked with a ponytail comment).
- `list_upcoming_details` (`services/events.py:441-622`) re-implements `get_event`, `list_security` and the link-session gate inline: about 180 lines of duplicated logic, kept in step by tests. [I] This was a deliberate trade for a constant query count.
- Separately, `list_security` is N+1.
- `list_unexcused_absences` carries a stale TODO about a DB view (`signals.py:80-83`).

---

## Gaps vs desired state

| Need | Gap | Verdict |
|---|---|---|
| Month/week range query | `GET /api/calendar/?start&end` exists and the frontend does not use it. It filters on start date only, so multi-day events that start earlier are missed. The default range is UTC. It scans all rows. | **Frontend-only** for a basic grid: call `/api/calendar/` with explicit start and end. **Backend extension (small)** to catch spanning events: in `calendar.py`, also include events and initiatives whose `end_date >= start`. One condition change, response shape unchanged. |
| Chapter timezone on the client | Not exposed anywhere. | **Backend extension (small)**: add `timezone` to an existing payload, either `/api/calendar/` (`{start, end, timezone, items}`, additive) or the chapter/me read. Until then the frontend can treat date/time as naive chapter-local strings. [I] Naive strings are enough for rendering. |
| Categories on chips | Calendar items carry only free-text `event_type`. There is no `event_type_id` and no color. `GET /api/events/types` exists. | **Frontend-only** for labels: map `event_type` names, and colors client-side. **Backend (additive)** if stable ids are wanted: add `event_type_id` to the event item. |
| Statuses on chips | No lifecycle column. Derived values are there: `understaffed`, `completeness.is_complete`, `open_job_count`, `required`. Cancelled events are invisible. | **Frontend-only**: derive past, upcoming and incomplete from these values. A draft or published state would need a **schema change (unclear / not needed)**, because the spec rejects a status field. |
| Location on calendar chips | Missing from calendar items. It is present in `GET /api/events/` and `/{id}`. | **Backend extension (one line)**: add `location` to the calendar event item. Or **frontend-only**: join with `getEvents()`. |
| Event detail: organizers | Present, but without names. | **Frontend-only**: join with the members list. Or a small additive backend change to add `name`. |
| Event detail: jobs | No per-event jobs read. `/api/tasks/` returns everything. | **Frontend-only** today (filter by `event_id`). **Backend extension (small, additive)**: an optional `event_id`/`initiative_id` query param on `GET /api/tasks/`, which also lets you apply visibility. |
| Event detail: security | `GET /api/events/{id}/security`, or the bundle in `/upcoming-details`, which covers upcoming events only. | **Frontend-only**. |
| Event detail: attendance requirement | `required` is on the event. `finable` and `fine_amount` are misleading because they are unused. | **Frontend-only**. Show `required` and hide `fine_amount`/`finable`, or state that the fine is flat (`flat_fine_cents` from `/api/fines/missed`). |
| Event detail: RSVP | Does not exist. | **Backend extension needed**: a new `event_rsvps` table, RPC and routes. Or **unclear**: product should decide whether organizer volunteering, job claims and excuses already cover it. |
| Attendance deep-link | `GET /api/attendance/event/{id}` exists (roster plus excuse status). The frontend does not call it. | **Frontend-only** for the link. **Backend extension (small)** if the roster should respect the audience and visibility and reject cancelled events. [I] Recommended. |
| Officer actions: edit, cancel, supervisors, organizers, security, notify, check-in, manual attendance, excuses, fines | Every one has an endpoint. Supervisor add/remove is unwired in the frontend. Event edit needs `calendar:event:update` even for supervisors. Roll call is per member. | **Frontend-only** for wiring. **Backend (optional)**: a bulk roll-call endpoint, plus audit rows for event PUT, hard delete and excuse submit. |
| Initiative officer actions | No delete or cancel. Non-chair admins cannot edit, because `INITIATIVE_UPDATE` is ignored. | **Backend extension needed** for cancel. **Small backend change** to honor `calendar:initiative:update` as an override. **Unclear** whether product wants either. |

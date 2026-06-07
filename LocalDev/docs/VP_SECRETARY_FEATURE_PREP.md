# VP and Secretary Feature Prep

Last updated: 2026-04-20

This document maps the requested VP Operations Engine and Secretary Communication Hub onto the current FraternityOS MVP.

## Requested Scope Captured

The requested modules are treated as the next execution layer on top of the existing MVP:

- VP (`Operations Engine`): event templates, dynamic checklists, chair assignment, readiness scoring, and post-event reporting.
- Secretary (`Communication Hub`): multi-channel announcements (SMS + email), segmented recipients, reminders, templates, engagement tracking, and escalation.

## Current Baseline

Active backend domains:
- Events
- Attendance
- Check-in links
- Excuses
- Fines
- Members
- Standing

Active frontend views:
- Dashboard
- Events
- Fines
- Members
- Standing

Deferred code already signals future direction:
- `deferred/api/routes/delinquency.py`
- `deferred/api/services/delinquency.py`
- `deferred/fratos/views/delinquency.tsx`
- `deferred/fratos/mocks/*`

## VP Operations Engine

Core idea: execution layer.

### Recommended First Data Model

Add migrations for:

- `event_templates`
  - `id`, `chapter_id`, `name`, `description`, `event_type`, `default_required`, `default_fine_amount`, `created_at`
- `event_template_roles`
  - `id`, `template_id`, `name`, `description`, `min_assignees`
- `event_template_tasks`
  - `id`, `template_id`, `role_name`, `title`, `description`, `due_offset_hours`, `sort_order`
- `event_roles`
  - `id`, `event_id`, `name`, `description`, `assigned_member_id`, `status`
- `event_tasks`
  - `id`, `event_id`, `role_id`, `assigned_member_id`, `title`, `description`, `due_at`, `status`, `completed_at`
- `post_event_reports`
  - `id`, `event_id`, `attendance_snapshot`, `issues`, `missed_responsibilities`, `generated_at`

Status values:
- Tasks: `not_started`, `in_progress`, `done`
- Roles: `unassigned`, `assigned`, `complete`

### Template Seeds

Create seed templates:

- Party
  - Roles: security, setup, cleanup, sober monitor
  - Tasks: guest list, risk walkthrough, check-in station, cleanup inspection
- Philanthropy
  - Roles: coordinator, volunteer captain, setup, partner liaison
  - Tasks: confirm partner, publish shift list, attendance requirement, post photos/report
- Chapter Meeting
  - Roles: agenda owner, attendance lead, minutes owner
  - Tasks: publish agenda, open check-in, record motions, distribute minutes

### Backend API Shape

Add `api/routes/operations.py`:

- `GET /api/operations/templates`
- `POST /api/operations/events/{event_id}/apply-template/{template_id}`
- `GET /api/operations/events/{event_id}/readiness`
- `GET /api/operations/events/{event_id}/tasks`
- `POST /api/operations/events/{event_id}/tasks`
- `PUT /api/operations/tasks/{task_id}`
- `POST /api/operations/events/{event_id}/roles/{role_id}/assign`
- `POST /api/operations/events/{event_id}/post-event-report`

Readiness formula for v1:

```text
readiness = completed_required_tasks / total_required_tasks
```

Later, weight task readiness by critical role coverage, attendance requirement publication, and open issue count.

### Frontend Module

Add a `VP` or `Operations` nav item.

Views:
- Template picker for existing and new events.
- Event readiness panel with percent, blockers, and checklist status.
- Chair assignment board with member picker and reliability indicators.
- Post-event report view linked from completed/past events.

### Testing

Backend:
- Applying a template creates roles and tasks exactly once.
- Readiness changes when task status changes.
- Chair assignment creates role-scoped sub-checklists.
- Post-event report snapshots attendance and missed tasks.

Frontend:
- Officer can apply a template to an event.
- Officer can assign chairs and update task status.
- Readiness percentage updates after task completion.
- Past event can generate and display a report.

## Secretary Communication Hub

Core idea: command center for messaging.

### Recommended First Data Model

Add migrations for:

- `member_groups`
  - `id`, `chapter_id`, `name`, `type`, `created_at`
- `member_group_members`
  - `group_id`, `member_id`
- `message_templates`
  - `id`, `chapter_id`, `name`, `channel`, `subject`, `body`, `created_at`
- `announcements`
  - `id`, `chapter_id`, `created_by`, `title`, `body`, `channels`, `segment`, `scheduled_at`, `sent_at`, `status`
- `announcement_recipients`
  - `id`, `announcement_id`, `member_id`, `email_status`, `sms_status`, `opened_at`, `clicked_at`, `last_attempt_at`
- `message_events`
  - `id`, `announcement_recipient_id`, `provider`, `event_type`, `payload`, `created_at`

Segments for v1:
- `whole_chapter`
- `pledges`
- `officers`
- custom `member_group`

### Provider Integration

Use explicit provider adapters:

- `api/services/email_provider.py` for SendGrid
- `api/services/sms_provider.py` for Twilio
- `api/services/message_dispatcher.py` for orchestration and retries

Environment variables:

```text
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_PHONE=
SENDGRID_API_KEY=
SENDGRID_FROM_EMAIL=
MESSAGE_WEBHOOK_SECRET=
```

For local testing, default providers should be dry-run adapters that store outbound messages in the database without contacting Twilio or SendGrid.

### Backend API Shape

Add `api/routes/communications.py`:

- `GET /api/communications/templates`
- `POST /api/communications/templates`
- `GET /api/communications/segments`
- `POST /api/communications/announcements`
- `GET /api/communications/announcements`
- `GET /api/communications/announcements/{announcement_id}`
- `POST /api/communications/announcements/{announcement_id}/send`
- `POST /api/communications/webhooks/sendgrid`
- `POST /api/communications/webhooks/twilio`
- `POST /api/communications/escalations/run`

Escalation logic for v1:

```text
if email unread after configured delay:
  send SMS
if SMS still unacknowledged after configured delay:
  flag for exec review
```

### Frontend Module

Add a `Secretary` or `Communications` nav item.

Views:
- Announcement composer with channel toggles, segment picker, and template picker.
- Scheduled/sent announcement list.
- Recipient engagement table with opened/clicked/unread states.
- Escalation queue for unread critical messages.

### Testing

Backend:
- Segment resolver returns correct recipients.
- Dry-run dispatcher records email and SMS attempts.
- Webhook endpoints update recipient engagement.
- Escalation job creates SMS retry or exec flag based on unread state.

Frontend:
- Officer can create announcement from template.
- Segment preview shows recipient count.
- Send action records dry-run deliveries locally.
- Engagement table updates from mocked webhook data.

## Implementation Sequence

1. Fix shared UI accessibility/responsiveness from `docs/WEBSITE_AUDIT.md`.
2. Add URL-backed navigation for Dashboard, Events, VP, Secretary, Fines, Members, Standing.
3. Implement VP database migrations and backend routes with seed templates.
4. Add VP frontend views using local API data.
5. Implement dry-run communication data model and dispatcher.
6. Add Secretary frontend views.
7. Add real Twilio/SendGrid adapters after dry-run tests pass.

## Local Development Readiness (GuildOS)

The local environment is prepared so these modules can be built without changing production behavior:

- `deploy/local-dev.sh` now guarantees feature/dev defaults in `.env`:
  - `FEATURE_VP_OPERATIONS=1`
  - `FEATURE_SECRETARY_COMMS=1`
  - `MESSAGE_DELIVERY_MODE=dry_run`
  - `ESCALATION_DELAY_MINUTES=120`
- `deploy/local-dev.sh` now guarantees frontend feature flags in `fratos/.env.local`:
  - `NEXT_PUBLIC_ENABLE_VP_MODULE=1`
  - `NEXT_PUBLIC_ENABLE_SECRETARY_MODULE=1`
- `.env.example` now includes Twilio/SendGrid variables and local dry-run defaults, so messaging behavior is testable without live provider calls.

Recommended local run:

```bash
bash deploy/local-dev.sh
```

Optional seeded run:

```bash
SEED_LOCAL_DB=1 bash deploy/local-dev.sh
```

## Implemented Baseline (Current)

The first VP backend slice is now wired in the active API:

- Migration: `migrations/0003_operations_engine.sql`
  - Adds `event_templates`, `event_template_roles`, `event_template_tasks`
  - Adds `event_roles`, `event_tasks`, `post_event_reports`
  - Seeds global templates for Party, Philanthropy, and Chapter Meeting
- Routes: `api/routes/operations.py`
  - `GET /api/operations/templates`
  - `POST /api/operations/events/{event_id}/apply-template/{template_id}`
  - `GET /api/operations/events/{event_id}/readiness`
- Service: `api/services/operations.py`
  - Template listing with roles/tasks expansion
  - Idempotent template application to an event (avoids duplicate roles/tasks)
  - v1 readiness calculation from completed tasks

## Build Plan by Milestone

Milestone 1 (VP Template + Checklist):
- Add `event_templates`, `event_template_roles`, `event_template_tasks`.
- Add template apply endpoint.
- Add checklist status transitions (`not_started`, `in_progress`, `done`).

Milestone 2 (VP Readiness + Chair Engine):
- Add `event_roles`, `event_tasks`.
- Add readiness endpoint + UI readiness panel.
- Add chair assignment endpoint/UI with reliability score card.

Milestone 3 (VP Post-Event Report):
- Add `post_event_reports`.
- Auto-generate report from attendance + missed task state.
- Persist delinquency-input fields (issues/missed responsibilities).

Milestone 4 (Secretary Core Messaging):
- Add `member_groups`, `message_templates`, `announcements`, `announcement_recipients`, `message_events`.
- Add template CRUD, segment resolver, compose/send workflow.
- Use dry-run adapters only.

Milestone 5 (Engagement + Escalation):
- Wire Twilio/SendGrid webhooks.
- Track open/click/unread state.
- Run escalation worker (`email unread -> SMS resend -> exec flag`).

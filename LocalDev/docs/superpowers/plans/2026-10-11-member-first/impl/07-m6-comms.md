# M6 — Communications: announcement CRUD, composer with email, outbox

> Read `00-README.md` first. Test first. Stay in your lane. No SMS controls (D8).

**Goal:** officers compose once and publish to the member feed, by email, and onto the calendar, atomically; sent announcements can be edited (text only, audited, never re-sent) and retracted (D9); the Outbox shows what went out.
**Spec:** `../01-phase-b-design.md` §5; `../audit/comms.md` §1–§3, Assessment items 1 and 3; `../audit/frontend-modules.md` §6, §8.
**Migrations:** 0224.
**Allowed files:** backend `migrations/0224_announcement_email_and_edit.sql`, `api/announcements/**`, `api/platform/outbox.py` (only if `enqueue_many` needs a per-member payload callback), `api/platform/message_templates.py` (`ANNOUNCEMENT_EMAIL` template + subject), tests under `tests/announcements/`, `tests/platform/`, `tests/cron/test_templates.py`; frontend `components/comms/**`, `components/cabin/Comms.tsx`, `components/OutboxModule.tsx` (may move to `components/comms/Outbox.tsx`), `hooks/useAnnouncements.ts`, `hooks/useOutbox.ts`, `lib/composer.ts`, `lib/consent.ts`, `api.ts`/`types.ts` (M6 block), `routes.tsx` (`/cabin/comms*` lines), `components/home/Announcements*.tsx` (read-only tile adjustments only).

## T1 — Backend

- [ ] `migrations/0224_announcement_email_and_edit.sql`:
  - widen `message_outbox_event_type_check` with `ANNOUNCEMENT_EMAIL` using the 0159 §3 dynamic pattern;
  - widen `audit_logs_action_check` with `UPDATE_ANNOUNCEMENT`, `RETRACT_ANNOUNCEMENT` using the 0160 pattern (also make `CREATE_ANNOUNCEMENT`, already in the catalog, actually written on create);
  - `ALTER TABLE announcements ADD COLUMN IF NOT EXISTS retracted_at TIMESTAMPTZ;` and a partial index on `(chapter_id) WHERE retracted_at IS NULL`.
- [ ] Failing tests `tests/announcements/test_email_destination.py`: `POST /{id}/send {"email": true}` creates one `ANNOUNCEMENT_EMAIL` row per audience member with an email (dedup `ANNOUNCEMENT_EMAIL:{ann}:{member}`), inside the same transaction as the send (monkeypatch enqueue to raise → announcement stays `draft`); `email: false` creates none; a replay with the same `Idempotency-Key` adds no rows; the rendered email subject is the announcement title and the body is the officer's text verbatim plus the standard footer; `officers` audience resolves with the existing `is_officer` helper; `members_with_balance` with `BalanceEngine`.
- [ ] Implement: `send_announcement(..., email: bool)` runs `an_send_announcement` with `sb=tx` then `enqueue` per recipient (payload `{title, body}`) with `sb=tx`. Template `_announcement_email` passes `payload.body` through (like `ANNOUNCEMENT_SMS`); `SUBJECTS` lookup falls back to `payload.title` for this type. `audiences_for_viewer`/recipient resolution factored into one function shared with `sms.resolve_recipients` minus phone/consent filters.
- [ ] Failing tests `tests/announcements/test_edit_retract.py`: `PATCH /{id}` on a draft changes any field; on a sent one changes only `title`/`body` (other fields → 422), bumps `updated_at`, writes `UPDATE_ANNOUNCEMENT`, enqueues **nothing**; `DELETE /{id}` on a sent one sets `retracted_at`, writes `RETRACT_ANNOUNCEMENT`, and the row disappears from `GET /` for viewers without `announcements:create` and from `/api/calendar/`; a draft delete still hard-deletes and now writes an audit row; create writes `CREATE_ANNOUNCEMENT`. Permissions: `announcements:create` for all three.
- [ ] Implement `PATCH` in `api/announcements/api/announcements.py` + `services/announcements.py` with `transaction()`; filter `retracted_at IS NULL` in `list_announcements` for non-creators and in the calendar read (`api/calendar` is **not** your lane — if the calendar query cannot pick up the filter via the announcements service it already calls, report `BLOCKED` with the exact line; do not edit `api/calendar`).
- [ ] Checkpoint: `python3 -m pytest tests/announcements tests/platform tests/cron/test_templates.py -q`.

## T2 — Composer and list (`/cabin/comms`, `/cabin/comms/new`, `/cabin/comms/:id`)

- [ ] `components/comms/Composer.tsx`: title, body (textarea, 2000 chars), audience radio (Everyone / Officers / Members with a balance), "Also put on the calendar" with date + optional time (chapter tz), destinations: Member feed (always on), Email (checkbox, default on). Steps: Draft (POST `/`) → Preview (recipient count by audience from `GET /api/members/` filtered client-side for display only; the server decides) → Send (POST `/{id}/send {email}` with `Idempotency-Key`) → Done (link to the outbox filtered by this announcement). `lib/composer.ts`: validation + recipient-count estimate, tested. Toast after the server answers; the draft persists so a failed send is resumable.
- [ ] `components/comms/AnnouncementList.tsx`: Drafts and Sent tabs; row actions Edit (sent: title/body only, with the "won't re-send" note), Retract (`ConfirmDialog`), Send (drafts). Detail at `/cabin/comms/:id` shows the text, audience, `sent_at`, and its outbox rows (filter `GET /api/announcements/outbox` client-side by `target_id`).
- [ ] Outbox (`components/comms/Outbox.tsx`): existing module + a "Sending" chip + grouping by `target_id` when opened from an announcement. No pagination (backend returns all; note ceiling with a `ponytail:` comment).
- [ ] Home tile: shows sent, non-retracted announcements only; the delete X is removed from Home (retract lives in the Cabin).
- [ ] Remove the Command-console announcement path's optimistic insert and its "SMS blast" claim (`useAppData.ts:225-241` equivalent after M1) — the console (M8) will call the same `useAnnouncements` mutation.
- [ ] Tests: composer validation table; list shows Retract iff `announcements:create`; Email checkbox present, no SMS control anywhere (`assert.doesNotMatch(/SMS/)`).
- [ ] Checkpoint: `npm test && npm run lint && npm run build`.

## Definition of done

M6 acceptance row; `grep -rn "send-sms\|sms-preview" greekos/src` returns nothing new; checksums updated.

## Risks

- Email volume: a chapter of 150 members → 150 outbox rows per announcement; the drain sends 100 per 5-minute run, so a blast completes within ~10 minutes. State this in the composer's Done step ("Emails go out over the next few minutes").
- Gmail/Workspace daily caps (ops-runbook §5a) — HUMAN FOLLOW-UP: confirm the sending account's limit before the first real blast.

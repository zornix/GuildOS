# Comms audit: announcements, outbox, email/SMS, cron (read-only, 2026-10-11)

Paths relative to `LocalDev/`. **[F]** = FACT read in code. **[I]** = INFERENCE.

---

## 1. Announcements

**Schema** [F]
- `announcements` table: `migrations/0086_announcements_tables_rpcs.sql:5-21`. Columns: `id, chapter_id, title, body, audience ('chapter'|'officers'|'members_with_balance'), status ('draft'|'sent'), created_by, sent_at, created_at, updated_at`.
- Calendar columns added in `0152_b4fend_unblocks.sql:24-31`: `calendar_date DATE`, `calendar_time TIME`, `hidden_from_calendar BOOLEAN DEFAULT FALSE`. Partial index on sent, not hidden, dated rows.
- No `deleted_at` column and no `retracted` status. `published_at` is `sent_at`. There is no custom recipient-list audience.
- `events.linked_announcement_id` FK exists (`0090_events_calendar_links.sql:11`), but nothing in `api/` or `greekos/src` reads or writes it.

**Endpoints** [F] (mounted at `/api/announcements`, `api/index.py:202`)

| Method / path | Permission | File |
|---|---|---|
| `GET /` | any signed-in user | `api/announcements/api/announcements.py:28-44` |
| `POST /` (create draft) | `announcements:create` | `:47-61` |
| `DELETE /{id}` | `announcements:create` | `:64-81` |
| `GET /sms-log` | `announcements:send` | `:84-92` |
| `GET /outbox` | `announcements:send` (treasury rows also need `treasury:audit:view`) | `:95-108` |
| `POST /outbox/{row_id}/retry` | `announcements:send` | `:111-130` |
| `GET /{id}/sms-preview` | `announcements:send:sms` | `:133-146` |
| `POST /{id}/send-sms` (two-phase confirm, `Idempotency-Key`) | `announcements:send:sms` | `:149-180` |
| `POST /{id}/send` (`Idempotency-Key`) | `announcements:send` | `:183-195` |

- **No update or PATCH endpoint.** `updated_at` is only set by the send RPC.
- **Delete** (`services/announcements.py:284-320`): a draft is hard-DELETEd. A sent announcement only gets `hidden_from_calendar=TRUE`, and the call is idempotent.
- **Audit rows:**
  - Send writes `SEND_ANNOUNCEMENT` (`0188_announcement_no_outbox.sql:34-36`), and so does the SMS send (`0132:104`).
  - Create, draft delete and hide write **no audit row**. `create_draft` is a plain table insert (`services/announcements.py:263-281`). `CREATE_ANNOUNCEMENT` is in the audit catalog (`0082:122`) but nothing writes it.
- **Who holds the permissions:**
  - `announcements:create` and `:send` go to officer, president, vice_president and secretary (`0083_rbac_seed_rpcs.sql:71,94,107,127`), plus admin through its blanket grant.
  - `announcements:send:sms` goes only to admin, president and secretary (`0130`).
- **Who sees them** (`services/announcements.py:367-394`, `344-364`):
  - Holders of `create` see every row, drafts included, and can filter by `status`.
  - Everyone else sees only `status='sent'` rows whose audience includes them. `officers` comes from `is_officer` over member_roles. `members_with_balance` is true when `BalanceEngine.member_outstanding > 0`.
  - The list query does **not** filter on `hidden_from_calendar`.
- **Homepage:**
  - `hooks/useAppData.ts:141,178` calls `api.getAnnouncements()` (`api.ts:773`) and passes the rows through `adaptAnnouncements` (`adapters.ts:356-370`).
  - `adaptAnnouncements` drops `hidden_from_calendar` rows, so a "delete" on the frontend acts as a full feed removal, while the backend keeps returning the row. It does **not** drop drafts, so an officer's homepage tile can show unsent drafts [F; whether drafts exist in practice is I].
  - The tile is `components/DashboardOverview.tsx:155-178`. Its X button opens a confirm dialog and then `handleDeleteAnnouncement`, which removes the item optimistically before the server answers (`useAppData.ts:202-205`).
- **The only frontend create path** is the Command console text "send announcement: TEXT" (`components/CommandModule.tsx:193-215`, then `useAppData.ts:225-241`, which calls create then send).
  - It adds the announcement optimistically before the server answers, which breaks a frontend rule.
  - Its summary text claims "Dispatched SMS & Calendar announcement blast" with channels `['Calendar','SMS','Push']`, but **no SMS or push is sent**.
  - `api.ts` has no `sms-preview` or `send-sms` call, so the SMS blast has no UI at all [F].
- **Posting an announcement sends no email** [F].
  - Migration 0188 removed the `ANNOUNCEMENT_PUBLISHED` outbox insert that 0086:83-89 had added (commit 49cba58: the row had no recipient and always failed).
  - ADR-0005 (`docs/adr/0005-…md`) still lists "published announcements" as automatic email. That is doc drift.

## 2. Outbox (`message_outbox`)

**Schema** [F]
- Base table: `0070_treasury_message_outbox.sql:14-45`. Columns: `id, chapter_id, created_at, event_type, member_id (nullable), target_table, target_id, dedup_key, payload JSONB, status, delivery_mode, delivered_at`. A **global UNIQUE index on `dedup_key`** (`:40`).
- Later columns:
  - `attempts`, `last_error` (0150:20-21)
  - `claimed_at` (0155:31)
  - `channel` 'email'|'sms', default 'email' (0159:19-24)
  - `provider_attempted_at`, `provider_message_id` (0186:1-2)
- Statuses: `pending, sending, sent, simulated, failed` (0070, then 0150 §2, then 0155 §2).
- Event types (built up by a widening CHECK; registry at `api/platform/message_templates.py:246-267`):
  - Treasury: INVOICE_ISSUED, PAYMENT_APPROVED, PAYMENT_REJECTED, REFUND_ISSUED, PAYMENT_REMINDER
  - Announcements and events: ANNOUNCEMENT_PUBLISHED (no longer produced), ANNOUNCEMENT_SMS, EVENT_NOTIFY
  - Jobs: JOB_REPORTED, JOB_APPROVED, JOB_REJECTED
  - Security: SECURITY_ASSIGNED, SECURITY_SWAP_REQUESTED, SECURITY_SWAP_ACCEPTED, SECURITY_SWAP_DECLINED (SECURITY_REMOVED has a template but is not in the CHECK)
  - Account and event email: SETUP_CODE, RESET_CODE, EVENT_CREATED, EVENT_ROLE_ASSIGNED
- A trigger `trg_outbox_pin_sms_channel` forces ANNOUNCEMENT_SMS and EVENT_NOTIFY onto `channel='sms'` (0159:35-50).
- `cron_heartbeats` table: 0200:70-77.

**Attempt cap** [F]
- `outbox_claim_batch`, latest body in `0215_outbox_attempt_cap.sql:2-59`.
- It requeues unstamped claims older than 15 minutes, **without refunding the attempt**.
- It parks stamped claims older than 15 minutes as `failed`, "delivery outcome unknown".
- It fails `pending` rows with `attempts >= 5` ("attempt cap reached").
- It claims by `FOR UPDATE SKIP LOCKED` and does `attempts+1`.
- Code-row payloads are wiped on park and on cap.
- Execute is revoked from PUBLIC, anon and authenticated (0155:140-153).

**Idempotency** [F]
- One enqueue path in Python: `api/platform/outbox.py`. `enqueue` (:72-114) defaults `dedup_key` to `"{event_type}:{target_id}"`. `enqueue_many` (:117-157) does one bulk insert with `ON CONFLICT (dedup_key) DO NOTHING` (:37-50).
- Outside a transaction, insert errors are logged and swallowed. Inside a transaction they are raised.

**Every producer and its trigger** [F]

| Event | Producer | Trigger | Dedup key |
|---|---|---|---|
| INVOICE_ISSUED | `treasury/services/invoices.py:54` `create_invoice`, `:99` `create_invoice_v2`, `:281` `issue_event_fines` | invoice or fine created | `INVOICE_ISSUED:{invoice_id}` |
| — | `invoices.py:238-259` `bulk_create_invoices` (dues run) | **enqueues nothing**; `tr_bulk_create_invoices` has no outbox insert | — |
| PAYMENT_APPROVED | `treasury/services/payments.py:51` (`verify_payment`), `:157` (`_after_verify_v2`, used by `verify_payment_v2` and `record_payment`) | approval, only when `_created` | `PAYMENT_APPROVED:{submission_id}` |
| PAYMENT_REJECTED | `payments.py:82` | rejection | `…:{submission_id}` |
| REFUND_ISSUED | `treasury/services/refunds.py:42` | refund | `…:{refund_id}` |
| PAYMENT_REMINDER | `memberadmin/api/scores.py:92` through `treasury/notifications.py:105-138` | officer-initiated, one member | `PAYMENT_REMINDER:{member_id}:{YYYY-MM-DD}` |
| EVENT_CREATED | `events/services/events.py:712` through `events/notifications.py:43-81` | event created, `visibility='chapter'` only, fans out to every active member | `EVENT_CREATED:{event}:{member}` |
| EVENT_ROLE_ASSIGNED | `events.py:845` (`add_supervisor`), `:913` (`add_organizer`) | officer assigns a role | `…:{event}:{member}:{role}:{assignment}` |
| SETUP_CODE / RESET_CODE | `auth/api/auth.py:156` (`_issue_setup_code`, also called from `chapters/services/onboarding.py:82,183`), `:385` invite, `:511` reset | code issued | `{type}:{member}:{expires_at}` |
| JOB_* | plpgsql `tk_report_done` (0144), `tk_approve_task`, `tk_reject_task` (0142) | job lifecycle | `job_*:{task}:…` |
| SECURITY_* | plpgsql `ev_assign_security` / `ev_request_security_swap` (0175), `ev_accept_security_swap` (0211), `ev_decline_security_swap` (0145) | security shifts | `security_*:…` |
| ANNOUNCEMENT_SMS | plpgsql `an_send_announcement_sms` (0132:86-99) | manual SMS blast | `ANNOUNCEMENT_SMS:{ann}:{member}` (a second blast of the same announcement adds no rows) |
| EVENT_NOTIFY | plpgsql `ev_notify_event` (0187) | manual event notify (1-hour cooldown, completeness gate) | per event, per send, per member |

**Draining** [F]
- `api/cron/services/outbox_drain.py:341-409`.
- It claims in batches of 25, up to 100 rows per run, within a 45-second budget (`:58-60`). Unused claims are released and their attempt refunded (`:369-382`).
- It writes a heartbeat to `cron_heartbeats` (`:387-406`). `/api/health` reports `degraded` when the heartbeat is older than 15 minutes (`api/health_checks.py:42-68`).
- There is also an **inline** SMS path: `dispatch_send` in `announcements/services/sms.py:208-287` claims pending rows (`:237-243`) and sends them during the HTTP request. Events notify reuses it.

**Delivery modes** [F]
- `MESSAGE_DELIVERY_MODE` = `dry_run` | `twilio`, for SMS (`api/config.py:21-23`, `api/platform/delivery.py:8-10`).
- `EMAIL_DELIVERY_MODE` = `dry_run` | `smtp` (`config.py:36-46`, `delivery.py:13-15`).
- The drain reads the *live* setting for each row. `message_outbox.delivery_mode` is only a snapshot (`outbox_drain.py:65-125`).
- The boot guard rejects bad values and missing credentials (`api/index.py:24-25,63-107`).
- Side note: 0132:99 writes the literal `'sms'` into the `delivery_mode` column. It is harmless because the drain ignores that column.

**Providers** [F]
- Email: stdlib `smtplib`, STARTTLS, Gmail or Workspace with an app password (`api/platform/email.py:36-57`). Plain text only, no HTML, no List-Unsubscribe header. It opens a new SMTP connection and logs in for every message.
- SMS: Twilio REST, Messaging Service SID preferred (`announcements/services/twilio_client.py`). Consent check uses `api/sms_consent.py:27-30`. The STOP/START webhook is `POST /api/twilio/inbound` (`twilio_inbound.py:110`).
- No Resend or SendGrid code. `SENDGRID_*` env vars are listed as unused, to delete (`docs/ops-runbook.md:462`).

**Templates** [F]
- `api/platform/message_templates.py`. One pure function per event type (`:246-267`). Static subject per type (`:271-292`).
- Footer (`:295-308`): SMS gets the STOP line, email does not. `render_email` returns (subject, body) (`:338-343`).
- ANNOUNCEMENT_SMS and EVENT_NOTIFY pass the officer's `payload.body` through unchanged (`:132-137`).
- The drain fills treasury payloads from the target row (`outbox_drain.py:78-83,128-155`).

**Delivery state and errors** [F]
- Close-out is `_close_row` (`outbox_drain.py:189-229`). Failure reasons:
  - `no phone`, `no_consent`, `no_email`, `no recipient`
  - `provider call failed`, `delivery bookkeeping failed`, `delivery failed`
- The provider-attempt stamp is written before each provider call (`:180-186`).
- **Audit:** only the officer Retry writes `audit_logs OUTBOX_RETRIED` (`announcements/services/outbox.py:179-194`, catalog 0160). Drain deliveries write no audit rows; the row itself is the record.

**Retries** [F]
- Automatic: only through the reaper and attempt cap. Rows that reach a terminal status are never reclaimed (`outbox_drain.py:30-34`).
- Manual: `retry_outbox_row` (`announcements/services/outbox.py:135-195`) resets attempts, keeps the stamp only for "delivery bookkeeping failed", and refuses code rows.

**Dedupe guarantees** [F/I]
- [F] Enqueue happens at most once per `dedup_key`. A claimed row cannot be sent twice concurrently.
- [F] A stamped row whose outcome is unknown is never resent automatically.
- [F] Treasury enqueue runs **after** the money RPC commits, with a plain client (`treasury/notifications.py:10-15`). If that insert fails it is only logged. A replay then skips it because `_created` is false. **So an approval email can be lost permanently.**

## 3. A generic "email the members" composer?

[F] **None exists.**
- No endpoint takes free text and sends it as email.
- The only officer-written text that reaches members is the in-app announcement (feed only, no email since 0188), the announcement **SMS** blast (`ANNOUNCEMENT_SMS`), and the event notify **SMS** (`EVENT_NOTIFY`).
- Every **email** row is produced by the system from a template.
- `PAYMENT_REMINDER` is triggered by an officer but uses a fixed template.

## 4. Email deliverability

- [F] Sender setup is documented in `docs/ops-runbook.md:232-286` (§5a): a Workspace or Gmail mailbox, 2-step verification, an app password, `EMAIL_FROM="GuildOS <ops@yourchapter.org>"`, an optional `EMAIL_REPLY_TO`, and the test command `npm run email:test` / `scripts/send_test_email.py`.
- [F] The runbook warns that Gmail rewrites `From` to `SMTP_USER` unless the sender is a verified alias (`:264-266`). Limits it quotes: about 500 a day on free Gmail, 2,000 a day on Workspace (`:258-262`). ADR-0005 says "Workspace SMTP caps at 500/day", which conflicts.
- [F] **The runbook, `.env.example` and the ADRs say nothing about SPF, DKIM or DMARC.** The only mention is in the untracked `/home/mshik/GuildOS/newmove.md:493`.
- [F] No sending domain is configured in the repo. `.env.example:55-68` has `EMAIL_FROM` blank.
- [I] For a Workspace custom domain, DKIM has to be turned on in the Google Admin console and SPF must include `_spf.google.com`. Neither is written down anywhere.

## 5. Unpaid-invoice reminders

- [F] **Manual, one member at a time:** `POST /api/memberadmin/remind/{member_id}` (`memberadmin/api/scores.py:27-112`).
  - Permission: `standing:remind`.
  - It reads open `unpaid_invoices` and their remaining balance through `remaining_by_invoice`, sends nothing when nothing is owed, and dedupes per member per calendar day.
  - Test: `tests/memberadmin/test_payment_reminder.py`.
- [F] Who holds `standing:remind`: officer and admin only (`0147_authority_one_gate.sql:61,98`). **The treasurer role does not.**
- [F] **No frontend caller.** `api.ts` has no `remind` call.
- [F] **Not scheduled.** There is no reminder cron.
- [F] **No audit row.**
- [F] The response key `sent_to` reports the member's email before anything is actually sent.
- [I] The dedupe day comes from `date.today()` (`treasury/notifications.py:120`), which is the server's day. On Vercel that is UTC, not the chapter's timezone.
- [F] **No bulk "remind everyone who owes"** and no rate limit beyond the daily dedupe.

## 6. Receipt or confirmation after payment approval

- [F] `PAYMENT_APPROVED` email serves as the receipt.
  - Subject: "Payment recorded" (`message_templates.py:273`).
  - Body: "Payment recorded: $X. Thank you." The amount is the submission's `claimed_amount_cents` (`:79-83`, `outbox_drain.py:80`).
  - It fires for verify, verify_v2 and the officer's `record_payment` (`payments.py:51,157,166-193`), once per submission and never on replay.
  - Test: `tests/treasury/test_chunkC_payments.py:205`.
- [F] **What the email lacks:**
  - The receipt number or id. A `receipts` row exists (`0030_treasury_receipts.sql:6-16`) but is not looked up.
  - Which invoices the payment was allocated to.
  - The remaining balance.
- [F] Durability gap: see §2. The enqueue is outside the RPC transaction.

## 7. Email verification

[F] **There is no email-verification flow.** No `email_verified` column, token or endpoint (grep of `api/`, `migrations/` and `greekos/src` found nothing). Setup and reset codes reach the member by email (`auth/notifications.py`), which proves inbox access implicitly when the code is redeemed. They are not a verification feature. There is no self-serve forgot-password either (`ops-runbook.md:203`).

## 8. Cron

- [F] Routes live in `api/cron/api/cron.py`, mounted at `/api/cron` (`index.py:195`). A router-level `require_cron_secret` checks the `Authorization: Bearer $CRON_SECRET` header with a constant-time compare and returns 401 when the secret is empty (`api/cron/auth.py:30-42`). The boot guard requires a secret of at least 16 characters (`index.py:23,57-63`).
- [F] **Jobs:**
  - `GET` and `POST /drain-outbox`: the real job.
  - `GET /process-fines`: a disabled no-op stub (`cron.py:24-35`).
- [F] **Schedule:** `*/5 * * * *` for `/api/cron/drain-outbox`, in both `LocalDev/vercel.json` and `Prod/vercel.json`. There is no other cron.
- [I] Vercel **Hobby** plans only allow daily crons, so a 5-minute schedule needs the Pro plan. Check the plan; if it is Hobby, email can sit for up to a day.

## 9. Frontend OutboxModule

[F] `components/OutboxModule.tsx`, `hooks/useOutbox.ts`.
- Shown in the nav only with `announcements:send` (`config/navigation.ts:30`).
- It lists rows from `GET /api/announcements/outbox`:
  - Status chips (All, Queued, Sent, Failed, Simulated) filter on the server. There is no "Sending" chip.
  - Channel chips filter on the client.
- Each row shows the recipient name, the masked phone (never the email address), the event type, times, the rendered body (codes are hidden), the error with a hint, and a Retry button when the failure can be retried (`lib/consent.ts:304-312`).
- **There is no compose UI.**

## 10. Tests and gaps

[F] **Covered:**
- `tests/announcements/`:
  - `test_calendar_fields.py` (create and delete semantics)
  - `test_list_filter.py`, `test_officers_audience.py`
  - `test_outbox.py` (list, retry, audit, code rows, no ANNOUNCEMENT_PUBLISHED row)
  - `test_sms_send.py`, `test_sms_permissions.py`
  - `test_twilio_client.py`, `test_twilio_inbound.py`
- `tests/cron/`:
  - `test_cron_auth.py`
  - `test_drain_outbox.py` (33 tests: claim, cap, budget, stamps, consent, reminder dedupe)
  - `test_drain_email.py`, `test_templates.py`
  - `test_heartbeats.py`, `test_no_double_send.py`, `test_attempt_cap.py`
- `tests/platform/test_outbox_enqueue.py`
- `tests/memberadmin/test_payment_reminder.py`
- `tests/auth/test_code_emails.py`, `tests/events/test_event_emails.py`
- Treasury: `test_chunkC_payments.py:205`, `test_chunkG_rebuild_hardening.py:306-359`

[F/I] **Gaps:**
- No test that the dues run does or does not notify. Today it silently does not.
- No test for losing the approval email when the enqueue fails after commit.
- No test of the frontend Command console announcement flow or its false SMS claim.
- No test that the homepage hides drafts.
- No test of the SMTP connection under batch load [I].
- No end-to-end test of real SMTP. Only a mocked `smtplib` (`test_drain_email.py:250`).

---

## Assessment: one "communications composer"

**Verdict [I]: reuse the announcements table and the outbox. No new "communication" entity.** The announcement row already has title, body, audience, calendar slot, send state and an audit trail. The outbox rows (`target_table='announcements'`, `target_id=ann.id`) already record exactly who was emailed and how delivery went.

A frontend-only orchestration (create announcement, then send, then enqueue, then create event) is **not enough**, for two reasons:

1. There is no endpoint that can enqueue officer-written email.
2. Three or four separate calls are not atomic. A failure halfway leaves the announcement posted with no email sent, or the reverse.

**Watch out:** creating a real event through `POST /api/events` (`calendar:event:create`) already emails `EVENT_CREATED` to every active member (`events/notifications.py:43`). If the composer also emails, members get the message twice. Either let the composer use the announcement's `calendar_date`/`calendar_time` (the D15 calendar slot, which sends no email), or have the composer suppress one of the two emails. `events.linked_announcement_id` (0090) already exists for linking the two.

### Smallest compatible backend extensions [I, proposals]

1. **Announcement email (the composer's core):**
   - Migration: widen the `message_outbox_event_type_check` CHECK with `ANNOUNCEMENT_EMAIL`, using the existing dynamic pattern (0159 §3).
   - Template: pass the body through and take the subject from `payload.title`. Today `SUBJECTS` is static per type, so this needs a one-line fallback in `render_email`.
   - Service: in `POST /{id}/send`, add an optional `email: bool`. Inside `get_db().transaction()`, call `an_send_announcement` with `sb=tx`, then `enqueue_many(tx, event_type='ANNOUNCEMENT_EMAIL', target_table='announcements', target_id=ann.id, member_ids=<audience>, dedup_key_for=lambda m: f"ANNOUNCEMENT_EMAIL:{ann}:{m}", payload={title, body})`.
   - Audience: reuse `sms.resolve_recipients` minus the phone and consent filter (the `audiences_for_viewer` logic already mirrors it).
   - Result: atomic, idempotent, and no new table.
2. **Email to a chosen member list:**
   - Add an audience value `'members'` plus a nullable `recipient_member_ids JSONB` column on `announcements`, with a tenant guard in the send path.
   - The feed filter then checks whether the viewer is in that list.
   - This avoids a separate recipients table.
3. **Update and delete:**
   - `PATCH /{id}` (permission `announcements:create`): drafts can change anything; sent announcements can change title and body only, with an audit row (new `UPDATE_ANNOUNCEMENT` action, widened like 0160) and an `updated_at` bump.
   - For delete, add `retracted_at TIMESTAMPTZ` (or reuse `hidden_from_calendar` and filter it in `list_announcements` for viewers without `create`), and write an audit row on both draft delete and hide.
   - This also fixes today's mismatch, where the frontend treats "hidden" as deleted but the backend still returns the row.
4. **Unpaid-invoice reminder with dedupe:**
   - Keep `enqueue_payment_reminder` and its day key.
   - Add `POST /api/memberadmin/remind` (bulk) that loops over `BalanceEngine.outstanding_by_member(chapter)`. It needs one `enqueue` call per member, because the payload differs per member and `enqueue_many` takes a single shared payload.
   - Grant `standing:remind` to treasurer, add an audit row for each bulk run, and compute the day key in the chapter's timezone.
   - Scheduling can wait (YAGNI). If it is ever needed, add a `/api/cron/remind-unpaid` route (the router is already secret-gated) and a second `crons` entry.
5. **Receipt on approval with idempotency:**
   - Already idempotent through `PAYMENT_APPROVED:{submission_id}`.
   - Smallest improvement: enrich in the drain by adding a lookup of the `receipts` and verified-payment amount to `_ENRICHMENT`, plus the remaining balance, and update the template text.
   - For durability, move the enqueue inside the transaction (pass a `transaction()` client around the RPC call and enqueue), or insert into the outbox inside `tr_verify_payment_v2`. That is the larger change.

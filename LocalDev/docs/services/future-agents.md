# Future Agents

Where automation plugs in later. Nothing in this document is implemented;
every hook below already exists as an honest seam in the codebase, so an agent
can be added without restructuring.

## Design constraints for any future agent

1. **Agents act through service APIs**, with a real member identity and RBAC
   permissions — never direct table writes, never the service-role client
   outside an RPC.
2. **Approval-gated by default.** The `command_requests` table
   (pending_approval → approved → executed/failed) is the template: a human
   with the approving permission signs off before side effects happen.
3. **Idempotent and audited**, like every other trust-boundary mutation —
   Idempotency-Key headers in, `audit_logs` rows out.
4. **No fabrication.** The bylaws stub's contract (`status:
   "not_implemented", answer: null`) is the standard: an agent that can't
   ground an answer says so.

## Planned agents and their existing hooks

### NL chapter controller (first in line)
- **Hook:** `api/nl_controller` — `command_requests.proposed_actions` (JSONB,
  currently always `[]`) and the approve/reject review flow.
- **Work:** a parser that turns `input_text` into typed proposed actions, an
  executor that runs *approved* requests by calling events / attendance /
  tasks / announcements service functions, and status transitions to
  `executed`/`failed` with `executed_at`.

### Bylaws Q&A
- **Hook:** `api/bylaws/services/documents.query_bylaws` (returns
  `not_implemented`), `bylaws_documents.content` stored verbatim.
- **Work:** retrieval over documents with citations; the response shape gains
  an `answer` plus source spans. Keep the "no answer rather than a made-up
  one" contract.

### Delinquency nagger
- **Hook:** announcements audience `members_with_balance` (treasury seam) and
  the `message_outbox` (delivery is dry-run today).
- **Work:** a scheduled job that drafts (not sends) balance reminders for
  treasurer approval; real delivery providers replace dry-run mode separately.

### Event-prep orchestrator
- **Hook:** the template tables from migration 0003 (`event_templates`,
  `event_roles`, `event_tasks`; their API was removed in 2026-10),
  `events.linked_task_group_id` / `linked_attendance_session_id` /
  `linked_announcement_id`.
- **Work:** on event creation, propose the standard prep bundle (task group +
  attendance session + announcement draft) as a command request.

### Standing reviewer
- **Hook:** `derive_standing()` reason codes, including the dormant
  `INCOMPLETE_REQUIRED_TASKS` signal.
- **Work:** weekly summary for standards_chair, with proposed interventions —
  proposals only; `standing:update` stays a human action.

## Explicitly out of scope until decided otherwise

Payment processing, real SMS/email/push delivery, Google Calendar sync, and
any agent that mutates the ledger.

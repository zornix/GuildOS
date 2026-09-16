# ADR-0005: Email for transactional, SMS for manual announcements

Status: accepted (2026-09-15)

## Context

`message_outbox` started life as an SMS queue: every notification the product
produces — setup codes, invoices, job approvals, security shifts — was going to
be a text message. Running SMS at that volume means a verified toll-free number,
a Messaging Service, prior express written consent per member, STOP handling,
and a carrier that can shut the sender off for getting any of it wrong (#54,
#57). All of that is real work for a chapter to complete before a single message
moves, and none of it is needed to tell a brother his payment was recorded.

Every member already has an email address: `members.email` is required, unique,
and the login identifier. A chapter has none of that infrastructure to buy.

## Decision

**SMS is only for the two manual announcement blasts** an officer composes and
sends on purpose: `ANNOUNCEMENT_SMS` and the event `EVENT_NOTIFY`. Those keep
consent enforcement and the "Reply STOP to opt out" footer.

**Everything automatic goes by email**: setup and reset codes, treasury
lifecycle, payment reminders, published announcements, jobs, security shifts and
swaps, event creation and event role assignment.

`message_outbox.channel` ('email' | 'sms', migration 0159) records the choice per
row and the drain routes on it. It defaults to email — the automatic case — and
a trigger pins the two SMS event types, because they are produced inside plpgsql
where a forgotten column would silently downgrade a blast to mail.

Email sends through Google Workspace / Gmail SMTP with an app password
(`api/platform/email.py`, stdlib `smtplib`). No consent check: transactional mail
from a chapter to its own members is the relationship, not marketing.

## Consequences

- A chapter can run GuildOS end to end with no Twilio account at all. SMS becomes
  an upgrade, not a prerequisite.
- Workspace SMTP caps at 500 recipients/day (2,000 on paid Workspace). A chapter
  of 80 sends well under that; crossing it means a transactional mail API, which
  replaces the body of `send_email` and nothing else.
- Setup codes now travel in an outbox payload, so that payload is a credential:
  the officer-facing outbox list refuses to render `SETUP_CODE` / `RESET_CODE`.
- Delivery failure is quieter than a text. `no_email` on a row is the signal, and
  the drain's failed rows are the operator surface.

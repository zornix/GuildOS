# 01 — Backend: event emails and the outbox list

Branch `fix/review-notifications`. Read `00-README.md` first. All paths are
under `LocalDev/`.

## Fix H1 — event-created email ignores visibility

**Problem.** `api/events/notifications.py::notify_event_created` emails every
active member. An event with `visibility` of `officers` or `custom` (see
`_can_view` in `api/events/services/events.py`) gets its title, date, time and
location mailed to the whole chapter.

**Steps**
1. In `tests/events/test_event_emails.py` add a test: create an event with
   `visibility="officers"` the same way the existing tests create one, then
   assert zero `EVENT_CREATED` rows exist in `message_outbox` for that event id.
   Check how visibility values are actually spelled in `_can_view` and use a
   real non-chapter one. Run it — it must fail.
2. At the top of `notify_event_created`, before the members query:
   ```python
   if (event.get("visibility") or "chapter") != "chapter":
       return 0
   ```
   Make sure the `event` dict the caller passes really carries `visibility`
   (check the call site in `events.py::create_event`). If it doesn't, pass it.
3. Update the function docstring and the module docstring line for
   `EVENT_CREATED` to say "chapter-visible events only".
4. `python3 -m pytest tests/events/` — all green.

**Commit:** `Email an event only when the whole chapter can see it`

## Fix M5 — event create does two queries per member

**Problem.** Same function loops `_enqueue` per member: one SELECT + one INSERT
each, inside the create-event request (~160 round trips for 80 members).

**Steps**
1. Add `enqueue_many` to `api/platform/outbox.py`, next to `enqueue`:
   - Signature: `enqueue_many(sb, *, event_type, chapter_id, target_table,
     target_id, member_ids: list[str], dedup_key_for, payload=None,
     channel="email") -> int` where `dedup_key_for` is a `member_id -> str`
     callable.
   - Build the row dicts exactly as `enqueue` does (same keys, same
     `body_payload` shape, `delivery_mode()`, `status="pending"`).
   - One SELECT: `.select("dedup_key").in_("dedup_key", keys)` to find rows
     already queued; drop them.
   - One INSERT of the remaining rows (skip the call if the list is empty).
   - On insert exception (lost UNIQUE race), fall back to calling `enqueue`
     once per remaining row so exactly-once still holds. Return the count queued.
   - Empty `member_ids` returns 0 without touching the DB.
2. Test first, in `tests/events/test_event_emails.py` (or a new
   `tests/platform/` file if one already exists for outbox): calling
   `notify_event_created` twice for the same event queues N rows the first time
   and 0 the second, and total rows for the event stay N.
3. Rewrite the loop in `notify_event_created` to one `enqueue_many` call,
   wrapped in the same "never fail the write" `try/except` + `logger.warning`
   that `_enqueue` uses. Keep the dedup key format
   `f"{EVENT_CREATED}:{event_id}:{member_id}"` byte-for-byte.
4. `python3 -m pytest tests/events/ tests/cron/` — all green.

**Commit:** `Queue event-created emails in one insert instead of one per member`

## Fix H2 — Outbox tab shows treasury messages to non-treasury officers

**Problem.** `GET /announcements/outbox` is gated on `announcements:send`.
Secretary and VP hold that but no treasury permission, and `list_outbox`
(`api/announcements/services/outbox.py`) renders every chapter row — including
invoice/payment/refund bodies with a member's name and dollar amount.

**Steps**
1. Find the treasury event types: grep `api/treasury/notifications.py` for its
   event-type constants (`INVOICE_ISSUED`, `PAYMENT_APPROVED`,
   `PAYMENT_REJECTED`, `REFUND_ISSUED`, `PAYMENT_REMINDER`, … — use what is
   really there). If that module exports a tuple/set of them, import it;
   otherwise define `_TREASURY_EVENT_TYPES` in `outbox.py` next to
   `_SECRET_EVENT_TYPES` with a comment pointing at the source.
2. Tests first in `tests/announcements/test_outbox.py`:
   - a caller with `announcements:send` but without `treasury:audit:view`
     (secretary) does NOT get a seeded treasury row back, and still gets a
     non-treasury row;
   - a caller who has `treasury:audit:view` gets both.
   Follow the file's existing fixtures for seeding rows and acting as a role.
3. `list_outbox` gets a keyword arg `include_treasury: bool = False`. When
   false, add `.not_.in_("event_type", sorted(_TREASURY_EVENT_TYPES))` to the
   query (check how the repo's `sb` client spells NOT IN — grep for `not_` /
   `neq`; if it has no NOT IN, filter the rows in Python *and* over-fetch is
   not needed: just filter after the query). Filtering in the query is
   preferred so `limit` still returns a full page.
4. In `api/announcements/api/announcements.py::list_outbox` pass
   `include_treasury=has_permission(user, "treasury:audit:view")`
   (`from api.rbac.services.permissions import has_permission` — check how
   other routes import it).
5. `retry_outbox_row`: apply the same rule — a caller without the treasury
   permission retrying a treasury row gets `OutboxRowNotFound`. Add the
   `include_treasury` kwarg, thread it from the route, one test.
6. `python3 -m pytest tests/announcements/` — all green.

**Commit:** `Hide treasury messages in the outbox from officers without treasury access`

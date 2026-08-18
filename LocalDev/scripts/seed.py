"""
Seed the local PostgreSQL database with test data.

Run:  python -m scripts.seed
"""

import sys
import os
import uuid
from datetime import datetime, timezone, timedelta, date, time

import bcrypt
import psycopg2
import jwt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.db_guard import ProdGuardError, require_demo

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fraternityos:localdev@localhost:5434/fraternityos")
JWT_SECRET = os.getenv("JWT_SECRET", "local-dev-secret-key-change-in-prod")

CHAPTER_ID = "00000000-0000-0000-0000-000000000001"
OFFICER_ID = "00000000-0000-0000-0000-000000000010"
OFFICER_AUTH_ID = "aaaaaaaa-0000-0000-0000-000000000010"
MEMBER_IDS = [f"00000000-0000-0000-0000-0000000001{i:02d}" for i in range(1, 8)]
MEMBER_AUTH_IDS = [f"aaaaaaaa-0000-0000-0000-0000000001{i:02d}" for i in range(1, 8)]

EVENT_IDS = [f"00000000-0000-0000-0000-000000000e{i:02d}" for i in range(1, 6)]

# Known demo password for seeded officers. Mirrored in the e2e login fixture at
# fratos/e2e/fixtures/auth.ts — keep the two in sync. Satisfies the min-8
# validator in api/auth/api/schemas.py.
OFFICER_DEMO_PASSWORD = "demo-officer-pw"

# Treasury authority is catalog permissions on roles since 0147 (treasury_grants
# is gone); the demo officer holds them through the 'officer' + 'treasurer' roles
# seeded into member_roles below.
DEMO_OFFICER_ROLE_KEYS = ("admin", "president", "treasurer")

# Phones are E.164 (migration 0149 + api/phone.py). The old bare 9-digit values
# matched nothing: the check-in page collects 10 digits and normalizes to +1...,
# so a seeded member could never be found by phone.
MEMBERS_DATA = [
    {"name": "Jake Martinez", "email": "jake@tke.org", "phone": "+15551110001", "role": "officer"},
    {"name": "Ryan Chen", "email": "ryan@tke.org", "phone": "+15551110002", "role": "member"},
    {"name": "Tyler Brooks", "email": "tyler@tke.org", "phone": "+15551110003", "role": "member"},
    {"name": "Marcus Johnson", "email": "marcus@tke.org", "phone": "+15551110004", "role": "member"},
    {"name": "Alex Rivera", "email": "alex@tke.org", "phone": "+15551110005", "role": "member"},
    {"name": "Chris Park", "email": "chris@tke.org", "phone": "+15551110006", "role": "member"},
    {"name": "Ethan Davis", "email": "ethan@tke.org", "phone": "+15551110007", "role": "member"},
    {"name": "Noah Williams", "email": "noah@tke.org", "phone": "+15551110008", "role": "member"},
]

EVENTS_DATA = [
    {
        "title": "Chapter Meeting - March",
        "description": "Monthly chapter meeting",
        "date": date.today() - timedelta(days=14),
        "time": time(19, 0),
        "location": "Chapter House",
        "required": True,
        "fine_amount": 25.00,
    },
    {
        "title": "Philanthropy Event",
        "description": "Community service day",
        "date": date.today() - timedelta(days=7),
        "time": time(10, 0),
        "location": "City Park",
        "required": True,
        "fine_amount": 50.00,
    },
    {
        "title": "Study Session",
        "description": "Midterm prep",
        "date": date.today() - timedelta(days=3),
        "time": time(18, 0),
        "location": "Library Room 204",
        "required": False,
        "fine_amount": 0.00,
    },
    {
        "title": "Chapter Meeting - April",
        "description": "Monthly chapter meeting",
        "date": date.today() + timedelta(days=3),
        "time": time(19, 0),
        "location": "Chapter House",
        "required": True,
        "fine_amount": 25.00,
    },
    {
        "title": "Formal",
        "description": "Spring formal dance",
        "date": date.today() + timedelta(days=14),
        "time": time(20, 0),
        "location": "Grand Ballroom",
        "required": False,
        "fine_amount": 0.00,
    },
]


def generate_token(member_id: str) -> str:
    # Claim set must match api/auth/api/auth.py::_issue_member_token or the
    # hardened _LocalAuth verifier rejects the token (aud/iss/exp/sub required).
    now = datetime.now(timezone.utc)
    payload = {
        "sub": member_id,
        "exp": now + timedelta(days=7),
        "iat": now,
        "iss": "guildos",
        "aud": "guildos",
        "ver": 0,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def _seed_expense(cur, vendor, amount_dollars, date_iso):
    amount_cents = int(amount_dollars * 100)
    cur.execute(
        'INSERT INTO chapter_expenses (chapter_id, category, amount_cents, status, description, created_by, created_at) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id',
        (CHAPTER_ID, 'supplies', amount_cents, 'active', vendor, OFFICER_ID, date_iso)
    )
    expense_id = cur.fetchone()[0]
    cur.execute(
        'INSERT INTO big_ledger (chapter_id, created_at, entry_type, amount_cents, member_id, source_table, source_id, status) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
        (CHAPTER_ID, date_iso, 'EXPENSE_APPROVED', -amount_cents, None, 'chapter_expenses', expense_id, 'active')
    )


def _seed_fine_invoice(
    cur,
    member_id: str,
    event_id: str,
    amount_dollars: float,
    reason: str,
    status: str,
    issued_at: str,
) -> None:
    """Create a fine as unpaid_invoices(kind=fine) with matching ledger entries."""
    amount_cents = int(round(amount_dollars * 100))
    invoice_status = "paid" if status == "paid" else "unpaid"

    cur.execute(
        'INSERT INTO unpaid_invoices '
        '(chapter_id, member_id, kind, amount_cents, status, description, source_event_id, created_at) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id',
        (CHAPTER_ID, member_id, "fine", amount_cents, invoice_status, reason, event_id, issued_at),
    )
    invoice_id = cur.fetchone()[0]

    cur.execute(
        'INSERT INTO big_ledger '
        '(chapter_id, created_at, entry_type, amount_cents, member_id, source_table, source_id, status) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
        (CHAPTER_ID, issued_at, "INVOICE_CREATED", amount_cents, member_id, "unpaid_invoices", invoice_id, "active"),
    )

    if status == "paid":
        cur.execute(
            'INSERT INTO verified_payments '
            '(chapter_id, member_id, invoice_id, submission_id, amount_cents, verified_by, verified_at, created_at) '
            'VALUES (%s, %s, %s, NULL, %s, %s, %s, %s)',
            (CHAPTER_ID, member_id, invoice_id, amount_cents, OFFICER_ID, issued_at, issued_at),
        )
        cur.execute(
            'INSERT INTO big_ledger '
            '(chapter_id, created_at, entry_type, amount_cents, member_id, source_table, source_id, status) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            (CHAPTER_ID, issued_at, "PAYMENT_RECEIVED", amount_cents, member_id, "unpaid_invoices", invoice_id, "active"),
        )


def _clear_demo_seed(cur) -> None:
    """Remove prior demo rows (fixed UUIDs) without touching other chapter/test data."""
    demo_member_ids = tuple([OFFICER_ID, *MEMBER_IDS])
    demo_event_ids = tuple(EVENT_IDS)

    cur.execute('DELETE FROM verified_payments WHERE chapter_id = %s', (CHAPTER_ID,))
    cur.execute('DELETE FROM chapter_expenses WHERE chapter_id = %s', (CHAPTER_ID,))
    cur.execute('DELETE FROM unpaid_invoices WHERE chapter_id = %s', (CHAPTER_ID,))
    cur.execute('DELETE FROM excuses WHERE event_id IN %s', (demo_event_ids,))
    cur.execute('DELETE FROM attendance WHERE event_id IN %s', (demo_event_ids,))
    cur.execute('DELETE FROM checkin_links WHERE event_id IN %s', (demo_event_ids,))
    cur.execute('ALTER TABLE fines DISABLE TRIGGER USER')
    cur.execute('ALTER TABLE big_ledger DISABLE TRIGGER USER')
    try:
        cur.execute('DELETE FROM big_ledger WHERE chapter_id = %s', (CHAPTER_ID,))
        cur.execute('DELETE FROM events WHERE chapter_id = %s', (CHAPTER_ID,))
        cur.execute('DELETE FROM members WHERE id IN %s', (demo_member_ids,))
    finally:
        # autocommit connection: an interrupted run must not leave the
        # append-only guard triggers disabled on the shared demo DB
        cur.execute('ALTER TABLE big_ledger ENABLE TRIGGER USER')
        cur.execute('ALTER TABLE fines ENABLE TRIGGER USER')
    cur.execute('DELETE FROM chapters WHERE id = %s', (CHAPTER_ID,))


def seed():
    try:
        require_demo(DATABASE_URL, context="seed")
    except ProdGuardError as exc:
        sys.exit(f"error: {exc}")

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    _clear_demo_seed(cur)

    cur.execute(
        'INSERT INTO chapters (id, name, organization, school) VALUES (%s, %s, %s, %s)',
        (CHAPTER_ID, "Delta Mu", "TKE", "State University"),
    )

    all_member_ids = [OFFICER_ID] + MEMBER_IDS
    all_auth_ids = [OFFICER_AUTH_ID] + MEMBER_AUTH_IDS

    for i, m in enumerate(MEMBERS_DATA):
        password_hash = None
        if m["role"] == "officer":
            password_hash = bcrypt.hashpw(
                OFFICER_DEMO_PASSWORD.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")
        cur.execute(
            'INSERT INTO members (id, auth_id, chapter_id, name, email, phone, role, status, password_hash) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (all_member_ids[i], all_auth_ids[i], CHAPTER_ID, m["name"], m["email"], m["phone"], m["role"], "active", password_hash),
        )

    # RBAC: the role/permission catalogs are seeded by migration 0083. Here we
    # mirror each demo member's legacy role into member_roles and make the demo
    # officer the chapter admin (so role assignment is exercisable locally).
    for i, m in enumerate(MEMBERS_DATA):
        cur.execute(
            'INSERT INTO member_roles (chapter_id, member_id, role_key) '
            'VALUES (%s, %s, %s) '
            'ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING',
            (CHAPTER_ID, all_member_ids[i], m["role"]),
        )
    for role_key in DEMO_OFFICER_ROLE_KEYS:
        cur.execute(
            'INSERT INTO member_roles (chapter_id, member_id, role_key) '
            'VALUES (%s, %s, %s) '
            'ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING',
            (CHAPTER_ID, OFFICER_ID, role_key),
        )

    for i, ev in enumerate(EVENTS_DATA):
        cur.execute(
            'INSERT INTO events (id, chapter_id, title, description, date, time, location, required, fine_amount, created_by) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (EVENT_IDS[i], CHAPTER_ID, ev["title"], ev["description"], ev["date"], ev["time"],
             ev["location"], ev["required"], ev["fine_amount"], OFFICER_ID),
        )

    now = datetime.now(timezone.utc)

    # Event 1 (past, required): most members attended
    for mid in all_member_ids[:6]:
        cur.execute(
            'INSERT INTO attendance (event_id, member_id, checked_in, checked_in_at, method) VALUES (%s, %s, %s, %s, %s)',
            (EVENT_IDS[0], mid, True, (now - timedelta(days=14)).isoformat(), "link"),
        )

    # Event 2 (past, required): fewer attended
    for mid in all_member_ids[:4]:
        cur.execute(
            'INSERT INTO attendance (event_id, member_id, checked_in, checked_in_at, method) VALUES (%s, %s, %s, %s, %s)',
            (EVENT_IDS[1], mid, True, (now - timedelta(days=7)).isoformat(), "link"),
        )

    # Excuse for event 2 - member 5 (Alex) has approved excuse
    cur.execute(
        'INSERT INTO excuses (event_id, member_id, reason, status, reviewed_by, reviewed_at, submitted_at) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s)',
        (EVENT_IDS[1], MEMBER_IDS[3], "Doctor appointment", "approved", OFFICER_ID, now.isoformat(), (now - timedelta(days=8)).isoformat()),
    )

    # Pending excuse for event 2 - member 6 (Chris)
    cur.execute(
        'INSERT INTO excuses (event_id, member_id, reason, status, submitted_at) VALUES (%s, %s, %s, %s, %s)',
        (EVENT_IDS[1], MEMBER_IDS[4], "Car broke down", "pending", (now - timedelta(days=7)).isoformat()),
    )

    issued_at = now.isoformat()

    # Fine invoices for members who missed event 1 (Ethan, Noah)
    for mid in all_member_ids[6:]:
        status = "paid" if mid == MEMBER_IDS[5] else "unpaid"
        _seed_fine_invoice(
            cur, mid, EVENT_IDS[0], 25.00,
            f"Missed {EVENTS_DATA[0]['title']} (unexcused)", status, issued_at,
        )

    # Fine invoices for members who missed event 2 without excuse (Alex, Chris, Ethan)
    for mid in [MEMBER_IDS[4], MEMBER_IDS[5], MEMBER_IDS[6]]:
        _seed_fine_invoice(
            cur, mid, EVENT_IDS[1], 50.00,
            f"Missed {EVENTS_DATA[1]['title']} (unexcused)", "unpaid", issued_at,
        )

    # Active checkin link for upcoming event 4
    expires_at = now + timedelta(minutes=10)
    cur.execute(
        'INSERT INTO checkin_links (event_id, short_code, created_by, expires_at, active) VALUES (%s, %s, %s, %s, %s)',
        (EVENT_IDS[3], "TsT123", OFFICER_ID, expires_at.isoformat(), True),
    )

    import random
    for i in range(50):
        days_ago = random.randint(0, 60)
        d_iso = (now - timedelta(days=days_ago, minutes=random.randint(0, 1440))).isoformat()
        _seed_expense(cur, f"Vendor/Service {i}", random.randint(10, 500), d_iso)
        mid = random.choice(all_member_ids)
        _seed_fine_invoice(cur, mid, EVENT_IDS[0], random.randint(10, 100), f"Random invoice {i}", "paid", d_iso)


    cur.close()
    conn.close()

    print("\n=== Database seeded ===")
    print(f"Chapter: Delta Mu ({CHAPTER_ID})")
    print(f"\nMembers ({len(MEMBERS_DATA)}):")
    for i, m in enumerate(MEMBERS_DATA):
        mid = all_member_ids[i]
        token = generate_token(mid)
        role_tag = " [OFFICER]" if m["role"] == "officer" else ""
        print(f"  {m['name']}{role_tag}")
        print(f"    id:    {mid}")
        print(f"    phone: {m['phone']}")
        print(f"    token: {token[:40]}...")
    print(f"\nOfficer token (full):")
    print(f"  {generate_token(OFFICER_ID)}")
    print(f"\nMember token (Ryan, full):")
    print(f"  {generate_token(MEMBER_IDS[0])}")
    print(f"\nEvents: {len(EVENTS_DATA)} ({sum(1 for e in EVENTS_DATA if e['date'] <= date.today())} past, {sum(1 for e in EVENTS_DATA if e['date'] > date.today())} upcoming)")
    print(f"Active checkin link: TsT123 (event: {EVENTS_DATA[3]['title']})")
    print(f"\nFine invoices: unpaid={4}, paid={1}")
    print(f"Excuses: approved={1}, pending={1}")


if __name__ == "__main__":
    seed()

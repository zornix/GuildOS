"""
Seed the local PostgreSQL database with test data.

Run:  python -m scripts.seed
"""

import sys
import os
from datetime import datetime, timezone, timedelta, date, time

import psycopg2
import jwt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fraternityos:localdev@localhost:5434/fraternityos")
JWT_SECRET = os.getenv("JWT_SECRET", "local-dev-secret-key-change-in-prod")

CHAPTER_ID = "00000000-0000-0000-0000-000000000001"
OFFICER_ID = "00000000-0000-0000-0000-000000000010"
MEMBER_IDS = [f"00000000-0000-0000-0000-0000000001{i:02d}" for i in range(1, 8)]

EVENT_IDS = [f"00000000-0000-0000-0000-000000000e{i:02d}" for i in range(1, 6)]

MEMBERS_DATA = [
    {"name": "Jake Martinez", "email": "jake@tke.org", "phone": "5551110001", "role": "officer"},
    {"name": "Ryan Chen", "email": "ryan@tke.org", "phone": "5551110002", "role": "member"},
    {"name": "Tyler Brooks", "email": "tyler@tke.org", "phone": "5551110003", "role": "member"},
    {"name": "Marcus Johnson", "email": "marcus@tke.org", "phone": "5551110004", "role": "member"},
    {"name": "Alex Rivera", "email": "alex@tke.org", "phone": "5551110005", "role": "member"},
    {"name": "Chris Park", "email": "chris@tke.org", "phone": "5551110006", "role": "member"},
    {"name": "Ethan Davis", "email": "ethan@tke.org", "phone": "5551110007", "role": "member"},
    {"name": "Noah Williams", "email": "noah@tke.org", "phone": "5551110008", "role": "member"},
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
    return jwt.encode(
        {"sub": member_id, "exp": datetime.now(timezone.utc) + timedelta(days=30)},
        JWT_SECRET,
        algorithm="HS256",
    )


def seed():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    for tbl in ["fines", "excuses", "attendance", "checkin_links", "events", "members", "chapters"]:
        cur.execute(f'DELETE FROM "{tbl}"')

    cur.execute(
        'INSERT INTO chapters (id, name, organization, school) VALUES (%s, %s, %s, %s)',
        (CHAPTER_ID, "Delta Mu", "TKE", "State University"),
    )

    all_member_ids = [OFFICER_ID] + MEMBER_IDS

    for i, m in enumerate(MEMBERS_DATA):
        cur.execute(
            'INSERT INTO members (id, chapter_id, name, email, phone, role, status) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (all_member_ids[i], CHAPTER_ID, m["name"], m["email"], m["phone"], m["role"], "active"),
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

    # Excuse for event 2 - Alex has approved excuse
    cur.execute(
        'INSERT INTO excuses (event_id, member_id, reason, status, reviewed_by, reviewed_at, submitted_at) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s)',
        (EVENT_IDS[1], MEMBER_IDS[3], "Doctor appointment", "approved", OFFICER_ID, now.isoformat(), (now - timedelta(days=8)).isoformat()),
    )

    # Pending excuse for event 2 - Chris
    cur.execute(
        'INSERT INTO excuses (event_id, member_id, reason, status, submitted_at) VALUES (%s, %s, %s, %s, %s)',
        (EVENT_IDS[1], MEMBER_IDS[4], "Car broke down", "pending", (now - timedelta(days=7)).isoformat()),
    )

    # Fines for members who missed event 1 (members 7, 8 missed)
    for mid in all_member_ids[6:]:
        cur.execute(
            'INSERT INTO fines (event_id, member_id, chapter_id, amount, reason, status, issued_at) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (EVENT_IDS[0], mid, CHAPTER_ID, 25.00, f"Missed {EVENTS_DATA[0]['title']} (unexcused)", "unpaid", now.isoformat()),
        )

    # Fines for members who missed event 2 without excuse (Chris, Ethan, Noah)
    for mid in [MEMBER_IDS[4], MEMBER_IDS[5], MEMBER_IDS[6]]:
        cur.execute(
            'INSERT INTO fines (event_id, member_id, chapter_id, amount, reason, status, issued_at) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (EVENT_IDS[1], mid, CHAPTER_ID, 50.00, f"Missed {EVENTS_DATA[1]['title']} (unexcused)", "unpaid", now.isoformat()),
        )

    # One paid fine (Ethan paid his event 0 fine)
    cur.execute(
        'UPDATE fines SET status = %s, paid_at = %s WHERE member_id = %s AND event_id = %s',
        ("paid", now.isoformat(), MEMBER_IDS[5], EVENT_IDS[0]),
    )

    # Active checkin link for upcoming event 4
    expires_at = now + timedelta(minutes=10)
    cur.execute(
        'INSERT INTO checkin_links (event_id, short_code, created_by, expires_at, active) VALUES (%s, %s, %s, %s, %s)',
        (EVENT_IDS[3], "TsT123", OFFICER_ID, expires_at.isoformat(), True),
    )

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
        print(f"    email: {m['email']}")
        print(f"    phone: {m['phone']}")
        print(f"    token: {token[:40]}...")
    print(f"\nLogin at http://localhost:3000 — use any member email above.")
    print(f"Officer login: jake@tke.org (full access)")
    print(f"\nEvents: {len(EVENTS_DATA)} ({sum(1 for e in EVENTS_DATA if e['date'] <= date.today())} past, {sum(1 for e in EVENTS_DATA if e['date'] > date.today())} upcoming)")
    print(f"Active checkin link: TsT123 → http://localhost:8001/c/TsT123")
    print(f"Fines: unpaid=4, paid=1")
    print(f"Excuses: approved=1, pending=1")


if __name__ == "__main__":
    seed()

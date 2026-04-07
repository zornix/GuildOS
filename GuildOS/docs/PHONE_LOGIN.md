# Phone-Number Check-In — Design Document

Last updated: 2026-04-04

---

## Problem

The original check-in flow required every member to have a Supabase account with a
magic-link email session. In practice, most members just need to prove they are
physically present at a meeting. Requiring them to log in via email on their phone
creates friction and drop-off.

**Observed issues with the email flow:**
- Members don't check email during meetings → miss the magic link window
- Mobile email apps sometimes strip or delay magic link delivery
- Some members haven't provided an email or use shared/old email addresses
- The full Supabase JS SDK adds unnecessary weight to a page that just needs to record attendance

## Solution

Replace the session-based check-in with a phone-number-only flow. Members enter
their 9-digit phone number on the check-in page to instantly record attendance.

The check-in link itself acts as the location proof (short TTL, officer-controlled),
and the phone number acts as the identity proof (must match a registered member in
the chapter).

---

## User Flow

1. Officer taps "Open Check-In" on an event → system generates 6-char short code
2. Officer shares the link `/c/{code}` (verbally, QR code, or group chat)
3. Member opens link on their phone
4. Page displays: event title, date, location, and a phone number input
5. Member types their 9-digit number (auto-formatted as XXX-XXX-XXX)
6. Taps "Check In"
7. Sees "You're checked in!" (green) or an error message (red)

Total time: ~5 seconds from opening the link.

### Officer flow (in the dashboard)

1. Navigate to Events → select an event → tap "Open Check-In"
2. Dashboard shows the short code prominently with a countdown timer
3. Officer can share the full URL or just announce the code
4. When the meeting segment is over, officer taps "Close Check-In" to kill the link early
5. The attendance roster updates in real-time (on reload) showing who checked in

---

## Backend

### Endpoint

```
POST /api/attendance/checkin/{short_code}/phone
```

**Request body:**
```json
{ "phone": "123456789" }
```

**No authentication header required.**

### Validation pipeline

1. **Pydantic validation** (`PhoneCheckIn` model):
   - `field_validator("phone")` strips all non-digit characters via `re.sub(r"\D", "", v)`
   - Enforces exactly 9 digits after stripping (raises `ValueError` → 422 if not)
   - Returns the cleaned digit-only string

2. **Link validation** (`validate_checkin_link(short_code)`):
   - Queries `checkin_links` table: `short_code` match, `active=true`, `expires_at >= now`
   - Uses admin Supabase client (bypasses RLS) with an `events(*)` join
   - Returns link data with nested event, or `None` if invalid/expired

3. **Member lookup**:
   - Queries `members` table: `phone` match + `chapter_id` (from the event via link) + `status=active`
   - 404 if no match — member isn't registered or phone doesn't match

4. **Duplicate check**:
   - Queries `attendance` table: `event_id` + `member_id` where `checked_in=true`
   - 409 if already checked in — prevents double-counting

5. **Attendance upsert**:
   - `on_conflict="event_id,member_id"` — handles race conditions (two rapid taps)
   - Sets `checked_in=true`, `checked_in_at=now()`, `method='link'`

### Response

**200 OK:**
```json
{
  "status": "checked_in",
  "event_title": "Chapter Meeting",
  "checked_in_at": "2026-04-04T19:00:00+00:00"
}
```

**Error codes:**
| Code | Meaning | When |
|------|---------|------|
| 410 | Link expired or invalid | Link not found, `active=false`, or `expires_at` passed |
| 404 | No member found | Phone number doesn't match any active member in this chapter |
| 409 | Already checked in | Member already has `checked_in=true` for this event |
| 422 | Validation failed | Phone number is not exactly 9 digits after stripping |

### Schema model

`PhoneCheckIn` in `api/models/schemas.py`:
- Accepts `phone` as string
- `field_validator` strips non-digit characters, enforces exactly 9 digits
- The cleaned value is what gets stored and queried — no formatting in the database

---

## Frontend (HTML Page)

The check-in page is a self-contained HTML page served by FastAPI at `/c/{code}`.
It does **not** use React, Next.js, or the Supabase JS SDK.

### Why a standalone HTML page?

- **No build step**: the page is a Python f-string rendered by FastAPI
- **No JS framework overhead**: loads instantly on any mobile browser
- **No auth dependency**: no Supabase JS client, no session management code
- **No CORS issues**: served from the same origin as the API
- **Works on any device**: just HTML + vanilla JS + inline CSS

### Key elements

- Phone input with `inputmode="numeric"` — triggers number pad on mobile
- `maxlength="11"` — allows for formatted input (XXX-XXX-XXX = 11 chars with dashes)
- Auto-formatting as user types: `123` → `123-456` → `123-456-789`
- Submit button starts disabled, enables when exactly 9 digits are entered
- On submit: `fetch()` POST to the phone check-in endpoint
- Success: hides form, shows green confirmation banner
- Error: shows red message with API detail, re-enables form for retry
- Button text changes to "Checking in..." during request to prevent double-taps

### Auto-format logic

```javascript
function formatPhone(raw) {
    const d = raw.replace(/\D/g, '').slice(0, 9);
    if (d.length <= 3) return d;
    if (d.length <= 6) return d.slice(0,3) + '-' + d.slice(3);
    return d.slice(0,3) + '-' + d.slice(3,6) + '-' + d.slice(6);
}
```

The formatter:
1. Strips all non-digit characters
2. Caps at 9 digits
3. Inserts dashes at positions 3 and 6
4. Preserves cursor position after reformatting (handles mid-string edits)

### Styling

Matches the existing FraternityOS dark theme:
- Background: `#0f0f1a`
- Card: `#1a1a2e` with `#2a2a45` border, 16px radius
- Accent: `#6c5ce7` (purple) — used for submit button and input focus border
- Success: `#10b981` (green) with `#10b98122` background
- Error: `#ef4444` (red) with `#ef444422` background
- Font: system font stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`)
- Phone input: `22px` font size with `2px` letter spacing for readability

### Error handling

| Scenario | User sees |
|----------|-----------|
| Link expired | "Link expired" page (410 HTML, no form rendered) |
| Phone not found | Red banner: "No member found with that phone number" |
| Already checked in | Red banner: "Already checked in" |
| Network failure | Red banner: "Network error. Try again." |
| Validation error (< 9 digits) | Submit button stays disabled (client-side prevention) |

---

## Database Prerequisite

The `members` table needs a `phone` column:

```sql
ALTER TABLE members ADD COLUMN phone text UNIQUE;
```

Members must have their phone number populated for this flow to work. This can be
done via:
- Bulk import by an officer (SQL `UPDATE` or admin script)
- Self-registration during onboarding (future Phase 2: invite link flow)
- Manual entry in the members management page (future UI enhancement)

### Phone format in database

Stored as **9 digits only**, no formatting (e.g., `"123456789"` not `"123-456-789"`).
The Pydantic validator strips formatting on input. All queries match on the raw digit string.

---

## Security Considerations

| Concern | Mitigation |
|---------|------------|
| Phone number is not a secret | Check-in links have short TTL (default 10 min) and officer can kill early. Knowing a phone number alone does nothing without an active link. |
| Someone could try all phone numbers | Rate limiting on the endpoint (future). The 9-digit space (10^9 = 1 billion combinations) is large enough that brute force during a 10-min window is impractical even at 100 req/sec. |
| Link forwarded to non-present member | Same risk as the JWT flow. TTL + officer judgment. Officer can review `checked_in_at` timestamps to spot outliers. |
| Phone number enumeration | 404 response says "No member found with that phone number" — this is intentional since only chapter members use the page. For public-facing endpoints this would be an info leak, but this page is only accessible via a secret short code. |
| Replay attack (re-using a code) | `active=false` after expiry or officer kill. Even if cached, the server-side check rejects expired/inactive links. |
| Man-in-the-middle | HTTPS on Vercel. The link URL is transmitted in the same trusted channel (group chat, in-person verbal). |

### Future security enhancements

- **Per-IP rate limiting**: max 5 attempts per IP per 10-minute window on the phone endpoint
- **Per-phone throttle**: max 3 check-in attempts per phone number per hour across all links
- **Geolocation check**: compare member's IP geolocation to event location (high false positive rate, useful only as an audit signal)
- **SMS OTP on registration**: one-time verification during onboarding to prove phone ownership

---

## Files Changed

| File | Change |
|------|--------|
| `api/models/schemas.py` | Added `PhoneCheckIn` model with phone validator |
| `api/routes/attendance.py` | Added `POST /checkin/{short_code}/phone` endpoint |
| `api/routes/checkin_page.py` | Rewrote HTML page: removed Supabase SDK, added phone input form |

---

## Interaction with Other Systems

| System | How phone check-in interacts |
|--------|------------------------------|
| **Fines** | Attendance records created by phone check-in are used by the cron job to determine who missed a required event. A phone check-in prevents a fine from being generated. |
| **Excuses** | If a member has an approved excuse, they don't need to check in. If they check in anyway, both records coexist — the attendance record takes priority in delinquency scoring. |
| **Delinquency** | The scoring engine counts phone check-ins the same as JWT check-ins. The `method` field distinguishes them but both count as `checked_in=true`. |
| **Roster view** | The attendance roster (`GET /api/attendance/event/{id}`) shows all check-ins regardless of method. Officers can see whether each member used `link` or `manual`. |

---

## Future Enhancements

- **Rate limiting:** Add per-IP or per-phone throttle to prevent abuse
- **Phone verification on registration:** Send SMS OTP once during onboarding to verify ownership
- **Remember phone:** `localStorage` on the device so returning members don't re-type
- **Confirmation name:** After phone lookup, show "Checking in as [Name]..." before final submit
- **QR code generation:** Auto-generate a QR code from the check-in URL for the officer to display
- **Offline resilience:** Service worker that queues the check-in if the phone is briefly offline

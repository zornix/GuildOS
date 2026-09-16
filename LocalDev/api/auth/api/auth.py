import secrets
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies import get_current_user
from api.rbac.auth import require_permission
from .schemas import (
    InviteRequest,
    LoginRequest,
    RedeemSetupCodeRequest,
    SetPasswordRequest,
)
from api.members.api.schemas import UserProfile
from api.platform.db import get_db
from api.platform.rows import unwrap_row
from api.config import settings

router = APIRouter()

# Token claims. iss/aud are verified on decode (api/platform/postgres.py), so a
# token minted for another audience — or a pre-hardening token carrying neither —
# is rejected and the holder is forced to log in again.
TOKEN_ISSUER = "guildos"
TOKEN_AUDIENCE = "guildos"
TOKEN_TTL_DAYS = 7

# Setup codes: unambiguous alphabet (no I/O/0/1) so a code can be read aloud or
# copied off a screen without transcription errors. 32**8 ~= 1.1e12 combinations,
# and codes are single-use, expire in 7 days, and are rate-limited on redemption.
SETUP_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SETUP_CODE_LENGTH = 8
SETUP_CODE_TTL_DAYS = 7

# Sliding-window rate limits for the two unauthenticated surfaces.
RATE_LIMIT_WINDOW_MINUTES = 15
RATE_LIMIT_MAX_PER_EMAIL = 10
RATE_LIMIT_MAX_PER_IP = 20

# Generic failure text. Unknown email and wrong password return this identical
# response so neither confirms whether an account exists.
INVALID_CREDENTIALS = "Invalid credentials"

# A real bcrypt hash of a value nobody can supply. Checked against when the email
# is unknown so that path costs the same ~100ms as a wrong-password path and the
# timing does not distinguish the two.
_DUMMY_HASH = bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt()).decode("utf-8")


def _issue_member_token(member_id: str, token_version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    return pyjwt.encode(
        {
            "sub": member_id,
            "iat": now,
            "exp": now + timedelta(days=TOKEN_TTL_DAYS),
            "iss": TOKEN_ISSUER,
            "aud": TOKEN_AUDIENCE,
            "ver": int(token_version or 0),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )


def _generate_setup_code() -> str:
    return "".join(secrets.choice(SETUP_CODE_ALPHABET) for _ in range(SETUP_CODE_LENGTH))


def _hash_secret(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_secret(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed stored hash — a non-match, not a 500.
        return False


def _parse_ts(value) -> datetime:
    """Coerce a timestamptz from either client (datetime via psycopg, ISO string
    via PostgREST) into an aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    # Unparseable — treat as already expired rather than trusting it.
    return datetime.min.replace(tzinfo=timezone.utc)


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


def _issue_setup_code(sb, *, chapter_id: str, member_id: str) -> tuple[str, str]:
    """Create a setup code for a member. Returns (plaintext_code, expires_at_iso).

    Only the bcrypt hash is stored; the plaintext is returned to the caller once
    and never recoverable afterwards.
    """
    code = _generate_setup_code()
    expires_at = datetime.now(timezone.utc) + timedelta(days=SETUP_CODE_TTL_DAYS)
    sb.table("member_setup_codes").insert({
        "chapter_id": chapter_id,
        "member_id": member_id,
        "code_hash": _hash_secret(code),
        "expires_at": expires_at.isoformat(),
    }).execute()
    return code, expires_at.isoformat()


def _recent_failures(sb, *, column: str, value: str) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)
    result = (
        sb.table("login_attempts")
        .select("id", count="exact")
        .eq(column, value)
        .eq("success", False)
        .gte("created_at", cutoff.isoformat())
        .execute()
    )
    return result.count or 0


def _enforce_rate_limit(sb, *, email: str, ip: str | None) -> None:
    """Raise 429 once this email or IP has burned through its failure budget."""
    if _recent_failures(sb, column="email", value=email) >= RATE_LIMIT_MAX_PER_EMAIL:
        raise HTTPException(429, "Too many attempts")
    if ip and _recent_failures(sb, column="ip", value=ip) >= RATE_LIMIT_MAX_PER_IP:
        raise HTTPException(429, "Too many attempts")


def _record_attempt(sb, *, email: str, ip: str | None, success: bool) -> None:
    """Record one authentication attempt.

    Best-effort: a logging failure must never take login down, so the insert is
    swallowed. The enforcing read in _enforce_rate_limit is not.
    """
    try:
        sb.table("login_attempts").insert({
            "email": email,
            "ip": ip,
            "success": success,
        }).execute()
    except Exception:
        pass


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    """
    Authenticate a member. Role plays no part in this flow (imp-one-gate.md D2).

    - Any member with a password_hash must supply the password.
    - Any member without one gets a grace token plus password_setup_required and
      is expected to call set-password immediately.
    - Only active members can log in; invitees must redeem their setup code
      first, so an unclaimed invite cannot be taken over by email alone.

    Unknown email and wrong password return an identical 401, so the endpoint
    never confirms whether an account exists. The 403 PASSWORD_REQUIRED reveal is
    the one deliberate exception — the login form needs it to know when to show
    the password field — and it is rate-limited like any other failure.
    """
    normalized_email = str(body.email).strip().lower()
    ip = _client_ip(request)
    sb = get_db()

    _enforce_rate_limit(sb, email=normalized_email, ip=ip)

    result = (
        sb.table("members")
        .select("id, name, email, role, chapter_id, password_hash, token_version")
        .eq("email", normalized_email)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )
    member = result.data if result else None

    if not member:
        # Equalize timing against the wrong-password path below.
        if body.password:
            _check_secret(body.password, _DUMMY_HASH)
        _record_attempt(sb, email=normalized_email, ip=ip, success=False)
        raise HTTPException(401, INVALID_CREDENTIALS)

    if member.get("password_hash"):
        if not body.password:
            _record_attempt(sb, email=normalized_email, ip=ip, success=False)
            raise HTTPException(403, detail={
                "message": "Password required for officer login",
                "code": "PASSWORD_REQUIRED",
            })
        if not _check_secret(body.password, member["password_hash"]):
            _record_attempt(sb, email=normalized_email, ip=ip, success=False)
            raise HTTPException(401, INVALID_CREDENTIALS)

    token = _issue_member_token(member["id"], member.get("token_version"))
    _record_attempt(sb, email=normalized_email, ip=ip, success=True)

    response = {"access_token": token, "token_type": "bearer"}
    if not member.get("password_hash"):
        response["password_setup_required"] = True

    return response


@router.post("/dev-login")
async def dev_login(body: LoginRequest):
    """Passwordless local dev login for direct-Postgres demo environments."""
    # Hard lockout on any deployed surface: preview URLs are public and inherit
    # env vars, so a stray DEV_AUTH_BYPASS must not be enough to open this door.
    if settings.is_deployed:
        raise HTTPException(404, "Not found")
    if not settings.DEV_AUTH_BYPASS:
        raise HTTPException(404, "Not found")

    normalized_email = str(body.email).strip().lower()
    sb = get_db()
    result = (
        sb.table("members")
        .select("id, name, email, role, chapter_id, token_version")
        .eq("email", normalized_email)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )
    member = result.data if result else None
    if not member:
        raise HTTPException(401, "No active member found with that email")

    return {
        "access_token": _issue_member_token(member["id"], member.get("token_version")),
        "token_type": "bearer",
    }


@router.post("/set-password")
async def set_password(body: SetPasswordRequest, user=Depends(get_current_user)):
    """Set or change the caller's own password (any authenticated member).

    Bumps token_version, which revokes every other outstanding session for this
    member, and returns a fresh token so the caller stays logged in.
    """
    sb = get_db()
    result = sb.rpc("au_set_password", {
        "p_member_id": user["id"],
        "p_password_hash": _hash_secret(body.password),
    }).execute()

    token_version = (result.data or {}).get("token_version", 0)

    return {
        "message": "Password set successfully",
        "access_token": _issue_member_token(user["id"], token_version),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserProfile)
async def get_me(user=Depends(get_current_user)):
    """Get current user's profile."""
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "chapter_id": user["chapter_id"],
        "chapter_name": (user.get("chapters") or {}).get("name"),
    }


@router.post("/invite")
async def invite_members(
    body: InviteRequest,
    officer=Depends(require_permission("members:invite")),
):
    """Invite new chapter members by email.

    Invitees are created with status 'invited', not 'active': they cannot log in
    by email alone, which closes the "whoever knows the email first claims the
    account" hole. Each invitee gets a single-use setup code, returned in
    plaintext exactly once for the officer to hand over out of band.
    Duplicate emails are reported in failed.
    """
    sb = get_db()
    invited: list[str] = []
    setup_codes: list[dict] = []
    failed: list[dict] = []
    chapter_id = officer["chapter_id"]

    for raw in body.emails:
        email = str(raw).strip().lower()
        local = email.split("@", 1)[0]
        name = local.replace(".", " ").replace("_", " ").strip().title() or "Member"
        try:
            result = sb.table("members").insert({
                "chapter_id": chapter_id,
                "name": name,
                "email": email,
                "role": "member",
                "status": "invited",
                # NULL unless the officer affirmed a signed opt-in (#57).
                "sms_consent_at": (
                    datetime.now(timezone.utc).isoformat() if body.sms_consent else None
                ),
            }).execute()
            if result.data:
                row = unwrap_row(result)
                code, _expires_at = _issue_setup_code(
                    sb, chapter_id=chapter_id, member_id=row["id"]
                )
                invited.append(email)
                setup_codes.append({"email": email, "setup_code": code})
            else:
                failed.append({"email": email, "error": "Insert failed"})
        except Exception as exc:
            failed.append({"email": email, "error": str(exc)})

    return {"invited": invited, "setup_codes": setup_codes, "failed": failed}


@router.post("/redeem-setup-code")
async def redeem_setup_code(body: RedeemSetupCodeRequest, request: Request):
    """Redeem an invite or password-reset code.

    Activates an invited member and returns a session with
    password_setup_required, so the member lands straight on password setup.
    Every failure — unknown email, wrong code, expired code, already-used code —
    returns the same generic 401, so this endpoint is not an oracle for which
    emails or codes exist.
    """
    normalized_email = str(body.email).strip().lower()
    ip = _client_ip(request)
    sb = get_db()

    _enforce_rate_limit(sb, email=normalized_email, ip=ip)

    def _reject() -> HTTPException:
        _record_attempt(sb, email=normalized_email, ip=ip, success=False)
        return HTTPException(401, INVALID_CREDENTIALS)

    result = (
        sb.table("members")
        .select("id, chapter_id, status, token_version")
        .eq("email", normalized_email)
        .in_("status", ["invited", "active"])
        .maybe_single()
        .execute()
    )
    member = result.data if result else None
    if not member:
        raise _reject()

    now = datetime.now(timezone.utc)
    codes = (
        sb.table("member_setup_codes")
        .select("id, code_hash, expires_at, used_at")
        .eq("member_id", member["id"])
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )

    matched_id = None
    for row in codes.data or []:
        if row.get("used_at"):
            continue
        if _parse_ts(row.get("expires_at")) <= now:
            continue
        if _check_secret(body.code, row["code_hash"]):
            matched_id = row["id"]
            break

    if not matched_id:
        raise _reject()

    # Single-use claim + invite completion, atomic in the RPC. A lost race
    # (concurrent or replayed redemption) returns claimed=false and lands on the
    # same generic 401 as every other failure.
    claim = sb.rpc("au_consume_setup_code", {
        "p_chapter_id": member["chapter_id"],
        "p_code_id": matched_id,
    }).execute()
    if not (claim.data or {}).get("claimed"):
        raise _reject()

    _record_attempt(sb, email=normalized_email, ip=ip, success=True)

    return {
        "access_token": _issue_member_token(member["id"], member.get("token_version")),
        "token_type": "bearer",
        "password_setup_required": True,
    }


@router.post("/reset-code/{member_id}")
async def issue_reset_code(
    member_id: str,
    officer=Depends(require_permission("members:invite")),
):
    """Issue a password-reset setup code for a member of the officer's chapter.

    This is the documented officer-assisted reset path: the officer hands the
    code over out of band and the member redeems it at /redeem-setup-code.
    Bumping token_version revokes the member's existing sessions immediately,
    which is the point when the reason for the reset is a lost or shared device.
    """
    sb = get_db()
    result = (
        sb.table("members")
        .select("id, chapter_id")
        .eq("id", member_id)
        .eq("chapter_id", officer["chapter_id"])
        .maybe_single()
        .execute()
    )
    member = result.data if result else None
    if not member:
        # Same 404 for "no such member" and "member of another chapter".
        raise HTTPException(404, "Member not found")

    code, expires_at = _issue_setup_code(
        sb, chapter_id=member["chapter_id"], member_id=member["id"]
    )

    sb.rpc("au_bump_token_version", {
        "p_chapter_id": member["chapter_id"],
        "p_member_id": member["id"],
    }).execute()

    return {"setup_code": code, "expires_at": expires_at}

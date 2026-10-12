# M0 — Security fixes

> Read `00-README.md` first. Test first. Stay in your lane.

**Goal:** close the P0 authority and input holes before any UI work (D10, D11, D13).
**Spec:** `../00-phase-a-audit.md` §5; `../audit/rbac.md` §4; `../audit/auth-members.md` §8; `../audit/treasury.md` §3.
**Migrations:** 0219 only.
**Allowed files:** `migrations/0219_role_grant_subset_rule.sql`; `api/rbac/api/roles.py`; `api/auth/api/auth.py`; `api/auth/api/schemas.py`; `api/treasury/api/payments.py`; `api/treasury/services/payments.py`; `api/treasury/api/schemas.py`; new `api/treasury/core/image_sniff.py`; `api/chapters/services/onboarding.py`; `api/chapters/api/chapters.py`; `api/chapters/api/schemas.py` (if the response model lives there); `scripts/seed.py`; new/changed tests under `tests/rbac/`, `tests/auth/`, `tests/treasury/`, `tests/chapters/`, `tests/test_seed_guard.py`.

## T1 — Grant only what you hold (D11)

Live body: `rbac_assign_role` in `0164_rbac_admin_tier.sql:71` (verify with grep). Today any `roles:assign` holder can assign any non-top role, including to self.

- [ ] Failing tests, `tests/rbac/test_grant_subset.py` (use `sb_client`, `chapter_id`, `member_factory`, and the `_assign` helper shape from `tests/rbac/test_authority.py`):
  - an `officer` assigning `treasurer` to self → raises with message `rbac_grant_exceeds_actor`;
  - an `officer` assigning `treasurer` to another member → same error;
  - an `officer` assigning `social_chair` to another member → succeeds (officer holds all 8 of its keys);
  - an `admin` assigning `treasurer` → succeeds;
  - the admin/president ceiling and last-admin tests in `tests/rbac/test_authority.py` still pass unchanged.
- [ ] `migrations/0219_role_grant_subset_rule.sql`: `CREATE OR REPLACE FUNCTION rbac_assign_role(...)` with the 0164 live body plus, after the chapter check and before the ceiling check: compute the actor's effective permission set (`member_roles` ∪ `'member'` → `role_permissions`) and the target role's set; if the target set is not a subset → `RAISE EXCEPTION 'rbac_grant_exceeds_actor'`. Admin passes trivially. Same rule inside `ch_import_roster` (live body `0163_roster_import_role.sql:4`): add `p_actor_id UUID DEFAULT NULL` as the LAST parameter so the existing call keeps working, and apply the rule only when an actor is given. Keep signatures otherwise identical.
- [ ] `api/rbac/api/roles.py:_map_role_error`: map `rbac_grant_exceeds_actor` → 403 "You can only grant roles whose permissions you already hold". Also map "unknown role" and "member not in chapter" DB errors → 404 (today they are 500s; audit §4).
- [ ] `api/chapters/services/onboarding.py` roster import passes the acting officer's id into `ch_import_roster`.
- [ ] API test in `tests/rbac/test_grant_subset.py`: POST `/api/rbac/members/{self}/roles {"role_key":"treasurer"}` as an officer → 403.
- [ ] Checkpoint: `python3 -m pytest tests/rbac tests/chapters -q`.

## T2 — `/set-password` requires the current password

`api/auth/api/auth.py:305-324`. Exception: a session that came from `/redeem-setup-code` has no password yet.

- [ ] Failing tests, `tests/auth/test_set_password_requires_current.py`: (a) a member with a password calling `/set-password` without `current_password` → 422; (b) with a wrong one → 403 and the password is unchanged; (c) with the right one → 200 and the new password logs in; (d) a freshly redeemed member (no `password_hash`) may set without `current_password`; (e) a password over 72 bytes → 422.
- [ ] `SetPasswordRequest` gets `current_password: str | None = None` and a max length. In the handler: if the member row has a `password_hash`, require and bcrypt-check it (reuse `_check_secret`); otherwise allow.
- [ ] Checkpoint: `python3 -m pytest tests/auth -q`.

## T3 — Evidence upload: content sniff, pending-only, cap

`api/treasury/services/payments.py` (`add_submission_evidence`, near `MAX_EVIDENCE_BYTES`) and `api/treasury/api/payments.py:136-167`.

- [ ] Failing tests, `tests/treasury/test_evidence_validation.py`: `text/plain` bytes → 415; a PNG header with client type `image/jpeg` → stored type is `image/png`; HEIC (`....ftypheic`) → accepted as `image/heic`; evidence on an approved submission → 409; a 4th file on one submission → 409; 2 MiB cap still 413.
- [ ] Implement a pure `sniff_image_type(data: bytes) -> str | None` in `api/treasury/core/image_sniff.py` (PNG `\x89PNG\r\n\x1a\n`, JPEG `\xff\xd8\xff`, HEIC/HEIF `ftyp` at offset 4 + brand in `heic heix hevc hevx mif1 msf1`). Service: ignore client `content_type`, store the sniffed one, 415 if `None`; `submission.status == 'pending'` else 409; existing evidence rows ≥ 3 → 409. Route maps the new domain errors.
- [ ] Checkpoint: `python3 -m pytest tests/treasury/test_v1_balance_submissions.py tests/treasury/test_evidence_validation.py -q`.

## T4 — Chapter signup must not return the setup code (D10)

`api/chapters/services/onboarding.py:85`, `api/chapters/api/chapters.py:28-57`, `tests/chapters/test_create_chapter.py`.

- [ ] Failing test: `POST /api/chapters` (bootstrap path) response JSON has no `setup_code` key; an outbox row of type `SETUP_CODE` exists for the officer.
- [ ] Remove the code from the bootstrap response. Keep the `PLATFORM_SECRET` path returning it (provisioning scripts rely on it) — test that too.
- [ ] Update existing tests that read the code from the response to read it from the test DB (`member_setup_codes`) the way `tests/auth/test_invite_setup_codes.py` does.
- [ ] Checkpoint: `python3 -m pytest tests/chapters -q`.

## T5 — Seeded demo admin password

`scripts/seed.py:34` hard-codes `demo-officer-pw`; prod `DATABASE_URL` points at the demo DB (CLAUDE.md).

- [ ] Failing test `tests/test_seed_guard.py`: running the seed entrypoint without `SEED_PASSWORD` exits non-zero before touching the DB (pattern: `tests/test_set_officer_password.py`).
- [ ] `seed.py` reads `SEED_PASSWORD` (required, ≥ 12 chars) and never embeds a literal.
- [ ] HUMAN FOLLOW-UP in your report: the live demo admin password must be rotated with `scripts/set_officer_password.py` by the user (their go-ahead; the DB is what prod points at). Do not run it.
- [ ] Checkpoint: `python3 -m pytest tests/test_seed_guard.py tests/test_set_officer_password.py -q`.

## Definition of done

All checkpoints green; `python3 scripts/migration_checksums.py --check` passes; the M0 acceptance row in `../02-phase-c-priorities.md` holds; report lists the password-rotation follow-up.

## Risks

- The subset rule changes who may hand out `treasurer`/`secretary`: only admins in practice. This is the chosen behaviour (D11). Say so in the 0219 header comment.
- Existing roster-import tests that assign roles without an actor must keep passing (actor is optional).

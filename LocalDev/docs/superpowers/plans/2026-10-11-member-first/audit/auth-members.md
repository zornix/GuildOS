# Audit: auth, sessions, accounts, members, onboarding

Read-only audit of `LocalDev/` on 2026-10-11 (main @ 80e4f8b). Paths are relative to `LocalDev/`.
**FACT** means I read it in code or migrations, or queried the demo database read-only. **INFERENCE** means a reasoned conclusion that I did not run end to end.

---

## 1. Login flow, end to end

| Step | Where | Notes |
|---|---|---|
| Endpoint | `POST /api/auth/login` (`api/auth/api/auth.py:204-272`, mounted `api/index.py:185`) | Body `{email, password?}` (`api/auth/api/schemas.py:4-6`). |
| Rate limit (checked first) | `auth.py:225`, `_enforce_rate_limit` `:180-185` | Counts **failures** in the last 15 min from the `login_attempts` table. The limits are 10 per email and 20 per IP (`:41-43`). The IP is the rightmost trusted `X-Forwarded-For` entry (`:102-125`). FACT |
| Lookup | `auth.py:227-234` | `members WHERE email=? AND status='active'`. Email is globally unique (`members_email_key`), so one account belongs to exactly one chapter. FACT |
| Password check | bcrypt 5.0.0 (`auth.py:75-84`, `requirements.txt`) | Unknown emails are checked against a dummy hash so the timing matches (`:52`, `:237-242`). A missing password returns 403 `PASSWORD_REQUIRED` (`:244-250`). Passwordless legacy rows can never log in (`:254-267`). FACT |
| Token minted | `_issue_member_token` `auth.py:55-68` | HS256 over `settings.JWT_SECRET`. Claims: `sub`=members.id, `iat`, `exp`=now+**7 days** (`TOKEN_TTL_DAYS=7`, `:31`), `iss`=`aud`=`"guildos"` (`:29-30`), `ver`=members.token_version. FACT |
| Verification | `_LocalAuth.get_user` `api/platform/postgres.py:630-659` | Algorithms are pinned to `["HS256"]`. aud and iss are verified. `exp`, `sub`, `aud` and `iss` are required. FACT |
| Per-request session check | `get_current_user` `api/dependencies.py:6-39` | Decodes the token, reloads the member row (`status='active'`, joined to `chapters`), then compares `ver` with `members.token_version`. A mismatch returns **403** "Session no longer valid" (`:36-37`). A deactivated member gets 403 "No active membership found" (`:29-30`). FACT |

- **Refresh or renewal:** there is none. There is no refresh token, no renewal endpoint and no sliding expiry. A session always ends 7 days after login. The only calls that hand out a new token are `/login`, `/redeem-setup-code` and `/set-password` (`auth.py:320-324`). FACT
- **Lifetime is not configurable.** `TOKEN_TTL_DAYS` is a module constant, not a field in `Settings` (`api/config.py` has no TTL field). `tests/auth/test_tokens.py:87-89` pins 6 days < TTL ≤ 7 days, with the comment "7-day TTL, not the old 30 days". FACT
- **Client storage:** `localStorage['g_token']` (`greekos/src/api.ts:5`, written at `:54` and `:80`, read at `:150`). There are no cookies and no sessionStorage for the token. sessionStorage is used only for the parked check-in code (`App.tsx:31`, `:57-59`). FACT
- **What survives a browser restart:** the token, for its full 7 days. `App.tsx:25` treats "a token exists" as signed in, without decoding or checking `exp`. FACT
- **Logout:** client-side only. `logout()` deletes the localStorage key (`api.ts:15-17`, `App.tsx:38`). There is no server logout endpoint, so a copied token stays valid until it expires or `ver` is bumped. FACT
- **Revocation:** the `members.token_version` epoch (migration `0148_auth_hardening.sql:25`). These operations bump it:
  - `au_set_password` (`0191_auth_code_lifecycle.sql:3-28`)
  - `au_bump_token_version`, used by the officer reset code (`0191:30-54`, called at `auth.py:502-506`)
  - `au_consume_setup_code`, used when a code is redeemed (`0191:56-95`)
  - `scripts/set_officer_password.py:30-33`

  Each bump kills **all** of the member's sessions. Per-session revocation does not exist. Removing a role needs no bump, because permissions are re-read on every request (`api/rbac/auth.py:31-37`). FACT
- **Frontend bug (FACT):** a revoked or stale session comes back as **403**, but the client clears the token only on **401** (`api.ts:169-172`, `:201-204`). On load, `useAppData.ts:185-188` therefore shows "Can't reach the chapter server" (`AppShell.tsx:103-106`) and keeps the dead token in storage. Every reload repeats this until the member clicks Sign out. Even on a 401, `logout()` runs but `App`'s `authed` state is not reset, so the same banner shows until a reload.

## 2. Account creation

There is **no open self-registration for members**. Accounts are created in five ways (FACT):
1. **Officer invite:** `POST /api/auth/invite`, requires `members:invite` (`auth.py:340-399`). The RPC `au_invite_member` (`0161_invite_atomicity.sql:12-35`) inserts the member with `status='invited'` and a bcrypt-hashed 8-character code (7-day TTL, `auth.py:36-38`). The plaintext code goes back to the officer and is also emailed through the outbox (`api/auth/notifications.py:31-74`).
2. **Roster CSV import:** `POST /api/chapters/{id}/roster`, requires `members:invite` (`api/chapters/api/chapters.py:60-86`, `api/chapters/services/onboarding.py:154-193`). Each row becomes an invited member with a setup code.
3. **Self-serve chapter signup:** `POST /api/chapters`, **unauthenticated**, rate-limited in process to 3 per IP and 20 total per hour (`api/chapters/auth.py:29-57`, `chapters.py:28-57`). `ch_create_chapter` (`0164_rbac_admin_tier.sql:16-69`) creates the chapter and an invited officer with roles `officer` and `admin`. **The setup code is returned in the HTTP response** (`onboarding.py:85`) as well as emailed.
4. **Scripts:**
   - `scripts/provision_chapter.py` (prompted password, active officer)
   - `scripts/seed.py` (demo; every member gets the password `demo-officer-pw`, `seed.py:34`)
   - `scripts/set_officer_password.py` (password reset by email)
5. **Dev login:** `POST /api/auth/dev-login` (`auth.py:275-302`). It returns 404 on any deployed host or when `DEV_AUTH_BYPASS` is off, and the boot guard refuses `DEV_AUTH_BYPASS` in production (`api/index.py:54-55`).

**Claiming an account:** `POST /api/auth/redeem-setup-code` (`auth.py:402-473`) takes email and code, and is rate-limited and generic-401 like login. It activates `invited` members, bumps `ver`, and returns a full 7-day token with `password_setup_required: true`. Then `POST /api/auth/set-password` (`auth.py:305-324`) requires a session, accepts any password of 8 or more characters (`schemas.py:9-17`), and **does not ask for the current password**. FACT

**Password reset:** officer-assisted only. `POST /api/auth/reset-code/{member_id}` requires `members:invite` and is chapter-scoped (`auth.py:476-514`). It bumps `ver`, burns old codes, and issues and emails a new code. There is **no self-service "forgot password" email**. The "Forgot password?" link (`LoginScreen.tsx:137-140`) only tells the member to ask an officer. FACT

**Email verification:** there is none. No `email_verified` column, no verification token table, and no email-change flow. A member cannot change their own email, and officers cannot edit it either: no endpoint updates `members.email`. Redeeming an emailed code indirectly proves the member owns the inbox for invites and roster rows. For self-serve chapter signup it proves nothing, because the code comes back to whoever submitted the form. FACT (no matches for `email_verified` or `verify` in the migrations or `api/`.)

## 3. The `members` table, final state

From migrations `0001`, `0002`, `0004`, `0148`, `0157`, confirmed read-only against the demo DB `information_schema` (FACT):

| column | type | null | default | origin |
|---|---|---|---|---|
| id | uuid | no | gen_random_uuid() | 0001:33 |
| chapter_id | uuid FK chapters ON DELETE CASCADE | no | | 0001:34 |
| name | text | no | | 0001:35 |
| email | text **UNIQUE (global)** | no | | 0001:36 |
| phone | text, CHECK E.164 `members_phone_e164` | yes | | 0001:37, 0149:144-162 |
| role | text CHECK in ('officer','member'), display-only | no | 'member' | 0001:38-43 |
| status | text CHECK in ('active','inactive','alumni','invited') | no | 'active' | 0001:39, 0148:60-63 |
| created_at | timestamptz | no | now() | 0001:40 |
| auth_id | uuid (legacy Supabase link, still read by `rbac_request_chapter_id`) | yes | | 0002:5, 0082:67 |
| password_hash | text (bcrypt) | yes | | 0004:5 |
| token_version | int | no | 0 | 0148:25 |
| sms_consent_at | timestamptz | yes | | 0157:16-18 |
| sms_opted_out_at | timestamptz | yes | | 0157:16-18 |

- **No class, pledge-class, grad-year or year column exists.** FACT. I searched migrations, `api/` and `greekos/src`. Migration `0149:68` adds `phone_unparsed`, but that column is **absent** in the demo DB even though `0149` is recorded as applied. That is schema drift; the cause is an INFERENCE (most likely the migration was edited after it was applied).
- **Frontend placeholders:** `Member.memberClass` ("Fall '22"), `gpa`, `major` and `roomNumber` exist only in `greekos/src/types.ts:32-40`. `adapters.ts:76-83` hard-codes `gpa: 0`, `memberClass: ''` and `phone: ''`. These are rendered in `RosterModule.tsx:126,142,148` ("0 GPA", "Room N/A"), `FinanceModule.tsx:362`, `DuesRunModal.tsx:130` and `EventsModule.tsx:1163` ("GPA: 0"). FACT. That breaks the frontend rule "nothing on screen the server did not return" (INFERENCE, judgment).
- **Issue #115 (open, not scheduled)** defines the intended meaning: the term a member joined, such as "Fall 2024". The plan is a `members.member_class` column set from a CSV column, edited by officers with the same permission as role assignment, and set by members at account creation. FACT
- **Who can edit what today (FACT):**

  | Field | How it changes |
  |---|---|
  | `role` | `PUT /api/members/{id}/role` (`roles:assign`, `api/members/api/members.py:79-129`, RPC `mem_set_legacy_role`) and the RBAC role endpoints |
  | `status` | Only invited→active, on redeem |
  | `sms_*` | Self opt-in (`members.py:59-76`), Twilio STOP (`api/announcements/api/twilio_inbound.py:98,105`), signup and import flags |
  | `password_hash` / `token_version` | The auth endpoints and scripts above |

  **No endpoint edits name, email, phone or status.** There is no deactivate and no move-to-alumni.
- **Where the columns feed logic:**
  - `status` gates login, sessions and the roster (`dependencies.py:24`, `members.py:20`).
  - `role` is display-only by rule.
  - Standing uses fines and unexcused absences only (`api/memberadmin/core/standing_rules.py`). No class or year input exists anywhere.

## 4. Member self-service

| Action | Endpoint | Gate |
|---|---|---|
| Read own profile (id, name, email, role, chapter_id, chapter_name) | `GET /api/auth/me` (`auth.py:327-337`, `api/members/api/schemas.py:4-10`) | any session |
| Read roster (id, name, email, role, status for the whole chapter, including invitees) | `GET /api/members/` (`members.py:25-56`) | any session; `sms_consent` is shown only for your own row unless you hold `members:invite` |
| Opt in to SMS | `POST /api/members/me/sms-consent` (`members.py:59-76`) | own row only, id from the token |
| Set or change password | `POST /api/auth/set-password` | any session, **no current password required** |
| Own permissions | `GET /api/rbac/me/permissions` | any session |

All facts above are from code. In addition (FACT):
- There is **no profile update endpoint** of any kind (name, phone, email).
- There is **no in-app SMS opt-out**; opting out happens only by replying STOP.
- Phone is never returned to the client. `list_members` does not select it, and `/me` omits it.
- Officer-only: invite, roster import, reset code (`members:invite`), role change (`roles:assign`), standing and scores (`standing:view_all`), reminders (`standing:remind`).

## 5. Onboarding

- **Backend:** "onboarding" means **chapter** onboarding only (`api/chapters/services/onboarding.py`: create chapter plus CSV import). There is no profile-completeness concept, no onboarding flag and no `onboarded_at` column. FACT
- **The only "must finish setup" signal** is `password_setup_required: true` on the redeem response (`auth.py:472`). It is not persisted. FACT
- **`OnboardingScreen.tsx`** is the pre-login "Start a chapter" form. It sends `POST /api/chapters` through `createChapter` (`api.ts:101-131`), then shows the setup code once (`OnboardingScreen.tsx:46-66`) and sends the officer back to sign-in to redeem it. It is reached only from `LoginScreen`'s "New here? Start a chapter" link (`App.tsx:34-36`). Its visibility is plain React state (`App.tsx:26`), so nothing can make it repeat. No flag exists or is needed. FACT
- **Gap (INFERENCE):** after a redeem, the token is already in localStorage (`api.ts:54`). If the member closes the tab on the "Choose a password" step, the reload lands in the app (`App.tsx:25`) with a full 7-day session and no password. Once it expires they are locked out until an officer issues a reset code. The redeem token is not scoped to set-password only.

## 6. Multi-tenant isolation

- **chapter_id binding (FACT):** the token carries only `sub`. `chapter_id` comes from the member row loaded on every request (`dependencies.py:20-27`) and never from the client. Every member and auth route reads `user["chapter_id"]`:
  - `members.py:39` (list)
  - `auth.py:362` (invite) and `:493` (reset, with the same 404 for "other chapter")
  - `chapters.py:71` (roster: path id must equal the session chapter)
  - `memberadmin/api/scores.py:58,68` and `services/member_detail.py:24-25`
  - `mem_set_legacy_role` (tenant guard inside the RPC, mapped at `members.py:126-128`)
- **RLS on `members`:** **not enabled**. `relrowsecurity=false` and there are no policies on the demo DB, and no `ENABLE ROW LEVEL SECURITY` for `members` appears in the migrations. This matters less than it sounds: the app connects as the owner, and Supabase API roles hold no grants on `members` (I checked `role_table_grants`). `member_setup_codes` has RLS with a chapter SELECT policy (`0148`). `login_attempts` has RLS with deny-all (`0148`). FACT
- **Cross-chapter risks:**
  1. **Email squatting through unauthenticated chapter signup** (FACT plus INFERENCE). Email is globally unique, and `POST /api/chapters` needs no proof of email ownership because the code comes back in the response. Anyone can register a real person's email as the officer of a junk chapter. That person then **cannot be invited or imported** by their real chapter: roster import says "Member cannot be invited" (`onboarding.py:166-173`) and invite says "Could not invite this address". Chapter names are globally unique too (`0164:34-36`), so a name can be squatted the same way. The in-process limit (`chapters/auth.py:26-31`) is per worker and resets on a cold start.
  2. **Email existence oracle** (FACT). `POST /api/chapters` returns 409 for any existing member email (`0164:37-39`, `chapters.py:49-55`), and the roster import reports foreign-chapter emails as row errors. This is unauthenticated and limited only by the in-process rate limit.
  3. One person cannot belong to two chapters, because email is the login key and is globally unique. That is a product constraint rather than a leak. FACT
  4. Every current route I read is chapter-scoped correctly. I found no IDOR. FACT

## 7. Existing tests

| File | Invariants asserted |
|---|---|
| `tests/auth/test_login_password.py` | A hashed member must supply the correct password. Passwordless rows never get a token. Unknown email and wrong password look identical. Invited members cannot log in. 10 failures trigger the limit, 9 do not. Failures are recorded. Covers a regression where an attacker could set a password and take over an account. |
| `tests/auth/test_tokens.py` | set-password bumps the epoch and returns a working token. Hardened claims (sub, ver, iat, iss/aud, TTL ≤ 7d). Missing or wrong aud, iss or sub returns 401. A stale `ver` returns **403** with the exact message. |
| `tests/auth/test_invite_setup_codes.py` | Invites create invited rows with codes, storing only the hash. Redeem activates and authenticates. Codes are single-use. Every redeem failure is the same 401. Redeem is rate-limited. A reset revokes sessions and refuses other chapters. Reset needs an officer. A duplicate email fails only that address. Atomicity: no row without a code. Legacy passwordless members recover through a reset. |
| `tests/auth/test_code_lifecycle.py` | Setting a password burns unused codes. A reset burns older codes. Redeem revokes earlier sessions. |
| `tests/auth/test_code_emails.py` | Every code is queued as an email. Reset has its own event type. The outbox never shows a code. Enqueue failures are logged without the code. Inside a transaction, enqueue failure raises. |
| `tests/auth/test_client_ip.py` | X-Forwarded-For parsing. A spoofed leftmost entry cannot open a new rate-limit bucket. |
| `tests/auth/test_rpc_privileges.py` | `au_*` and repo functions are not PUBLIC-executable. |
| `tests/members/test_list_consent.py` | Roster consent visibility (own row vs `members:invite`). Opt-out overrides consent. |
| `tests/chapters/test_create_chapter.py` | Signup writes the chapter, officer and admin role. Redeem activates. Phone validation. 409s write nothing and look identical. PLATFORM_SECRET works and a bad secret is 401. Bootstrap is rate-limited. Rollback when the code cannot be issued. |
| `tests/chapters/test_roster_import.py` | All-or-nothing import. Roles, with admin and president refused. Consent column. Skip vs reject. Another chapter is unreachable. Size limit. Non-officers refused. Rollback. Generic foreign-email error. |
| `tests/memberadmin/*` | Standing and score inputs (fines in cents, started events only, excuses), reminder dedup, prior security shifts. |
| `tests/config/test_production_guard.py` | Production boot refuses a default or short JWT_SECRET, DEV_AUTH_BYPASS, a missing DATABASE_URL and similar. |
| `tests/test_set_officer_password.py` | The script guards prod, bumps `ver`, burns codes and rolls back atomically. |
| `greekos/src/lib/auth.test.ts`, `session.test.ts` | Code normalization, the redeem→password step, error copy, form validation, `can()`. |

**Gaps (FACT, no test found for these):**
- An expired token returning 401.
- The frontend handling a 403 for a stale session.
- set-password with a password over 72 bytes.
- `GET /api/auth/me` and the members list across chapters.
- dev-login being locked out on a deployed host.

## 8. Security concerns

1. **Token in localStorage with no CSP** (FACT). Any XSS can read and exfiltrate a 7-day bearer token. `vercel.json:25-30` sets nosniff, DENY, Referrer-Policy and HSTS but no `Content-Security-Policy`. The XSS surface is small: I found no `dangerouslySetInnerHTML`, `innerHTML` or `eval` in `greekos/src`, and no server-rendered HTML apart from one redirect (`api/attendance/api/checkin_page.py:17`). Severity: medium, INFERENCE.
2. **set-password needs no current password** (FACT, `auth.py:305-324`). Anyone holding a token (XSS, a shared laptop, a forgotten sign-out) can set a new password. That revokes the owner's sessions and leaves the attacker with persistent access. Severity: high, INFERENCE.
3. **Logout does not revoke anything server-side** (FACT). Sign-out on a shared machine only forgets the token locally.
4. **Login rate limiting exists**: DB-backed, 10 failures per email or 20 per IP in 15 minutes (`auth.py:40-43`, `:180-201`). Two weaknesses (FACT):
   - The limit is checked before the password, so 10 bad attempts lock the real user out for 15 minutes. Anyone can trigger this targeted lockout.
   - `login_attempts` has no pruning job (no other references), so it grows without bound.

   The chapter-signup limit is in process only.
5. **Weak password policy** (FACT). Length 8 or more is the only rule (`schemas.py:13-14`). There is no maximum, and bcrypt 5.0 **raises ValueError above 72 bytes**, which I reproduced locally. In `/set-password` that is unhandled, so it would return a 500 (INFERENCE). `_check_secret` swallows the error on login.
6. **The seeded demo admin uses the committed password** (FACT). `jake@tke.org` (role officer, status active, roles admin, president and treasurer) has `demo-officer-pw` (`scripts/seed.py:34`) on the demo DB, which I verified with bcrypt. `CLAUDE.md` says the **production** DATABASE_URL currently points at that demo DB. So the live site accepts a sign-in from anyone who has read the repo. The repo is private on GitHub, which lowers the risk without removing it.
7. **Unauthenticated chapter signup** allows email and chapter-name squatting and gives an email existence oracle (§6). FACT plus INFERENCE.
8. **No email verification** anywhere (§2). FACT
9. **No audit rows for credential changes** (FACT). The `au_*` RPCs write no `audit_logs` (`0191`), despite the hard rule that trust-boundary RPCs write audit rows. Password sets, resets and redeems leave only `login_attempts`.
10. **Good practices already in place** (FACT): the algorithm is pinned; aud and iss are required; the JWT_SECRET boot guard demands 32+ characters and no dev default (`index.py:22,45`); dev-login is hard-404 when deployed; Swagger is off when deployed; CORS is limited to `FRONTEND_URL`; codes are stored only as hashes, single-use, and wiped from the outbox; responses are generic and timing-equalized; Sentry runs with `include_local_variables=False`.

---

## Assessment: should we add "Remember me"?

**What exists today:** every login is already "remembered". The token sits in `localStorage` for a fixed 7 days, survives restarts, and is never renewed. So a checkbox can only make two meaningful changes:

- **Unchecked: forget on close.** This one has real value for a shared or lab computer. It is a frontend-only change: write the token to `sessionStorage` instead of `localStorage`.
- **Checked: stay signed in longer.** This one needs the backend. Today an active member is logged out hard on day 7 regardless of activity, so "remember me" cannot mean more than that without a longer `exp` or a renewal.

**The smallest honest version is frontend only, with no backend change.**
1. Add a checkbox, "Keep me signed in on this device for 7 days", in `LoginScreen`. Pick the default and say so.
2. `authPost` writes the token to `localStorage` when the box is checked and to `sessionStorage` otherwise. `ensureLogin`, `App.tsx:25` and `authPost(withToken)` read from either. `logout` clears both.
3. Redeem and set-password follow the same choice. The simplest rule is that the redeem step defaults to `sessionStorage` until the password is saved.
4. Caveat: `sessionStorage` is per tab. A check-in link opened in a new tab will ask for sign-in again. The code is parked (`App.tsx:31`), so it still works after sign-in.
5. Fix the 403 bug in the same change: treat a 403 "Session no longer valid" or "No active membership" like a 401. Otherwise a remembered but revoked session reads as "server down". Add a `lib/` test.

**Optional backend change, if "remember" must mean longer than 7 days:** add `remember: bool = False` to `LoginRequest` and give `_issue_member_token` a TTL parameter (for example 12 hours unremembered and 30 days remembered). Make both values `Settings` fields so they are configurable. Revocation still works through `token_version` and the per-request status check: a password change, officer reset or deactivation kills even a 30-day token. That is about 10 lines plus a test change, because `test_tokens.py:87-89` pins the 7-day TTL. It reverses a deliberate hardening ("not the old 30 days"), so it should be an explicit decision.

**What a checkbox does not fix:** XSS exposure. Both storages are readable by script. Only an HttpOnly cookie changes that, which is a bigger change (CSRF, cookie config, `allow_credentials` is already on). Server-side logout also remains missing. Before making sessions longer, I would first require the current password on `/set-password` and add a CSP. A longer-lived token makes concern #2 worse.

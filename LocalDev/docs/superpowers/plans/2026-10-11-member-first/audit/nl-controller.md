# NL controller audit (read-only), 2026-10-11

Scope: `api/nl_controller/**`, `greekos/src/components/CommandModule.tsx`, `command-copy.test.ts`,
`lib/parseWhen.ts`, the command executor in `hooks/useAppData.ts`, related tests and migrations.
All paths are relative to `LocalDev/`. Tags: **[FACT]** means read in code. **[INFERENCE]** means a reasoned conclusion that was not run or not fully traced.

## 0. Headline

The "NL controller" is two halves that are **not connected**. [FACT]

1. **The backend** (`api/nl_controller`, about 140 LOC) records raw text into `command_requests` and lets an approver flip its status. It has no parser and no executor, and the frontend never calls it. `greekos/src/api.ts` has no `nl-controller` function (grep shows no hits).
2. **The frontend "Command console"** is a hand-rolled regex parser inside a React component. It runs entirely in the browser and fires the same domain hooks the normal UI uses.

There is no natural language and no LLM anywhere. The UI copy says so on purpose (`command-copy.test.ts:11`).

## 1. Architecture

### Backend (dead surface) [FACT]

- Mounted at `/api/nl-controller` (`api/index.py:137,205`).
- `GET /commands?status=` lists rows. It needs `nl_controller:execute` or `nl_controller:approve` (`api/nl_controller/api/commands.py:16-21`).
- `POST /commands {input_text: str(min 1)}` inserts a row with `proposed_actions: []` and `status: pending_approval` (`commands.py:24-34`, `services/commands.py:10-26`, `api/schemas.py:8-9`).
- `POST /commands/{id}/review {decision: approve|reject}` takes the `pending_approval` row to `approved` or `rejected`. It is scoped to the chapter and returns 404 when no row matches (`commands.py:37-52`, `services/commands.py:29-54`). On approve, nothing executes (TODO at `services/commands.py:50-53`).
- Table `command_requests`: status enum includes `executed`/`failed`, plus an `executed_at` column that nothing writes (`migrations/0089_nl_controller_tables.sql:5-20`). RLS is select-only by chapter. It is defense-in-depth only, since the app connects as the owner.
- The design intent lives in `docs/services/future-agents.md:24-30` ("parser → typed proposed_actions → approve → executor calls service functions").
- A stale `api/nl_controller/api/__pycache__/router.cpython-314.pyc` exists with no `router.py` source. It is harmless residue.

### Frontend (the real thing) [FACT]

- Tab `command` is gated by `nl_controller:execute` (`greekos/src/config/navigation.ts:31`) and rendered at `App.tsx:243-249`.
- The flow is **confirm the raw text first, then parse, then execute**:
  1. On submit, `setPendingCommand(raw text)` runs (`CommandModule.tsx:285`).
  2. `ConfirmDialog` shows the *raw string* and a generic warning (`:366-375`).
  3. On Run, `handleRunCommand` parses (`:52-251`) and calls `onExecuteCommand({type, payload, summary})`.
  4. That reaches `useAppData.handleExecuteCommand`, a switch that dispatches to domain hooks (`hooks/useAppData.ts:210-252`).
- **There is no preview of the parsed action.** The officer confirms the text, never the resolved member, amount in cents, date or recipients. There is no dry-run.
- Execution is fire-and-forget. The command log entry is written as `Sent` synchronously, before any server response (`:83-88`, `:119-124`, etc.). Server errors surface only through the hooks' toasts.

## 2. Grammar (complete list) [FACT]

Each branch matches on a lowercase prefix or substring, then runs a regex. Rules are tried in order and **fall through** on failure.

| # | Intent | Trigger / regex | Example | Notes |
|---|---|---|---|---|
| 1 | FINE | `startsWith('fine ')`, `/fine\s+([a-zA-Z\s]+?)\s+\$?(\d+)(?:\s+for\s+(.+))?/i` (`:61-62`) | `fine Cody Jenkins $25 for missing chapter` | Whole dollars only. Default reason is `'Bylaws Infraction Citation'` (`:66`). Goes to `finance.handleIssueFine` → `submitTransaction` → `createInvoice` with `source:'fine'` (`lib/transaction.ts:71-76`). |
| 2 | TASK | `startsWith('assign ')`, `/assign\s+(.+?)\s+to\s+([a-zA-Z\s]+)/i` (`:98-99`) | `assign Living Room Sweep to Cody Jenkins` | **`dueDate` is hardcoded `'2026-07-16'`** (`:113`), which is already in the past. Priority is `Medium`, so `required:false` (`hooks/useTasks.ts:29`). |
| 3 | EVENT | `startsWith('schedule ')`, `/schedule\s+(.+?)(?:\s+on\s+(.+?))?(?:\s+at\s+(.+))?$/i` (`:134-135`) | `schedule Poker Night on Friday at 8pm` | Date and time go through `parseWhen`, which refuses rather than guesses (`lib/parseWhen.ts`). Hardcoded `location:'Fraternity House'`, `type:'Brotherhood'`, `end = start+2h % 24` (`:150`), so a 23:00 start gets a 01:00 end on the same date. The `jobs` payload is dropped by `toEventBody` (`adapters.ts:188-209`). |
| 4 | ANNOUNCEMENT | `lower.includes('announcement')` (`:195`). The prefix strip is `/^(?:send\|post\|broadcast)\s+announcement:?\s*/i` | `send announcement: suit and tie tomorrow` | Fixed title `'Chapter announcement'`. Calls `createAnnouncement` then `sendAnnouncement` (`useAppData.ts:225-240`). |
| 5 | EXCUSE_APPROVE | `lower.includes('approve excuse')`, `/approve\s+excuse\s+for\s+([a-zA-Z\s]+)/i` (`:222-224`) | `approve excuse for Devin Brooks` | With no name, the name becomes the literal `'brother'`. The executor picks the first *pending* excuse whose `memberName` contains the text (`useAppData.ts:245`). |
| – | "extend bid to NAME" | **No parser.** It was removed in `ea00d43` (recruitment removal). | – | **Dead intent**, but still advertised in the help text (`:266`) and the template chip (`:47`), and **pinned by the test** (`command-copy.test.ts:13`). It always errors. It is also leftover recruitment vocabulary. |
| – | ATTENDANCE | In the type union only (`:20`, `useAppData.ts:211`) | – | Never produced. Dead. |

**Parameter extraction** [FACT]
- **Names:** `members.find(m => m.name.toLowerCase().includes(raw))`. This is a substring match where the first hit wins, with no ambiguity check (`:67`, `:103`). The character class `[a-zA-Z\s]` rejects names with an apostrophe or hyphen (O'Brien, Smith-Jones) and accented names.
- **Money:** `\$?(\d+)` then `parseFloat`, then `Math.round(*100)`. It is not anchored, so `fine Al $25.50 for late` gives **$25 with the default reason**. The `.50` silently breaks the `for` group. [FACT from the regex. INFERENCE on the exact runtime result.]
- **Dates:** only for `schedule`, via `parseWhen`. It accepts today, tomorrow, a weekday prefix of at least 3 letters, "July 17" and ISO dates. Times accept 8pm, 8:30 pm, 19:00, noon and midnight. It is well built and tested (`lib/parseWhen.test.ts`).

**Error messages** [FACT]
- An unknown command shows `'Not a supported command. See the list above.'` (`:249`).
- An unreadable schedule date shows `Couldn't read a date/time from "<raw>"` (`:145`).
- **Wrong message:** a fine or assign whose member is not found falls through and reports "Not a supported command" instead of "no member matches X".

**Correctness bugs** (ranked)
1. **Fall-through into an announcement** [FACT, from tracing the code path]. Any input containing "announcement" that an earlier rule did not consume is published as a chapter announcement, with the *entire raw text* as the body. Example: `assign announcement flyers to Zed` where no member matches "Zed" publishes "assign announcement flyers to Zed" to the chapter feed. The confirm dialog shows only the raw text, so the officer cannot see it is about to become an announcement.
2. **Ambiguous member substring on a money path** [FACT]. `fine Al $50` fines whichever member containing "al" comes first in roster order (e.g. "Alex", "Sal", "Kalvin").
3. **Decimal fine amounts are silently truncated, and the reason is replaced with the default** [FACT].
4. **Task due date is hardcoded in the past** (`:113`) [FACT].
5. **False claims on screen** [FACT]:
   - The announcement summary says "Dispatched SMS & Calendar announcement blast" (`:206`), and the confirm dialog mentions "texts" (`:370`). But `an_send_announcement` has no outbox (`migrations/0188_announcement_no_outbox.sql`); it publishes to the feed and audits only.
   - The excuse branch logs "Approved" even when no matching pending excuse exists. The executor silently no-ops (`useAppData.ts:245-248`).
   - Both break the CLAUDE.md rule "Nothing on screen that the server did not return".
6. **Wrong end time** for events starting at 22:00 or later (`:150`) [FACT].
7. The `events` prop is unused (`:17,28`) [FACT].

## 3. Authorization [FACT]

- `nl_controller:execute` is granted to officer, president and vice_president. `nl_controller:approve` is granted to president, plus admin's blanket grant (`migrations/0083_rbac_seed_rpcs.sql:75,98,110`; `docs/services/permissions-matrix.md:93-94`).
- **In the frontend console, that key only hides or shows the tab.** Every action goes through the normal REST endpoint with the caller's own session, so each endpoint re-checks its own key:

| Action | Endpoint and permission check |
|---|---|
| Fine | `POST` invoices, `require_permission(treasury:invoice:create)` (`api/treasury/api/invoices.py:82`) |
| Task | `tasks:create` |
| Event | `calendar:event:create` |
| Announcement | `announcements:create` + `announcements:send` (`api/announcements/api/announcements.py:50,184-186`) |
| Excuse | `attendance:excuse:review` |

- The same services and RPCs as the normal UI run, so chapter guards, idempotency and audit rows hold.
- **No privilege escalation path exists.** The console cannot do anything the user could not already do by clicking.
- **Gate mismatch:**
  - treasurer has `treasury:invoice:create` but not `nl_controller:execute` (`0083:115-120`, `0147:75-87`), so the treasurer, the natural fine-issuer, cannot see the console. [FACT]
  - A role with `nl_controller:execute` but without the action key sees templates that 403 on Run. [INFERENCE: per-role grants after 0147 were not fully traced.]
- The backend `/api/nl-controller` endpoints are correctly gated and chapter-scoped, but unused.

## 4. Audit logging [FACT]

- The underlying RPCs write `audit_logs` as normal: e.g. `an_send_announcement` (`0188:34`), and the treasury invoice RPC with its ledger row.
- **Nothing records that an action came from the console, or what text produced it.** `command_requests` is never written by the UI.
- The command log is React state, so it is lost on reload ("Commands run in this session", `:332`). Failed or unparseable attempts are not recorded anywhere. That means there is **no data on how often parsing fails**, which is the number that decides between options A and B.

## 5. LLM / AI [FACT]

- `grep -rniE "openai|anthropic|llm|gpt|claude|haiku|sonnet"` over `api/`, requirements, `config.py` and `.env.example` finds no SDK, no key and no config. The only hits are comments citing CLAUDE.md and regex `fullmatch`.
- Project rule: "No fabricated business logic … return not_implemented" (CLAUDE.md). The bylaws Q&A follows that stub contract.

## 6. UI [FACT]

- **Input:** a single `<input type=text>` with autofocus (`:288-296`).
- **Help:** a one-paragraph syntax line (`:264-268`), plus 6 template chips that fill the box (`:43-50`, `:308-320`).
- **Missing:** autocomplete, member-name suggestions, inline validation and per-field errors.
- **Confirmation:** a generic danger dialog showing the raw text (`:366-375`). It does not show the parsed result.
- **Result:** a row in the in-memory log with a Sent or Error badge. Server success or failure arrives separately as a toast from `syncApi` or `handleIssueFine`.
- **History:** session-only, newest first. It is not persisted and not shared with other officers.

## 7. Tests and gaps [FACT]

**Existing tests**
- Backend: `tests/services_scaffold/test_route_registration.py:43` checks the route is mounted. `tests/services_scaffold/test_schemas.py:40-43` checks the `CommandReview` decision enum. There are no service or DB tests for nl_controller.
- Frontend:
  - `command-copy.test.ts` checks the help copy only, and pins the dead "extend bid" string.
  - `lib/parseWhen.test.ts` gives good coverage of date and time parsing.

**Gaps**
- **The command parser has zero tests.** It lives inside a component, against the CLAUDE.md rule "New logic goes in `lib/` with a test".
- There are no tests for name ambiguity, the fall-through to an announcement, decimal money, or executor no-ops.

## 8. Code quality

**Size** [FACT]

| Part | LOC |
|---|---|
| `CommandModule.tsx` | 378, of which about 200 are parser and executor logic |
| `parseWhen.ts` | 63 |
| Executor switch in `useAppData.ts` | ~45 (`:210-252`) |
| Backend `nl_controller` | ~140, including the migration |

- **Style:** hand-rolled `if startsWith` plus regex, with duplicated history-push blocks (about 5 copies). It is *under*-engineered, not over-engineered: no shared intent type, `payload: any`, and parse is mixed with UI.
- **The backend is speculative scaffolding.** It is an approval workflow for a parser that does not exist. [FACT/INFERENCE]
- **Dead code:** the "extend bid" intent (help text, template, test), the `ATTENDANCE` type, the unused `events` prop, the stale `router.pyc`, and the whole backend `/api/nl-controller` surface from the UI's point of view.

---

# Options

## Assumptions (all INFERENCE)

- **Only officers use the console**, since it is gated by `nl_controller:execute`. So "5 active users per chapter" is an upper bound; 1–3 is likelier.
- **Volume:** 2–5 commands per user per day, 30 days a month.
- **Monthly commands:**

| Chapters | Commands per month |
|---|---|
| 1 | 300–750 |
| 5 | 1,500–3,750 |
| 20 | 6,000–15,000 |

- **Pricing:** from the claude-api skill model table, cached 2026-10-06:
  - Claude Haiku 5.5 (`claude-haiku-5-5`): $0.10 per million input tokens and $0.50 per million output tokens, for prompts up to 100K tokens.
  - Claude Sonnet 5.5: $2 / $10.
  - Haiku 5.5 has no server-side refusal fallback.

## A. Improve the deterministic parser (recommended now)

**Work**

1. Move parsing into `lib/command.ts` as a pure `parseCommand(text, members, now) → {intent, params} | {error, field}`. Write a table-driven `command.test.ts`.
2. **Anchor on the leading verb** and remove the `includes('announcement')` and `includes('approve excuse')` fall-through. That kills bug #1.
3. **Resolve names:**
   - Exact full name wins. Then a unique prefix or substring.
   - If there are several matches, error with "Al matches Alex Kim, Sal Ortiz — be more specific".
   - Widen the character class to `[\p{L}'\- ]`.
4. **Money:** `\$?(\d+(?:\.\d{1,2})?)` through the existing `dollarsToCents`. Anchor the regex. Add an upper bound check.
5. **Optional clauses:**
   - `assign … to NAME [by DATE]`, using `parseWhen`'s date half. Drop the hardcoded date; leave it null when absent.
   - `schedule … [at LOCATION]`. Clamp the end time, or leave it null.
6. **Preview before confirm:** parse first, then show the resolved action in `ConfirmDialog`. For example: "Fine **Cody Jenkins** $25.00 — missing chapter", or "Publish announcement to all members: …". Make the copy accurate: no SMS claim.
7. **Autocomplete:**
   - Native `<datalist>` of member names (ladder rung 4).
   - Or show a verb-specific hint line under the input as the user types, e.g. `fine NAME $AMOUNT for REASON`.
8. **Clean up dead code and fix copy:**
   - Delete `extend bid` and `ATTENDANCE`, and fix the test.
   - Mark a log row `Sent` only after the hook resolves, or relabel it as "Requested".
   - Make the excuse no-op an error.
9. **Optional:** log each attempt (text, parsed intent or error) to `command_requests` via the existing `POST /api/nl-controller/commands`. That gives audit provenance and measures the failure rate. Otherwise, delete the backend surface.

**Cost and risk**
- **Size:** about 150–250 LOC changed and about 100 LOC of tests; 1–2 dev-days.
- **Latency:** under 1 ms, client-side. **Cost:** $0.
- **Reliability:** deterministic and fully testable. The same input always gives the same action.
- **Maintenance:** each new intent is one table row plus tests.
- **Ceiling:** officers must learn about 6 verb shapes. Paraphrases like "give cody a 25 dollar fine" fail with a helpful error.

## B. Hybrid: deterministic first, small LLM fallback

**Shape**
- On parse failure, the client calls a **server** endpoint, e.g. `POST /api/nl-controller/parse`. This reuses the existing router and key, and the API key stays server-side.
- The endpoint makes **one** Messages call:
  - model `claude-haiku-5-5`
  - structured output (`output_config.format`) using the intent JSON schema
  - `effort: low`; no tools, no loop
- It returns `{intent, params}` as a **proposal only**.
- The client feeds the proposal through the *same* `lib/command.ts` validator and preview as option A. The officer confirms. Execution goes through the same endpoints. The attempt is logged to `command_requests`; it already has a `proposed_actions` JSONB column.
- **Prerequisite:** option A's typed intent schema. Generate the prompt and the JSON schema from that one source so the grammar does not drift.

**Tokens per request** [INFERENCE]

| Part | Tokens |
|---|---|
| System prompt (grammar + schema + about 8 examples) | ~1,000–1,500 |
| User text | ~20–40 |
| Output JSON (incl. any low-effort thinking) | ~80–300 |

The 1.5K prefix may sit below the minimum cacheable size, and at these prices caching does not matter.

**Per-call cost:**
- **Haiku 5.5:** about $0.00015 input + up to $0.00015 output, so **about $0.0002–0.0003 per call.**
- **Sonnet 5.5:** about $0.003 + $0.003, so **about $0.005–0.006 per call.**

**Monthly cost**, worst case where **every** command hits the LLM; the realistic fallback share is 10–30%:

| Chapters | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| 1 | $0.06–0.23 | $1.50–4.50 |
| 5 | $0.30–1.10 | $7.50–22 |
| 20 | $1.20–4.50 | $30–90 |

The token cost is negligible. The real costs are:
- an `anthropic` dependency and a `Settings` field for the key, plus a decision on handling it in Prod;
- a privacy decision (member names, fine reasons and announcement text go to a third party);
- a 0.5–2 s added latency on the fallback path;
- outage and refusal handling (fall back to the parser's error);
- an eval set of about 50–100 real phrasings to maintain;
- about 250–400 LOC plus tests, 3–5 dev-days.

**Security**
- **Injection surface:** keep it to the officer's own text by sending **no roster, event titles or chapter data** in the prompt. Self-injection gains nothing beyond what the UI already permits. If roster names were in the prompt, a member's display name could become an injection vector.
- **The model never authorizes anything.** Permissions are enforced by the existing endpoints with the user's own session; the model never holds elevated credentials.

The validator must guarantee:
1. Strict schema: `additionalProperties:false`, and `intent` is in the fixed enum of existing intents.
2. Every `amount` is an integer number of cents, more than 0 and at most a cap (e.g. $500).
3. A member is a *name string* resolved server- or client-side to exactly one active member of the caller's chapter. The model never supplies an ID.
4. Dates and times are re-parsed by `parseWhen`, or validated as ISO and not in the past.
5. Free-text fields (reason, title, announcement body) are length-capped and must be **verbatim substrings of the user input**, so the model cannot author content.
6. There is always a human preview and confirm, and no auto-execution.
7. Each user is rate-limited (e.g. 20/min, 200/day) to bound cost and abuse.
8. Input, proposal and outcome are logged to `command_requests`.

## C. Bounded agent workflows (tools + approval + budget caps)

- **Shape:** a tool loop over per-domain tools. A multi-step plan is shown for approval, with per-task token and dollar caps.
- **Cost:** 3–8 model calls of about 5–20K tokens each, so about **$0.002–0.01 per task on Haiku 5.5, or $0.05–0.30 on Sonnet 5.5**. That is still small in dollars.
- **Complexity is high:**
  - tool definitions for each domain;
  - plan or approval UI;
  - partial failure, since endpoints do not share a transaction, so a half-executed plan needs a compensation story;
  - evals, and budget enforcement.
  - About 1–3k LOC and weeks of work.
- **Justified only** for genuinely multi-step goals, e.g. the "event-prep orchestrator" in `docs/services/future-agents.md` ("set up the formal: event + 3 jobs + announcement draft"). It is not justified for single-action commands.

## Recommendation

**Do A now.** It fixes real defects on a money path (ambiguous member, truncated amount, accidental announcement) and adds the missing preview, for $0 and with deterministic tests.

**Move to B only when** the logged attempts (A step 9) show more than ~10–15% of real attempts failing to parse over about 4 weeks across at least 2 chapters, *and* officers are actually using the console. Most failures should be paraphrases, not typos a hint line would fix. Use Haiku 5.5. The validator above is non-negotiable.

**Move to C only if** a multi-step workflow such as event prep becomes a product requirement. Single commands never need it.

**Separately decide the fate of the backend `nl_controller`:** either repurpose it as the command attempt and audit log, which is the cheap A step 9, or remove it as dead scaffolding.

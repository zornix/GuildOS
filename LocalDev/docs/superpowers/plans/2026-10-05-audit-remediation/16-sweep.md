# 16 · Sweep: fixed error messages, dead code out, plan-speak out of comments

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Do exactly what each step says; if a step cannot be done as written, stop and report instead of improvising.

**Stream:** `16-sweep` · **Wave:** 4 (after every other code stream is merged) · **Agent:** Gemini 3.8 Flash medium (Antigravity CLI) · **Branch:** `fix/audit-16-sweep`
**Findings:** F-064, R-06, F-071, and the comment residue from report §8
**Goal:** no HTTP response contains raw exception text; symbols nothing calls are gone; comments describe the code, not the plan that produced it.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-064, F-071, §8, Appendix C.4 (R-06).

## Global constraints

- Behaviour must not change except the text of error messages named in Task 1. No migration. No route path changes. No renames of anything that is still used.
- Before deleting any symbol, prove it has no caller: `grep -rn "<name>" api scripts tests greekos/src` must show only its definition (and, where the task says so, the tests listed).
- Run `python3 -m pytest <the test folders named in each task> -q` after each task and `python3 -m ruff check api scripts tests` at the end. Not the full suite.
- Commands run from `LocalDev/`.

## Review focus

1. A message a user relies on to understand what to do (for example "Already checked in") must stay just as informative after Task 1.
2. Status codes do not change.
3. Nothing deleted in Task 2 is imported anywhere (run `python3 -c "import api.index"`).
4. Task 3 changes comments and docstrings only: `git diff` for those files must show no changed code line.

---

### Task 1: F-064 and R-06 — fixed messages, details in the log

**Files:** `api/platform/errors.py` (new), `tests/platform/test_errors.py` (new), and the call sites listed below

- [ ] **Step 1: failing test**

```python
from api.platform.errors import public_message


def test_known_fragment_maps_to_its_fixed_text():
    known = {"already checked in": "Already checked in", "not found": "Not found"}
    assert public_message(Exception("event 123 not found in chapter 9"), known, "Not allowed") == "Not found"


def test_unknown_error_gets_the_default_and_no_internal_text():
    out = public_message(Exception('duplicate key value violates unique constraint "x_pkey"'), {}, "Could not save")
    assert out == "Could not save"
```

- [ ] **Step 2: implement** `api/platform/errors.py`:

```python
"""Turn an internal exception into a fixed, user-safe message. The original goes to the log."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def public_message(exc: Exception, known: dict[str, str], default: str) -> str:
    text = str(exc)
    for fragment, message in known.items():
        if fragment in text:
            return message
    logger.warning("unmapped error surfaced as %r: %s", default, text)
    return default
```

- [ ] **Step 3: apply it at each site.** At every site: keep the status code, replace the interpolated exception text. Where a `known` map is needed, build it from the messages the code can actually receive: for an RPC, open its live definition (`docs/superpowers/plans/2026-10-05-audit-remediation/fn-index.txt` says which migration) and list its `RAISE EXCEPTION` texts; write one short fixed sentence per text, without ids.

| Site | Today | Change to |
|---|---|---|
| `api/treasury/api/fines_legacy.py` waive handler (`f"Fine not found or not waivable: {exc}"`) | 404 + raw text | 404 `"Fine not found or cannot be waived"` |
| `api/treasury/api/payments.py` reallocate handler (`f"Reallocation failed: {exc}"`) | 409 + raw text | 409 via `public_message` with the `tr_reallocate_payment` messages; default `"Reallocation could not be applied"` |
| `api/treasury/api/invoices.py` void handler (`f"Invoice cannot be voided: {exc}"`) | 409 + raw text | 409 via `public_message` with the `tr_void_invoice` messages; default `"Invoice cannot be voided"` |
| `api/auth/api/auth.py` invite loop (`failed.append({"email": email, "error": str(exc)})`) | raw text per row | `"error": "Could not invite this address"`, and `logger.warning` the real error |
| `api/attendance/api/attendance.py` and `api/attendance/api/excuses.py` `_rpc_http_error` | returns `msg` verbatim | same status rules; message via `public_message` with the `at_set_attendance` / `at_review_excuse` / `at_checkin_self` messages; default `"That change is not allowed"`. Move the one function to `api/attendance/api/errors.py` and import it in both files |
| `api/initiatives/services/initiatives.py` (`raise InitiativesError(msg)` for `member_not_in_chapter`, and the bare `raise` after it) | cross-chapter id surfaces as 500 | add `class MemberNotInChapter(InitiativesError)`; raise it for `member_not_in_chapter`; in `api/initiatives/api/initiatives.py::_map_domain_errors` map it to 404 `"Member not found"`. The exceptions already mapped there carry our own text; leave them |
| `api/treasury/api/reports.py` (`HTTPException(400, str(exc))` for `ValueError`) | our own validation text | leave as is |

  Then search for any others: `grep -rnE "HTTPException\([0-9]+, *f[\"'].*\{exc" api` and `grep -rnE "HTTPException\([0-9]+, *str\(exc\)" api`. Fix each the same way, or list it in the report with the reason you left it.
- [ ] **Step 4: tests.** For each changed site there is an existing test that triggers the error (find it with `grep -rn "<old message fragment>" tests`); update its expected text. Add one test for the initiatives 404.
- [ ] **Step 5: run `python3 -m pytest tests/platform tests/treasury tests/auth tests/attendance tests/initiatives -q`. Checkpoint** — suggested message `fix(api): error responses carry fixed messages, not exception text`.

---

### Task 2: F-071 — remove what nothing calls

For each symbol: run the grep from "Global constraints". Delete it only if the result matches the "expected callers" column. Otherwise leave it and report what you found.

| Symbol | File | Expected callers | Action |
|---|---|---|---|
| `Page` | `api/treasury/api/pagination.py` | none | delete the file |
| `idempotency_operation` | `api/treasury/core/idempotency.py` | only `# noqa: F401 (contract anchor)` imports | delete the file and those imports |
| `incomplete_required_tasks` | `api/tasks/services/tasks.py` (~170-180) | none | delete the function |
| `current_request_id` | `api/observability.py` | none (stream 14 added a logging filter that reads the context variable directly) | delete the function |
| `_LocalAuthAdmin` and `self.admin` | `api/platform/postgres.py` | none | delete the class and the attribute |
| contract-anchor import | `api/treasury/services/invoices.py:10`, `api/treasury/api/invoices.py` (`TreasuryMessage  # noqa: F401`) | none | delete the unused imports |
| `AuditLogger`, `LedgerWriter` | `api/treasury/core/audit.py`, `api/treasury/core/ledger.py` | only `tests/treasury/test_chunk0_foundations.py` | do NOT delete. Add to each class docstring: `Test fixture only. Production writes go through tr_* RPCs.` |

- [ ] Run `python3 -c "import api.index"` and `python3 -m pytest tests/treasury tests/tasks tests/config tests/services_scaffold -q`. **Checkpoint** — `chore: remove symbols with no callers`.

---

### Task 3: comments say what the code does

- [ ] List the plan-speak: `grep -rnE "Chunk [A-H0-9]|B4FEND|imp-[a-z]|decision #[0-9]|checklist [0-9]\.[0-9]|spec §[0-9]" api --include=*.py`. About 50 lines.
- [ ] For each hit, rewrite the comment or docstring so it states the rule or the reason in plain words and drops the identifier. Example: `# decision #5 (void/waive is Treasurer only)` → `# Only a treasurer may void or waive an invoice.` If you cannot tell what the identifier meant, delete just the identifier and keep the rest of the sentence. Do not touch SQL migrations, tests, or any code line.
- [ ] Check: `python3 -m compileall -q api` succeeds, `python3 -m ruff check api` passes, `python3 -c "import api.index"` succeeds, and in `git diff -U0` every changed line is a `#` comment or docstring text. **Checkpoint** — `docs(api): comments describe behaviour instead of plan identifiers`.

## Report

Finish with the report block from `00-README.md` ("What to hand back").

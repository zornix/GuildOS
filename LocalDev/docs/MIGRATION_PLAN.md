# Backend DDD Migration Plan

This plan outlines the steps required to migrate the remaining legacy flat-module architecture (`api/routes/`, `api/models/schemas.py`, `api/services/`) into the new Domain-Driven Design (DDD) pattern (`api/<domain>/`).

**Guiding Principles:**
1. **Behavior-preserving**: Migrations should not change API contracts or break the frontend unless explicitly noted.
2. **One route at a time**: Move logic handler-by-handler to ensure `npm run test:e2e` remains green.
3. **Canonical Shape**: Every new domain must adhere to the standard structure (`api/`, `services/`, `core/`, `db/`).

---

## Phase 1: Complete Partial Conformances

Both the **Events** and **Attendance** domains have their new package boundaries established, but their handlers still reside in the legacy `api/routes/` folder.

### 1. Events Domain (`api/events/`)
- **Move Handlers**: Migrate `api/routes/events.py` handlers into `api/events/api/events.py`.
- **Move Schemas**: Extract `EventCreate`, `EventUpdate`, and `EventResponse` from `api/models/schemas.py` to `api/events/api/schemas.py`.
- **Implement Service Layer**: Create `api/events/services/events.py` so route handlers become thin wrappers.
- **Enforce Visibility**: Apply `visibility` filtering (e.g., `visibility='officer'`) in list/get queries using `calendar:officer:view`.
- **Swap RBAC**: Replace `require_officer` with specific permissions like `require_permission(EVENT_CREATE)`.
- **Delete**: `api/routes/events.py`.

### 2. Attendance Domain (`api/attendance/`)
- **Move Handlers**: Relocate `attendance.py`, `excuses.py`, `checkin_links.py`, and `checkin_page.py` from `api/routes/` into `api/attendance/api/`.
- **Move Services**: Move `api/services/checkin_links.py` to `api/attendance/services/checkin_links.py`.
- **Move Schemas**: Migrate `PhoneCheckIn` and `ManualAttendance` to `api/attendance/api/schemas.py`.
- **Session Integration**: Update the check-in flow to stamp `session_id` on attendance rows natively. Make `closes_at` actively expire sessions rather than relying purely on the TTL of short links.
- **Swap RBAC**: Transition to `require_permission(ATTENDANCE_OVERRIDE)`, `CHECKIN_CREATE`, and `EXCUSE_REVIEW`.
- **Delete**: Legacy attendance/excuse routes.

---

## Phase 2: Migrate Standalone Entities (Members & Auth)

These modules are currently entirely in the legacy flat structure.

### 1. Directory/Members Domain (`api/members/`)
- **Setup Folder**: Create `api/members/api/router.py`, `api/members/api/members.py`, `api/members/api/schemas.py`.
- **Migrate Logic**: Move handlers from `api/routes/members.py`.
- **Schemas**: Move member representations.
- **RBAC**: Replace `require_officer` with specific member administration permissions (e.g., `members:view_all`, `members:update_role`).

### 2. Identity/Auth Domain (`api/auth/`)
- **Setup Folder**: Create `api/auth/api/router.py`, `api/auth/services/session.py`.
- **Migrate Logic**: Move `api/routes/auth.py`. 
- **Dependencies**: Keep shared JWT/authentication extractors in `api/dependencies.py` or move them explicitly to `api/auth/core/security.py` and export them.

---

## Phase 3: Consolidate Operations & Tasks

Currently, `api/routes/operations.py` acts as an event-prep template engine, while the new `api/tasks/` domain handles discrete task management. 

### 1. Operations Engine Migration
- **Merge into Tasks?**: The operations template engine (`api/services/operations.py`) generates task groups from templates. This logic should be moved into a new `api/tasks/services/templates.py`.
- **Move Handlers**: Move `api/routes/operations.py` endpoints to `api/tasks/api/operations.py` (or mount as `/api/operations` but backed by the tasks domain).
- **Cleanup**: Delete `api/routes/operations.py` and `api/services/operations.py`.

---

## Phase 4: Fines & Cron (Treasury Alignment)

The legacy `fines.py` and `cron.py` are the last holdouts interacting with the old financial system.

### 1. Fines & Automation
- **Move Fines**: Legacy `fines` are converted to Treasury invoices via the `FineToInvoice` bridge. Migrate `api/routes/fines.py` into `api/treasury/api/fines_legacy.py` (or a dedicated integration module) until the frontend shifts entirely to using standard Treasury invoices.
- **Move Fine Processor**: Move `api/services/fine_processor.py` into `api/treasury/services/fine_processor.py`. This processor should eventually just issue Treasury invoices directly based on `attendance.signals`.
- **Cron Jobs**: Create `api/cron/` as a lightweight trigger router that delegates immediately to domain services (e.g., calling `api/treasury/services/fine_processor.run_auto_fines()`). Delete `api/routes/cron.py`.

---

## Execution Checklist

1. [ ] Read `TREASURY_ARCHITECTURE.md` and `services/README.md` to internalize the target shape.
2. [ ] Execute Phase 1 (Events). Run tests.
3. [ ] Execute Phase 1 (Attendance). Run tests.
4. [ ] Execute Phase 2 (Members & Auth). Run tests.
5. [ ] Execute Phase 3 (Operations -> Tasks). Run tests.
6. [ ] Execute Phase 4 (Fines & Cron). Run tests.
7. [ ] Assert `api/routes/`, `api/services/`, and `api/models/schemas.py` are completely empty and delete the folders.
8. [ ] Update `docs/services/service-map.md` to reflect full conformance.

# Authority comes from member_roles, with an admin tier

## Context

Authority had two competing sources of truth: `member_roles` and a legacy `members.role` column. The permission resolver unioned both, so revoking an officer role through the RBAC API failed to revoke permissions (F-022). Any holder of `roles:assign` could grant themselves admin, president, or treasurer (F-023). Roster CSV import stamped `members.role = 'officer'` for any non-member title (F-006).

## Decision

Decided 2026-10-05 (decisions D8, D9; migrations 0162–0164, 0203):

1. **One source of truth:** Permissions are resolved solely from `member_roles`, plus an implicit `member` baseline. The `members.role` column is display-only and kept in sync by the RPCs.
2. **Admin tier:** The chapter creator becomes its initial `admin`. `admin` and `president` can only be granted or revoked by an admin. Multiple admins may exist; an admin can step down, but the last admin of a chapter cannot be removed.
3. **Backfill:** Existing chapters without an admin received their earliest active or invited officer as `admin`.

## Consequences

- Roster CSV import writes catalog roles to `member_roles`. It sets the legacy display column to `officer` only for an explicit `officer` role; other titles use `member`.
- By product decision D2, officers may still approve their own payments and credit their own account below the $500 threshold.
- Assign and revoke RPCs reject non-admin attempts to grant or revoke admin/president (403), and prevent deleting the final admin (409).

"""RBAC — the central permission foundation for every GuildOS domain.

Public surface:
  - api.rbac.auth.require_permission(...)  → FastAPI dependency factory
  - api.rbac.services.permissions.has_permission(member, permission, resource=None)
  - api.rbac.services.permissions.get_member_permissions(member)

No domain may hardcode role/permission checks inline; everything goes through
these helpers — `require_officer` and treasury's `require_capability` were
deleted by migration 0147. The legacy `members.role` column is display-only;
permissions come from `member_roles` via api.rbac, plus the implicit member
baseline every member always has.
"""

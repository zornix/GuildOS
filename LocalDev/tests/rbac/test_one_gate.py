"""One gate for authority — the swapped gates resolve through the catalog only.

`require_officer` and `require_capability` are gone (imp-one-gate.md D1/D3): the
authority that used to come from `members.role == "officer"` or a
`treasury_grants` row now comes from a permission key carried by a role in
`member_roles`. The bug class this pins: a member whose legacy `members.role` is
'member' but who holds 'officer' in `member_roles` was refused by the old
`require_officer` check and is admitted by `require_permission`.

No database: the supabase client is the system boundary and a minimal fake
stands in for it (same shape as test_permissions_service.py).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException

import api.rbac.services.permissions as permissions_service
from api.rbac.auth import require_permission

# Every key the one-gate swap put on a route, with the role that must carry it.
SWAPPED_KEYS = [
    "members:invite",
    "attendance:checkin_link:manage",
    "attendance:override",
    "attendance:excuse:review",
    "tasks:create",
    "roles:assign",
    "standing:view_all",
    "standing:remind",
    "treasury:fines:issue",
    "treasury:invoice:create",
    "treasury:payment:verify",
    "treasury:budget:view",
    "treasury:audit:view",
    "treasury:expense:create",
    "treasury:adjustment:create",
    "treasury:refund:create",
    "treasury:rebuild:run",
]

MIGRATION = (
    Path(__file__).resolve().parents[2] / "migrations" / "0147_authority_one_gate.sql"
)


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def execute(self):
        return _Result(self._rows)


class FakeSb:
    def __init__(self, member_roles, role_permissions):
        self._tables = {
            "member_roles": member_roles,
            "role_permissions": role_permissions,
        }

    def table(self, name):
        return _Query(self._tables[name])


def _officer_catalog():
    """The 0147 officer grant, as the resolver would read it back."""
    return FakeSb(
        member_roles=[{"role_key": "officer"}],
        role_permissions=[
            {"role_key": "officer", "permission_key": key} for key in SWAPPED_KEYS
        ],
    )


@pytest.fixture
def rbac_on_fake(monkeypatch):
    def _use(sb):
        monkeypatch.setattr(permissions_service, "get_db", lambda: sb)
        return sb

    return _use


# ── the bug class ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("permission", SWAPPED_KEYS)
async def test_member_holding_officer_via_member_roles_passes(rbac_on_fake, permission):
    """members.role == 'member', member_roles == ['officer'] → admitted.

    This is exactly the account the deleted `require_officer` refused.
    """
    rbac_on_fake(_officer_catalog())
    user = {"id": "m-1", "chapter_id": "c-1", "role": "member"}

    assert await require_permission(permission)(user=user) is user


@pytest.mark.parametrize("permission", SWAPPED_KEYS)
async def test_plain_member_still_refused(rbac_on_fake, permission):
    rbac_on_fake(
        FakeSb(
            member_roles=[{"role_key": "member"}],
            role_permissions=[
                {"role_key": "member", "permission_key": "bylaws:query"},
                {"role_key": "member", "permission_key": "tasks:complete"},
            ],
        )
    )
    user = {"id": "m-2", "chapter_id": "c-1", "role": "member"}

    with pytest.raises(HTTPException) as exc:
        await require_permission(permission)(user=user)
    assert exc.value.status_code == 403


async def test_legacy_officer_column_still_resolves(rbac_on_fake):
    """D6: LEGACY_ROLE_COMPAT stays, so an un-backfilled officer keeps access."""
    rbac_on_fake(
        FakeSb(
            member_roles=[],  # no granular assignment yet
            role_permissions=[
                {"role_key": "officer", "permission_key": "members:invite"}
            ],
        )
    )
    user = {"id": "m-3", "chapter_id": "c-1", "role": "officer"}

    assert await require_permission("members:invite")(user=user) is user


# ── the deleted gates ────────────────────────────────────────────────────────


def test_require_officer_is_gone():
    import api.dependencies as dependencies

    assert not hasattr(dependencies, "require_officer")


def test_treasury_capability_module_is_gone():
    assert importlib.util.find_spec("api.treasury.auth") is None


# ── catalog / code agreement ─────────────────────────────────────────────────


def test_new_keys_are_seeded_by_the_migration():
    """Keys are backend-owned: a route key with no catalog row is a dead gate."""
    sql = MIGRATION.read_text()
    for key in (
        "members:invite",
        "attendance:checkin_link:manage",
        "standing:remind",
        "treasury:expense:create",
        "treasury:adjustment:create",
        "treasury:refund:create",
        "treasury:rebuild:run",
    ):
        assert f"'{key}'" in sql, f"{key} is not seeded in 0147"


def test_route_constants_match_the_catalog_keys():
    from api.attendance.auth import CHECKIN_LINK_MANAGE
    from api.members.api.members import ROLES_ASSIGN
    from api.treasury.api import adjustments, expenses, invoices, payments, rebuild, refunds, reports

    assert CHECKIN_LINK_MANAGE == "attendance:checkin_link:manage"
    assert ROLES_ASSIGN == "roles:assign"
    assert adjustments.ADJUSTMENT_CREATE == "treasury:adjustment:create"
    assert refunds.REFUND_CREATE == "treasury:refund:create"
    assert rebuild.REBUILD_RUN == "treasury:rebuild:run"
    assert expenses.EXPENSE_CREATE == "treasury:expense:create"
    assert expenses.BALANCE_VIEW == "treasury:budget:view"
    assert invoices.INVOICE_CREATE == "treasury:invoice:create"
    assert payments.PAYMENT_REVIEW == "treasury:payment:verify"
    assert payments.RECEIPT_VIEW == "treasury:audit:view"
    assert reports.DASHBOARD_VIEW == "treasury:budget:view"
    assert reports.RECORD_VIEW == "treasury:audit:view"


def test_treasury_invoice_void_stays_off_the_officer_role():
    """0121 decision #5: void/waive is Treasurer only — 0147 must not widen it."""
    sql = MIGRATION.read_text()
    officer_block = sql.split("SELECT 'officer', x.perm FROM (VALUES", 1)[1].split(
        ") AS x(perm)", 1
    )[0]
    assert "treasury:invoice:void" not in officer_block

import { describe, expect, it } from "vitest";
import { NAV, OFFICER_ONLY, type NavItem } from "./navigation";

/** Mirrors the Sidebar filter: legacy officer gate + RBAC permission gate. */
function visibleNav(role: "officer" | "member", permissions: string[]): NavItem[] {
  return NAV.filter(
    (n) =>
      (!OFFICER_ONLY.includes(n.id) || role === "officer") &&
      (!n.requiredPermission || permissions.includes(n.requiredPermission)),
  );
}

describe("permission-aware nav filtering", () => {
  it("hides officer-only and permission-gated pages from a plain member", () => {
    const ids = visibleNav("member", ["tasks:complete"]).map((n) => n.id);
    expect(ids).not.toContain("standing");
    expect(ids).not.toContain("active-checkins");
    expect(ids).not.toContain("admin-roles");
    expect(ids).not.toContain("recruitment");
    expect(ids).toContain("tasks");
    expect(ids).toContain("announcements");
  });

  it("shows bylaws to a member with bylaws:query (the seeded member grant)", () => {
    const ids = visibleNav("member", ["bylaws:query"]).map((n) => n.id);
    expect(ids).toContain("bylaws");
  });

  it("shows admin-roles only with roles:assign, regardless of legacy role", () => {
    expect(visibleNav("officer", []).map((n) => n.id)).not.toContain("admin-roles");
    expect(visibleNav("member", ["roles:assign"]).map((n) => n.id)).toContain("admin-roles");
  });

  it("keeps the legacy OFFICER_ONLY gate working unchanged", () => {
    const ids = visibleNav("officer", []).map((n) => n.id);
    expect(ids).toContain("standing");
    expect(ids).toContain("active-checkins");
  });

  it("every gated NavItem uses a domain:action permission string", () => {
    for (const item of NAV) {
      if (item.requiredPermission) {
        expect(item.requiredPermission).toMatch(/^[a-z_]+:[a-z_:]+$/);
      }
    }
  });
});

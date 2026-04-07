"use client";
import { useEffect, useState } from "react";
import { AuthProvider, useAuth } from "./hooks/use-auth";
import { T } from "./lib/theme";
import { Icon } from "./components/ui/icon";
import { Avatar } from "./components/ui/avatar";
import { Badge } from "./components/ui/badge";
import { DashboardPage } from "./views/dashboard";
import { EventsPage } from "./views/events";
import { FinesPage } from "./views/fines";
import { MembersPage } from "./views/members";
import { StandingPage } from "./views/standing";

type PageId = "dashboard" | "events" | "fines" | "members" | "standing";

const NAV: { id: PageId; label: string; icon: string }[] = [
  { id: "dashboard", label: "Dashboard", icon: "home" },
  { id: "events", label: "Events", icon: "cal" },
  { id: "fines", label: "Fines", icon: "dollar" },
  { id: "members", label: "Members", icon: "users" },
  { id: "standing", label: "Standing", icon: "shield" },
];

function AppShell() {
  const { user, logout } = useAuth();
  const [page, setPage] = useState<PageId>("dashboard");

  const navItems = NAV.filter((n) => n.id !== "standing" || user.role === "officer");

  useEffect(() => {
    if (page === "standing" && user.role !== "officer") setPage("dashboard");
  }, [page, user.role]);

  return (
    <div style={{ display: "flex", height: "100vh", background: T.bg, fontFamily: "'Inter', -apple-system, sans-serif", color: T.tx, overflow: "hidden" }}>
      <div style={{ width: 220, background: T.sf, borderRight: `1px solid ${T.bd}`, display: "flex", flexDirection: "column", flexShrink: 0 }}>
        <div style={{ padding: "20px 16px", borderBottom: `1px solid ${T.bd}` }}>
          <div style={{ fontSize: 18, fontWeight: 800 }}><span style={{ color: T.ac }}>Fraternity</span>OS</div>
          <div style={{ fontSize: 10, color: T.txm, marginTop: 2, textTransform: "uppercase", letterSpacing: 1 }}>Operations Platform</div>
        </div>
        <nav style={{ flex: 1, padding: "12px 8px" }}>
          {navItems.map((n) => (
            <button
              key={n.id}
              onClick={() => setPage(n.id)}
              style={{
                width: "100%", display: "flex", alignItems: "center", gap: 10,
                padding: "10px 12px", borderRadius: 8, border: "none", cursor: "pointer",
                fontSize: 13, fontWeight: 500, marginBottom: 2,
                background: page === n.id ? T.ac + "22" : "transparent",
                color: page === n.id ? T.acl : T.txm,
              }}
            >
              <Icon type={n.icon} size={16} /> {n.label}
            </button>
          ))}
        </nav>
        <div style={{ padding: 12, borderTop: `1px solid ${T.bd}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 4px" }}>
            <Avatar name={user.name} size={28} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: T.tx, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.name}</div>
              <div style={{ fontSize: 10, color: T.txm, textTransform: "capitalize" }}>{user.role}</div>
            </div>
            <button onClick={logout} style={{ background: "none", border: "none", color: T.txm, cursor: "pointer", padding: 4 }} title="Sign out">
              <Icon type="out" size={14} />
            </button>
          </div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>{NAV.find((n) => n.id === page)?.label}</h1>
            <Badge color={user.role === "officer" ? "purple" : "blue"}>{user.role}</Badge>
          </div>
          {page === "dashboard" && <DashboardPage />}
          {page === "events" && <EventsPage />}
          {page === "fines" && <FinesPage />}
          {page === "members" && <MembersPage />}
          {page === "standing" && <StandingPage />}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}

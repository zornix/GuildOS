"use client";
import { useState } from "react";
import { useAuth } from "../../hooks/use-auth";
import { tokens } from "../../config/theme/tokens";
import { Sidebar } from "./sidebar";
import { PageHeader } from "./page-header";
import { DashboardPage } from "../../views/dashboard";
import { EventsPage } from "../../views/events";
import { FinesPage } from "../../views/fines";
import { MembersPage } from "../../views/members";
import { StandingPage } from "../../views/standing";
import { ActiveCheckInsPage } from "../../views/active-checkins";
import { OFFICER_ONLY, type PageId } from "../../config/navigation";

export function AppShell() {
  const { user, logout } = useAuth();
  const [page, setPage] = useState<PageId>("dashboard");

  const activePage: PageId = OFFICER_ONLY.includes(page) && user.role !== "officer" ? "dashboard" : page;

  return (
    <div style={{
      display: "flex",
      height: "100vh",
      background: tokens.color.bg,
      fontFamily: tokens.font.sans,
      color: tokens.color.text,
      overflow: "hidden",
    }}>
      <Sidebar user={user} activePage={activePage} onNavigate={setPage} onLogout={logout} />
      <div style={{ flex: 1, overflowY: "auto", padding: tokens.layout.shellPadding }}>
        <div style={{ maxWidth: tokens.layout.contentMaxWidth, margin: "0 auto" }}>
          <PageHeader activePage={activePage} user={user} />
          {activePage === "dashboard" && <DashboardPage />}
          {activePage === "events" && <EventsPage />}
          {activePage === "fines" && <FinesPage />}
          {activePage === "members" && <MembersPage />}
          {activePage === "standing" && <StandingPage />}
          {activePage === "active-checkins" && <ActiveCheckInsPage />}
        </div>
      </div>
    </div>
  );
}

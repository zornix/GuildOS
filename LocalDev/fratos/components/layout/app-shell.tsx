"use client";
import { useEffect, useState } from "react";
import { useAuth } from "../../hooks/use-auth";
import { tokens } from "../../config/theme/tokens";
import { Sidebar } from "./sidebar";
import { PageHeader } from "./page-header";
import { DashboardPage } from "../../views/dashboard";
import { EventsPage } from "../../views/events";
import { TreasuryPage } from "../../views/treasury";
import { FinesPage } from "../../views/fines";
import { MembersPage } from "../../views/members";
import { StandingPage } from "../../views/standing";
import { ActiveCheckInsPage } from "../../views/active-checkins";
import { TasksPage } from "../../views/tasks";
import { AnnouncementsPage } from "../../views/announcements";
import { RecruitmentPage } from "../../views/recruitment";
import { BylawsPage } from "../../views/bylaws";
import { CommandPage } from "../../views/command";
import { AdminRolesPage } from "../../views/admin-roles";
import { usePermissions } from "../../hooks/use-permissions";
import { NAV, OFFICER_ONLY, type PageId } from "../../config/navigation";

function useNarrowViewport() {
  const [isNarrow, setIsNarrow] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 760px)");
    const sync = () => setIsNarrow(query.matches);

    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  return isNarrow;
}

export function AppShell() {
  const { user, logout } = useAuth();
  const { can, loading: permissionsLoading } = usePermissions();
  const [page, setPage] = useState<PageId>("dashboard");
  const isNarrow = useNarrowViewport();

  const officerBlocked = OFFICER_ONLY.includes(page) && user.role !== "officer";
  const requiredPermission = NAV.find((n) => n.id === page)?.requiredPermission;
  // Don't bounce off a gated page while permissions are still loading; the
  // views render their own access guards in the meantime.
  const permissionBlocked = !permissionsLoading && requiredPermission !== undefined && !can(requiredPermission);
  const activePage: PageId = officerBlocked || permissionBlocked ? "dashboard" : page;

  return (
    <div style={{
      display: "flex",
      flexDirection: isNarrow ? "column" : "row",
      height: "100vh",
      background: tokens.color.bg,
      fontFamily: tokens.font.sans,
      color: tokens.color.text,
      overflow: "hidden",
    }}>
      <Sidebar user={user} activePage={activePage} onNavigate={setPage} onLogout={logout} compact={isNarrow} can={can} />
      <div style={{ flex: 1, minWidth: 0, overflowY: "auto", overflowX: "hidden", padding: isNarrow ? tokens.space[4] : tokens.layout.shellPadding }}>
        <div style={{ maxWidth: tokens.layout.contentMaxWidth, margin: "0 auto", minWidth: 0 }}>
          <PageHeader activePage={activePage} user={user} />
          {activePage === "dashboard" && <DashboardPage />}
          {activePage === "events" && <EventsPage />}
          {activePage === "treasury" && <TreasuryPage />}
          {activePage === "fines" && <FinesPage />}
          {activePage === "members" && <MembersPage />}
          {activePage === "standing" && <StandingPage />}
          {activePage === "active-checkins" && <ActiveCheckInsPage />}
          {activePage === "tasks" && <TasksPage />}
          {activePage === "announcements" && <AnnouncementsPage />}
          {activePage === "recruitment" && <RecruitmentPage />}
          {activePage === "bylaws" && <BylawsPage />}
          {activePage === "command" && <CommandPage />}
          {activePage === "admin-roles" && <AdminRolesPage />}
        </div>
      </div>
    </div>
  );
}

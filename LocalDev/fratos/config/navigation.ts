export type PageId =
  | "dashboard"
  | "events"
  | "treasury"
  | "fines"
  | "members"
  | "standing"
  | "active-checkins"
  | "tasks"
  | "announcements"
  | "recruitment"
  | "bylaws"
  | "command"
  | "admin-roles";

export interface NavItem {
  id: PageId;
  label: string;
  icon: string;
  /** RBAC permission string required to see this page (checked via /api/rbac/me/permissions). */
  requiredPermission?: string;
}

export const NAV: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: "home" },
  { id: "events", label: "Events", icon: "cal" },
  { id: "treasury", label: "Treasury", icon: "wallet" },
  { id: "fines", label: "Fines", icon: "dollar" },
  { id: "members", label: "Members", icon: "users" },
  { id: "tasks", label: "Tasks", icon: "check" },
  { id: "announcements", label: "Announcements", icon: "megaphone" },
  { id: "standing", label: "Standing", icon: "shield" },
  { id: "active-checkins", label: "Active Check-Ins", icon: "link" },
  { id: "recruitment", label: "Recruitment", icon: "target", requiredPermission: "recruitment:pipeline:view" },
  { id: "bylaws", label: "Bylaws", icon: "file", requiredPermission: "bylaws:query" },
  { id: "command", label: "Command", icon: "zap", requiredPermission: "nl_controller:execute" },
  { id: "admin-roles", label: "Roles & Access", icon: "key", requiredPermission: "roles:assign" },
];

export const OFFICER_ONLY: PageId[] = ["standing", "active-checkins"];

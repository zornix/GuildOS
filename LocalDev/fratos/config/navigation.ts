export type PageId = "dashboard" | "events" | "fines" | "members" | "standing" | "active-checkins";

export interface NavItem {
  id: PageId;
  label: string;
  icon: string;
}

export const NAV: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: "home" },
  { id: "events", label: "Events", icon: "cal" },
  { id: "fines", label: "Fines", icon: "dollar" },
  { id: "members", label: "Members", icon: "users" },
  { id: "standing", label: "Standing", icon: "shield" },
  { id: "active-checkins", label: "Active Check-Ins", icon: "link" },
];

export const OFFICER_ONLY: PageId[] = ["standing", "active-checkins"];

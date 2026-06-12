import type { Member, MyPermissions } from "./types";

export function isDevAuthBypassEnabled() {
  return process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "1";
}

export const devAuthUser: Member = {
  id: "local-dev-officer",
  name: "Local Dev Officer",
  role: "officer",
  email: "dev@greekos.local",
  chapter_id: "local-dev-chapter",
  status: "active",
};

export const devAuthPermissions: MyPermissions = {
  permissions: ["*"],
  roles: ["local-dev", "officer", "admin"],
};

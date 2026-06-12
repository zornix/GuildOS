import type { Member, MyPermissions } from "./types";

export function isDevAuthBypassEnabled() {
  return process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "1";
}

export const devAuthUser: Member = {
  id: "00000000-0000-0000-0000-000000000010",
  name: "Jake Martinez",
  role: "officer",
  email: "jake@tke.org",
  chapter_id: "00000000-0000-0000-0000-000000000001",
  status: "active",
};

export const devAuthEmail = "jake@tke.org";

export const devAuthPermissions: MyPermissions = {
  permissions: ["*"],
  roles: ["local-dev", "officer", "admin"],
};

/** Who is signed in, as the backend sees it. Permission keys come from
 *  GET /api/rbac/me/permissions; code never branches on a role's name. */

/** Selects the default chapter-wide dashboard view. Module access and actions
 *  must use their own permission keys, independently of this presentation flag. */
export const OFFICER_VIEW_KEY = 'standing:view_all';

export function can(permissions: Iterable<string>, key: string): boolean {
  for (const p of permissions) if (p === key) return true;
  return false;
}

export function isOfficerView(permissions: Iterable<string>): boolean {
  return can(permissions, OFFICER_VIEW_KEY);
}

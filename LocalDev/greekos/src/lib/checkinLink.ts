/** `/?checkin=CODE` deep links. The backend's `/c/CODE` page redirects here so
 *  that check-in always happens signed in (decision D6). */

export const CHECKIN_PARAM = 'checkin';
/** sessionStorage slot that carries the code across the login screen. */
export const CHECKIN_STORAGE_KEY = 'g_checkin';

/** Door codes are 6 letters/digits today and case-sensitive on the server;
 *  4-8 leaves room for a length change without accepting arbitrary strings. */
const CODE = /^[A-Za-z0-9]{4,8}$/;

/** The door code in a query string, or null when absent or malformed. */
export function readCheckinCode(search: string): string | null {
  const raw = new URLSearchParams(search).get(CHECKIN_PARAM);
  return raw !== null && CODE.test(raw) ? raw : null;
}

/** The same URL without the checkin parameter, for history.replaceState. */
export function stripCheckinParam(url: string): string {
  const u = new URL(url);
  u.searchParams.delete(CHECKIN_PARAM);
  return u.toString();
}

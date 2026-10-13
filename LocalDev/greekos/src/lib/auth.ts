/** Pure rules for the sign-in screens. No fetch, no React — see api.ts for the calls.
 *
 *  Backend contracts (api/auth/api/auth.py):
 *    POST /api/auth/login              -> { access_token, password_setup_required? }
 *    POST /api/auth/redeem-setup-code  -> { access_token, password_setup_required: true }
 *        access_token is setup-only (JWT claim pwd_setup: true, 1 hour): the API refuses it
 *        with 403 PASSWORD_SETUP_REQUIRED everywhere except /set-password and /me.
 *    POST /api/auth/set-password       -> { access_token }  (takes the setup-only token, returns a full one)
 */

/** Which panel the login screen shows. */
export type AuthStep = 'signin' | 'code' | 'password';

/** Codes are read aloud or copied off a screen: forgive case, spaces and dashes. */
export function normalizeSetupCode(raw: string): string {
  return raw.toUpperCase().replace(/[^A-Z0-9]/g, '');
}

/** A redeemed setup code yields a session that must set a password before anything else. */
export function stepAfterAuth(result: { password_setup_required?: boolean }): AuthStep | 'app' {
  return result.password_setup_required ? 'password' : 'app';
}

/** True when a stored token is the setup-only one, so a reload goes back to set-password
 *  instead of mounting the app on a token every endpoint refuses. Reads the payload only;
 *  the server still verifies the signature. */
export function isSetupToken(token: string | null): boolean {
  try {
    const part = token?.split('.')[1];
    if (!part) return false;
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(json)?.pwd_setup === true;
  } catch {
    return false;
  }
}

/** Turn an auth failure into something a member can act on. */
export function authErrorMessage(err: unknown, fallback: string): string {
  const e = err as { status?: number; code?: string; message?: string };
  if (e?.code === 'PASSWORD_REQUIRED') return 'Enter your password to sign in.';
  if (e?.status === 429) return 'Too many attempts. Wait 15 minutes and try again.';
  if (e?.status === 401) return fallback;
  if (e?.status === 0) return 'Cannot reach the server. Check your connection and try again.';
  return e?.message || fallback;
}

export function validateSignIn(email: string, password: string): string | null {
  if (!email.trim()) return 'Enter your chapter email.';
  if (!password) return 'Enter your password.';
  return null;
}

export function validateCodeForm(email: string, code: string): string | null {
  if (!email.trim()) return 'Enter the email your chapter has on file.';
  if (normalizeSetupCode(code).length < 8) return 'Setup codes are 8 characters.';
  return null;
}

export function validateNewPassword(password: string, confirm: string): string | null {
  if (password.length < 8) return 'Use at least 8 characters.';
  if (password !== confirm) return 'Passwords do not match.';
  return null;
}

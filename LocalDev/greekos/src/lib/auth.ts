/** Pure rules for the sign-in screens. No fetch, no React — see api.ts for the calls.
 *
 *  Backend contracts (api/auth/api/auth.py):
 *    POST /api/auth/login              -> { access_token, password_setup_required? }
 *    POST /api/auth/redeem-setup-code  -> { access_token, password_setup_required: true }
 *    POST /api/auth/set-password       -> { access_token }  (requires a session)
 */

/** Which panel the login screen shows. */
export type AuthStep = 'signin' | 'code' | 'password';

/** Codes are read aloud or copied off a screen: forgive case, spaces and dashes. */
export function normalizeSetupCode(raw: string): string {
  return raw.toUpperCase().replace(/[^A-Z0-9]/g, '');
}

/** A member with no password hash gets a grace token and must set one now. */
export function stepAfterAuth(result: { password_setup_required?: boolean }): AuthStep | 'app' {
  return result.password_setup_required ? 'password' : 'app';
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

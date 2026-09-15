import { FormEvent, useState } from 'react';
import { localDevLogin, login, redeemSetupCode, setPassword } from '../api';
import {
  AuthStep,
  authErrorMessage,
  normalizeSetupCode,
  stepAfterAuth,
  validateCodeForm,
  validateNewPassword,
  validateSignIn
} from '../lib/auth';

const inputClass =
  'w-full text-sm border border-slate-200 rounded-lg p-2.5 min-h-11 focus:outline-none focus:border-gold';
const labelClass = 'text-xs font-semibold text-slate-700 block mb-1';
const primaryClass =
  'w-full bg-navy hover:bg-[#16304f] text-white font-semibold text-xs py-3 min-h-11 rounded-lg disabled:opacity-60';
const linkClass = 'text-xs text-slate-500 hover:text-navy underline underline-offset-2';

/** Setup codes and officer-issued reset codes redeem through the same endpoint;
 *  only the copy differs, so the member knows where the code comes from. */
const CODE_COPY = {
  setup: {
    title: 'Enter your setup code',
    hint: 'Your chapter sent you an 8-character setup code when they added you.',
    button: 'Redeem code'
  },
  reset: {
    title: 'Reset your password',
    hint: 'Ask an officer to issue you a reset code, then enter it here. Codes expire in 7 days.',
    button: 'Use reset code'
  }
} as const;

export default function LoginScreen(
  { onLoggedIn, onStartChapter }: { onLoggedIn: () => void; onStartChapter?: () => void }
) {
  const [step, setStep] = useState<AuthStep>('signin');
  const [codeKind, setCodeKind] = useState<keyof typeof CODE_COPY>('setup');
  const [email, setEmail] = useState('');
  const [password, setPasswordValue] = useState('');
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const go = (next: AuthStep) => { setError(null); setStep(next); };

  /** Runs one auth call with the shared busy/error handling. */
  const run = async (fallback: string, call: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await call();
    } catch (err) {
      setError(authErrorMessage(err, fallback));
    } finally {
      setBusy(false);
    }
  };

  const submitSignIn = (e: FormEvent) => {
    e.preventDefault();
    const invalid = validateSignIn(email, password);
    if (invalid) return setError(invalid);
    return run('That email and password do not match. Check both and try again.', async () => {
      const result = await login(email, password);
      if (stepAfterAuth(result) === 'password') go('password');
      else onLoggedIn();
    });
  };

  const submitCode = (e: FormEvent) => {
    e.preventDefault();
    const invalid = validateCodeForm(email, code);
    if (invalid) return setError(invalid);
    return run('That code is not valid for this email, or it has expired or been used.', async () => {
      await redeemSetupCode(email, normalizeSetupCode(code));
      go('password');
    });
  };

  const submitPassword = (e: FormEvent) => {
    e.preventDefault();
    const invalid = validateNewPassword(newPassword, confirmPassword);
    if (invalid) return setError(invalid);
    return run('Could not save that password. Try again.', async () => {
      await setPassword(newPassword);
      onLoggedIn();
    });
  };

  const bypass = () =>
    run('Local bypass failed — is DEV_AUTH_BYPASS on?', async () => {
      await localDevLogin();
      onLoggedIn();
    });

  const emailField = (
    <div>
      <label htmlFor="email" className={labelClass}>Email</label>
      <input id="email" type="email" autoComplete="username" value={email}
        onChange={e => setEmail(e.target.value)} className={inputClass} />
    </div>
  );

  const errorBox = error && (
    <p role="alert" className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
      {error}
    </p>
  );

  return (
    <div className="min-h-screen bg-[#f8fafc] flex items-center justify-center p-4 font-sans">
      <div className="w-full max-w-sm bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
        <h1 className="font-display font-bold text-xl text-navy">GreekOS</h1>

        {step === 'signin' && (
          <form onSubmit={submitSignIn} className="space-y-4" noValidate>
            <p className="text-xs text-slate-500 mt-1">Sign in with your chapter email.</p>
            {emailField}
            <div>
              <label htmlFor="password" className={labelClass}>Password</label>
              <input id="password" type="password" autoComplete="current-password" value={password}
                onChange={e => setPasswordValue(e.target.value)} className={inputClass} />
            </div>
            {errorBox}
            <button type="submit" disabled={busy} className={primaryClass}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
            <div className="flex flex-wrap justify-between gap-2 pt-1">
              <button type="button" className={linkClass}
                onClick={() => { setCodeKind('setup'); go('code'); }}>
                I have a setup code
              </button>
              <button type="button" className={linkClass}
                onClick={() => { setCodeKind('reset'); go('code'); }}>
                Forgot password?
              </button>
            </div>
            {onStartChapter && (
              <button type="button" onClick={onStartChapter} disabled={busy}
                className="w-full text-xs text-slate-500 hover:text-navy pt-1">
                New here? Start a chapter
              </button>
            )}
            {import.meta.env.DEV && (
              <button type="button" onClick={bypass} disabled={busy}
                className="w-full text-xs text-slate-500 hover:text-navy pt-1">
                Local only: sign in as seeded officer
              </button>
            )}
          </form>
        )}

        {step === 'code' && (
          <form onSubmit={submitCode} className="space-y-4" noValidate>
            <p className="text-sm font-semibold text-navy mt-2">{CODE_COPY[codeKind].title}</p>
            <p className="text-xs text-slate-500">{CODE_COPY[codeKind].hint}</p>
            {emailField}
            <div>
              <label htmlFor="setup-code" className={labelClass}>Code</label>
              <input id="setup-code" type="text" inputMode="text" autoComplete="one-time-code"
                spellCheck={false} maxLength={16} value={code}
                onChange={e => setCode(e.target.value)}
                className={`${inputClass} tracking-widest uppercase font-mono`} />
            </div>
            {errorBox}
            <button type="submit" disabled={busy} className={primaryClass}>
              {busy ? 'Checking…' : CODE_COPY[codeKind].button}
            </button>
            <button type="button" className={linkClass} onClick={() => go('signin')}>
              Back to sign in
            </button>
          </form>
        )}

        {step === 'password' && (
          <form onSubmit={submitPassword} className="space-y-4" noValidate>
            <p className="text-sm font-semibold text-navy mt-2">Choose a password</p>
            <p className="text-xs text-slate-500">
              You are signed in. Set a password to finish — it replaces any code you used, and signs
              out your other devices.
            </p>
            <div>
              <label htmlFor="new-password" className={labelClass}>New password</label>
              <input id="new-password" type="password" autoComplete="new-password" value={newPassword}
                onChange={e => setNewPassword(e.target.value)} className={inputClass} />
              <p className="text-[11px] text-slate-400 mt-1">At least 8 characters.</p>
            </div>
            <div>
              <label htmlFor="confirm-password" className={labelClass}>Confirm password</label>
              <input id="confirm-password" type="password" autoComplete="new-password"
                value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                className={inputClass} />
            </div>
            {errorBox}
            <button type="submit" disabled={busy} className={primaryClass}>
              {busy ? 'Saving…' : 'Save password and continue'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

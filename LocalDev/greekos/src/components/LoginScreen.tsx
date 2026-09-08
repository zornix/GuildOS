import { FormEvent, useState } from 'react';
import { localDevLogin, login } from '../api';

export default function LoginScreen({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      onLoggedIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not sign in');
    } finally {
      setBusy(false);
    }
  };

  const bypass = async () => {
    setBusy(true);
    setError(null);
    try {
      await localDevLogin();
      onLoggedIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Local bypass failed — is DEV_AUTH_BYPASS on?');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f8fafc] flex items-center justify-center p-4 font-sans">
      <form onSubmit={submit} className="w-full max-w-sm bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
        <div>
          <h1 className="font-display font-bold text-xl text-navy">GreekOS</h1>
          <p className="text-xs text-slate-500 mt-1">Sign in with your chapter email.</p>
        </div>
        <div>
          <label htmlFor="email" className="text-xs font-semibold text-slate-700 block mb-1">Email</label>
          <input id="email" type="email" autoComplete="username" required value={email}
            onChange={e => setEmail(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold" />
        </div>
        <div>
          <label htmlFor="password" className="text-xs font-semibold text-slate-700 block mb-1">Password</label>
          <input id="password" type="password" autoComplete="current-password" required value={password}
            onChange={e => setPassword(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold" />
        </div>
        {error && (
          <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
        )}
        <button type="submit" disabled={busy}
          className="w-full bg-navy hover:bg-[#16304f] text-white font-semibold text-xs py-3 min-h-11 rounded-lg disabled:opacity-60">
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        {import.meta.env.DEV && (
          <button type="button" onClick={bypass} disabled={busy}
            className="w-full text-xs text-slate-500 hover:text-navy">
            Local only: sign in as seeded officer
          </button>
        )}
      </form>
    </div>
  );
}

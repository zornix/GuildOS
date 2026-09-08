import React, { useId, useState } from 'react';

interface DoorCodeFieldProps {
  /** The code identifies the event; the backend checks in the signed-in member. */
  onSelfCheckIn: (code: string) => Promise<{ ok: boolean; message: string }>;
  /** Home renders the small version; Attendance the large centered one. */
  compact?: boolean;
}

/** The 6-character door code entry, shared by Home and Attendance. */
export default function DoorCodeField({ onSelfCheckIn, compact = false }: DoorCodeFieldProps) {
  const id = useId();
  const [code, setCode] = useState('');
  const [feedback, setFeedback] = useState<{ ok: boolean; message: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const result = await onSelfCheckIn(code);
    setBusy(false);
    setFeedback(result);
    if (result.ok) setCode('');
  };

  return (
    <form onSubmit={submit} className={compact ? 'flex flex-wrap items-end gap-2' : 'space-y-4'}>
      <div className={compact ? '' : 'text-center'}>
        <label htmlFor={id} className="text-xs font-bold text-slate-700 block mb-1">
          Door code
        </label>
        <input
          id={id}
          type="text"
          inputMode="text"
          autoComplete="one-time-code"
          maxLength={6}
          value={code}
          onChange={e => setCode(e.target.value)}
          placeholder="A7x9Kp"
          required
          className={compact
            ? 'w-36 text-center text-xl font-mono font-black tracking-widest py-2 border-2 border-slate-300 rounded-lg focus:outline-none focus:border-gold bg-white text-slate-900'
            : 'w-48 mx-auto text-center text-3xl font-mono font-black tracking-widest py-3 border-2 border-slate-300 rounded-xl focus:outline-none focus:border-gold'}
        />
      </div>

      <button
        type="submit"
        disabled={busy || !code.trim()}
        className={`bg-navy text-gold hover:bg-slate-800 font-bold min-h-11 rounded-lg text-xs transition-all cursor-pointer disabled:opacity-50 ${compact ? 'px-4' : 'w-full py-3'}`}
      >
        {busy ? 'Checking in…' : 'Check in'}
      </button>

      {feedback && (
        <div
          role="status"
          className={`p-2.5 rounded-lg text-xs font-semibold ${compact ? 'basis-full' : ''} ${
            feedback.ok ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-red-50 text-red-800 border border-red-200'
          }`}
        >
          {feedback.message}
        </div>
      )}
    </form>
  );
}

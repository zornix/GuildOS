import { useState } from 'react';
import { MessageSquare } from 'lucide-react';
import Card from '../ui/Card';
import { api } from '../../api';
import { SMS_CONSENT_LABEL } from '../../lib/consent';

/** The member's own SMS opt-in (#57). Consent is theirs to give, so this is the
 *  one control that is never officer-gated.
 *
 *  Turning it on POSTs /api/members/me/sms-consent, which also clears a prior
 *  STOP. There is no opt-out endpoint — the carriers' own STOP keyword is the
 *  opt-out, so "off" here tells them how to use it rather than pretending to. */
export default function SmsConsentCard({ consented }: { consented: boolean }) {
  const [on, setOn] = useState(consented);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const optIn = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.optInToSms();
      setOn(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-4 sm:p-5 space-y-3">
      <div className="flex items-center justify-between border-b border-slate-100 pb-2">
        <h3 className="font-display font-extrabold text-slate-900 text-sm flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-gold-muted" />
          Text me chapter announcements
        </h3>
        <span
          className={`text-xs font-bold px-2 py-0.5 rounded-full border ${
            on
              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
              : 'bg-slate-100 text-slate-600 border-slate-200'
          }`}
        >
          {on ? 'On' : 'Off'}
        </span>
      </div>

      <p className="text-xs text-slate-600 leading-relaxed">{SMS_CONSENT_LABEL}</p>

      {on ? (
        <p className="text-xs text-slate-500">
          Announcement texts are on. Reply <span className="font-mono font-semibold">STOP</span> to
          any message to turn them off. Everything else still reaches you by email.
        </p>
      ) : (
        <button
          type="button"
          onClick={() => void optIn()}
          disabled={busy}
          className="bg-navy hover:bg-[#1e2d42] text-white font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg cursor-pointer disabled:opacity-60"
        >
          {busy ? 'Saving…' : 'Turn texts on'}
        </button>
      )}

      {error && <p className="text-xs font-semibold text-rose-700 break-words">{error}</p>}
    </Card>
  );
}

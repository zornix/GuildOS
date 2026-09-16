import { FormEvent, useState } from 'react';
import { createChapter, CreateChapterResult } from '../api';
import { SMS_CONSENT_LABEL } from '../lib/consent';

/** Self-serve chapter signup: the pre-login half of onboarding. The officer
 *  gets a one-time setup code here and redeems it on the sign-in screen —
 *  no password is ever set from this form. */
export default function OnboardingScreen({ onBack }: { onBack: () => void }) {
  const [name, setName] = useState('');
  const [organization, setOrganization] = useState('');
  const [school, setSchool] = useState('');
  const [officerName, setOfficerName] = useState('');
  const [officerEmail, setOfficerEmail] = useState('');
  const [officerPhone, setOfficerPhone] = useState('');
  // Unchecked by default and it stays that way: carriers require prior express
  // consent, and a pre-ticked box is not consent (#57).
  const [smsConsent, setSmsConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<CreateChapterResult | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setCreated(await createChapter({
        name,
        organization: organization || undefined,
        school: school || undefined,
        officer_name: officerName,
        officer_email: officerEmail,
        officer_phone: officerPhone,
        sms_consent: smsConsent
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the chapter');
    } finally {
      setBusy(false);
    }
  };

  const field = 'w-full text-sm border border-slate-200 rounded-lg p-2.5 min-h-11 focus:outline-none focus:border-gold';
  const label = 'text-xs font-semibold text-slate-700 block mb-1';

  if (created) {
    return (
      <div className="min-h-screen bg-[#f8fafc] flex items-center justify-center p-4 font-sans">
        <div className="w-full max-w-sm bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
          <h1 className="font-display font-bold text-xl text-navy">{name} is ready</h1>
          <p className="text-xs text-slate-500">
            We emailed the setup code to{' '}
            <span className="font-semibold text-slate-700 break-all">{created.officer_email}</span>.
            It is also below — write it down, it is shown here only once. Go back to sign in, enter
            that address and redeem the code to set your password.
          </p>
          <p className="font-display font-bold text-2xl tracking-[0.3em] text-navy bg-slate-50 border border-slate-200 rounded-lg py-4 text-center break-all">
            {created.setup_code}
          </p>
          <button type="button" onClick={onBack}
            className="w-full bg-navy hover:bg-[#16304f] text-white font-semibold text-xs py-3 min-h-11 rounded-lg">
            Go to sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f8fafc] flex items-center justify-center p-4 font-sans">
      <form onSubmit={submit} className="w-full max-w-sm bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
        <div>
          <h1 className="font-display font-bold text-xl text-navy">Start a chapter</h1>
          <p className="text-xs text-slate-500 mt-1">
            You become the first officer. Add everyone else afterwards from the roster.
          </p>
        </div>

        <div>
          <label htmlFor="chapter-name" className={label}>Chapter name</label>
          <input id="chapter-name" required value={name}
            onChange={e => setName(e.target.value)} className={field} />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="organization" className={label}>Organization <span className="font-normal text-slate-400">(optional)</span></label>
            <input id="organization" value={organization}
              onChange={e => setOrganization(e.target.value)} className={field} />
          </div>
          <div>
            <label htmlFor="school" className={label}>School <span className="font-normal text-slate-400">(optional)</span></label>
            <input id="school" value={school}
              onChange={e => setSchool(e.target.value)} className={field} />
          </div>
        </div>
        <div>
          <label htmlFor="officer-name" className={label}>Your name</label>
          <input id="officer-name" autoComplete="name" required value={officerName}
            onChange={e => setOfficerName(e.target.value)} className={field} />
        </div>
        <div>
          <label htmlFor="officer-email" className={label}>Your email</label>
          <input id="officer-email" type="email" autoComplete="email" required value={officerEmail}
            onChange={e => setOfficerEmail(e.target.value)} className={field} />
        </div>
        <div>
          <label htmlFor="officer-phone" className={label}>Your phone</label>
          <input id="officer-phone" type="tel" autoComplete="tel" required value={officerPhone}
            onChange={e => setOfficerPhone(e.target.value)} placeholder="+1 555 111 0001" className={field} />
        </div>

        <label className="flex items-start gap-3 text-xs text-slate-600 leading-relaxed min-h-11 cursor-pointer">
          <input
            type="checkbox"
            checked={smsConsent}
            onChange={e => setSmsConsent(e.target.checked)}
            className="mt-0.5 w-4 h-4 shrink-0 accent-navy cursor-pointer"
          />
          <span>{SMS_CONSENT_LABEL}</span>
        </label>

        {error && (
          <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
        )}

        <button type="submit" disabled={busy}
          className="w-full bg-navy hover:bg-[#16304f] text-white font-semibold text-xs py-3 min-h-11 rounded-lg disabled:opacity-60">
          {busy ? 'Creating…' : 'Create chapter'}
        </button>
        <button type="button" onClick={onBack} disabled={busy}
          className="w-full text-xs text-slate-500 hover:text-navy">
          Back to sign in
        </button>
      </form>
    </div>
  );
}

import { useState } from 'react';
import { Check, Copy, Trophy } from 'lucide-react';
import Card from '../ui/Card';
import { ContributionRecord, resumeLine } from '../../lib/contribution';

interface MyRecordProps {
  record: ContributionRecord;
}

/** "My record": the member's own lifetime contribution counts plus the one
 *  line they can paste onto a résumé. Positive-only, personal, never ranked
 *  against anyone else (ADR-0004). */
export default function MyRecord({ record }: MyRecordProps) {
  const [copied, setCopied] = useState(false);
  const line = resumeLine(record);

  const counts = [
    { label: 'Events organized', value: record.eventsOrganized.length },
    {
      label: 'Attendees reached',
      value: record.eventsOrganized.reduce((sum, e) => sum + e.attendeeCount, 0)
    },
    { label: 'Events supervised', value: record.eventsSupervised.length },
    { label: 'Initiatives chaired', value: record.initiativesChaired.length },
    { label: 'Jobs completed', value: record.jobsDone.length },
    { label: 'Events attended', value: record.eventsAttendedCount }
  ];

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(line);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Card className="p-4 sm:p-5 space-y-4">
      <div className="flex items-center justify-between border-b border-slate-100 pb-2">
        <h3 className="font-display font-extrabold text-slate-900 text-sm flex items-center gap-2">
          <Trophy className="w-4 h-4 text-gold-muted" />
          My record
        </h3>
        <span className="text-xs text-slate-500">Yours only &middot; never a ranking</span>
      </div>

      <dl className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {counts.map(c => (
          <div key={c.label} className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2">
            <dd className="text-lg font-display font-extrabold text-navy">{c.value}</dd>
            <dt className="text-[11px] leading-tight text-slate-500">{c.label}</dt>
          </div>
        ))}
      </dl>

      <div className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-lg bg-navy/5 border border-slate-200 p-3">
        <p className="text-xs text-slate-700 flex-1 break-words">{line}</p>
        <button
          type="button"
          onClick={copy}
          className="shrink-0 self-start sm:self-auto bg-navy hover:bg-[#1e2d42] text-white font-bold text-xs px-3 py-2 min-h-11 sm:min-h-0 rounded-lg flex items-center gap-1.5 cursor-pointer"
        >
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? 'Copied' : 'Copy line'}
        </button>
      </div>
    </Card>
  );
}

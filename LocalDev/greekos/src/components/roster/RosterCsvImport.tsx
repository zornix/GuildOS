import { useRef, useState } from 'react';
import { Upload } from 'lucide-react';
import type { RosterImportResult, RosterRowError } from '../../api';
import Card from '../ui/Card';
import { ROSTER_CONSENT_NOTE, ROSTER_CSV_HEADER } from '../../lib/consent';

/** Officer-only roster CSV upload. The import is all-or-nothing: a rejected
 *  file imported nothing, so the row list below is a to-fix list, not a
 *  partial-failure report. */
export default function RosterCsvImport(
  { onImport }: { onImport: (file: File) => Promise<RosterImportResult> }
) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [rowErrors, setRowErrors] = useState<RosterRowError[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RosterImportResult | null>(null);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setRowErrors([]);
    setError(null);
    setResult(null);
    try {
      setResult(await onImport(file));
    } catch (err) {
      const rows = (err as { rows?: RosterRowError[] }).rows;
      if (rows) setRowErrors(rows);
      else setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <Card className="p-4 space-y-3">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-display font-bold text-slate-900">Import a roster</h3>
          <p className="text-xs text-slate-500 mt-1">
            CSV with the header{' '}
            <code className="font-mono break-all">{ROSTER_CSV_HEADER}</code>.{' '}
            <code className="font-mono">role</code> and <code className="font-mono">consent</code>{' '}
            are optional; put <code className="font-mono">yes</code> in{' '}
            <code className="font-mono">consent</code> only for members who signed an opt-in for
            chapter announcement texts.
          </p>
          <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-2">
            {ROSTER_CONSENT_NOTE}
          </p>
        </div>
        <label className="bg-navy hover:bg-[#16304f] text-white font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-sm flex items-center justify-center gap-2 cursor-pointer whitespace-nowrap">
          <Upload className="w-4 h-4" />
          {busy ? 'Importing…' : 'Upload CSV'}
          <input ref={inputRef} type="file" accept=".csv,text/csv" className="sr-only"
            disabled={busy} onChange={e => pick(e.target.files?.[0])} />
        </label>
      </div>

      {result && (
        <div className="text-xs bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg px-3 py-2 space-y-1">
          <p className="font-semibold">
            Invited {result.created_count}
            {result.skipped_count > 0 && `, skipped ${result.skipped_count} already on the roster`}
          </p>
          {result.created.map(m => (
            <p key={m.email} className="font-mono break-all">
              {m.email} — setup code {m.setup_code}
            </p>
          ))}
          {result.created.length > 0 && (
            <p className="text-emerald-700">
              Each setup code was emailed to its member. They are shown here only once, so hand
              over a code yourself if the email does not land.
            </p>
          )}
        </div>
      )}

      {rowErrors.length > 0 && (
        <div className="text-xs bg-red-50 border border-red-200 text-red-800 rounded-lg px-3 py-2 space-y-1">
          <p className="font-semibold">Nothing was imported — fix these rows and upload again:</p>
          <ul className="space-y-0.5">
            {rowErrors.map((e, i) => (
              <li key={`${e.row}-${i}`}>Row {e.row}: {e.error}</li>
            ))}
          </ul>
        </div>
      )}

      {error && (
        <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
      )}
    </Card>
  );
}

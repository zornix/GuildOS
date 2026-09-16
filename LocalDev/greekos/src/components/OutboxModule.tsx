import { useState } from 'react';
import { AlertTriangle, Inbox, RefreshCw, Send } from 'lucide-react';
import { OutboxMessage, OutboxStatus } from '../types';
import { useOutboxFeed } from '../hooks/useOutbox';
import Card from './ui/Card';
import { outboxFailure } from '../lib/consent';

type Filter = OutboxStatus | 'all';

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'pending', label: 'Queued' },
  { id: 'sent', label: 'Sent' },
  { id: 'failed', label: 'Failed' },
  { id: 'simulated', label: 'Simulated' }
];

/** Status pill colours: failure has to read as failure at a glance. */
const STATUS_TONE: Record<string, string> = {
  pending: 'bg-amber-50 text-amber-700 border-amber-200',
  sending: 'bg-sky-50 text-sky-700 border-sky-200',
  sent: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  simulated: 'bg-slate-100 text-slate-600 border-slate-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200'
};

const STATUS_LABEL: Record<string, string> = {
  pending: 'Queued',
  sending: 'Sending',
  sent: 'Sent',
  simulated: 'Simulated',
  failed: 'Failed'
};

const when = (iso?: string) => (iso ? new Date(iso).toLocaleString() : '');

/** Every SMS the chapter has queued, sent or failed to send. */
export default function OutboxModule() {
  const [filter, setFilter] = useState<Filter>('all');
  const { messages, loading, error, refetch, retry } = useOutboxFeed(filter);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);

  const handleRetry = async (id: string) => {
    setRetrying(id);
    setRetryError(null);
    try {
      await retry(id);
    } catch (err) {
      setRetryError((err as Error).message);
    } finally {
      setRetrying(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Send className="w-6 h-6 text-gold" />
            <h2 className="text-2xl font-display font-extrabold text-slate-900 tracking-tight">
              Outbox
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Every message the chapter has queued, sent or failed to send.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void refetch()}
          className="bg-white hover:bg-slate-50 text-slate-800 border border-slate-200 font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-xs flex items-center gap-2 cursor-pointer self-start"
        >
          <RefreshCw className="w-4 h-4 text-gold" />
          Refresh
        </button>
      </div>

      {/* Status filter chips — scroll sideways on a phone rather than wrapping. */}
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
        {FILTERS.map(f => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            aria-pressed={filter === f.id}
            className={`shrink-0 min-h-11 px-4 rounded-full border text-xs font-bold cursor-pointer transition-all ${
              filter === f.id
                ? 'bg-navy text-gold border-navy'
                : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {retryError && (
        <div className="flex items-start gap-2 text-xs font-semibold text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-3">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{retryError}</span>
        </div>
      )}

      {error ? (
        <Card className="p-8 text-center text-xs font-semibold text-rose-700">{error}</Card>
      ) : loading ? (
        <Card className="p-8 text-center text-xs text-slate-500">Loading messages…</Card>
      ) : messages.length === 0 ? (
        <Card className="p-10 text-center space-y-2">
          <Inbox className="w-8 h-8 text-slate-300 mx-auto" />
          <p className="text-sm font-bold text-slate-700">Nothing here</p>
          <p className="text-xs text-slate-500">
            {filter === 'all'
              ? 'No messages have been queued for this chapter yet.'
              : `No ${STATUS_LABEL[filter]?.toLowerCase()} messages.`}
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {messages.map(m => (
            <MessageRow
              key={m.id}
              message={m}
              retrying={retrying === m.id}
              onRetry={() => void handleRetry(m.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function MessageRow({
  message,
  retrying,
  onRetry
}: {
  message: OutboxMessage;
  retrying: boolean;
  onRetry: () => void;
  /** No @types/react in this project, so `key` is an ordinary prop. */
  key?: string | number;
}) {
  // "no_consent" is not an error the officer can retry away — only the member
  // can opt in — so it reads as an explanation and hides Retry (#57).
  const failure = outboxFailure(message.error);

  return (
    <Card className="p-4 space-y-2">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-bold text-slate-900 truncate">
            {message.recipientName}
            {message.recipientPhone && (
              <span className="font-medium text-slate-500"> · {message.recipientPhone}</span>
            )}
          </p>
          <p className="text-xs text-slate-500">
            {message.eventType} · queued {when(message.createdAt)}
            {message.deliveredAt && ` · delivered ${when(message.deliveredAt)}`}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span
            className={`px-2.5 py-1 rounded-full border text-xs font-bold ${
              STATUS_TONE[message.status] || STATUS_TONE.simulated
            }`}
          >
            {STATUS_LABEL[message.status] || message.status}
          </span>
          {message.status === 'failed' && failure.retryable && (
            <button
              type="button"
              onClick={onRetry}
              disabled={retrying}
              className="bg-navy hover:bg-slate-800 text-gold font-bold text-xs px-3 py-2 min-h-11 rounded-lg flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${retrying ? 'animate-spin' : ''}`} />
              Retry
            </button>
          )}
        </div>
      </div>

      {message.body && <p className="text-sm text-slate-700 break-words">{message.body}</p>}

      {message.error && (
        <p
          className={`text-xs font-semibold break-words ${
            failure.retryable ? 'text-rose-700' : 'text-slate-600'
          }`}
        >
          {failure.text}
          {failure.retryable && ` (attempt ${message.attempts})`}
        </p>
      )}
    </Card>
  );
}

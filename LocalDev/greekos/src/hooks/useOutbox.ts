import { useCallback, useEffect, useState } from 'react';
import { OutboxMessage, OutboxNotification, OutboxStatus } from '../types';
import { api } from '../api';
import { adaptOutbox } from '../adapters';

/** Legacy local-notice shape. The server sends notices; only useFinance still declares this dep. */
export type EnqueueOutbox = (notif: Omit<OutboxNotification, 'id' | 'timestamp' | 'status'>) => void;

/** The real message outbox, fetched by the Outbox module (officer-gated). */
export function useOutboxFeed(status: OutboxStatus | 'all') {
  const [messages, setMessages] = useState<OutboxMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      setMessages(adaptOutbox(await api.getOutbox(status === 'all' ? undefined : status)));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const retry = async (id: string) => {
    await api.retryOutboxMessage(id);
    await refetch();
  };

  return { messages, loading, error, refetch, retry };
}

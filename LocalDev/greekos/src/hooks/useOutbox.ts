import { INITIAL_OUTBOX } from '../data/mockData';
import { OutboxNotification } from '../types';
import { usePersistentState } from './usePersistentState';

/** Demo-only SMS/push outbox. Every domain enqueues into it, so `enqueue` is
 *  handed down to the domain hooks that send notices. */
export function useOutbox() {
  const [outbox, setOutbox] = usePersistentState<OutboxNotification[]>('g_outbox', INITIAL_OUTBOX);

  const enqueueOutbox = (notif: Omit<OutboxNotification, 'id' | 'timestamp' | 'status'>) => {
    const newEntry: OutboxNotification = {
      ...notif,
      id: 'out_' + Math.random().toString(36).substring(2, 9),
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
      status: 'Delivered'
    };
    setOutbox(prev => [newEntry, ...prev]);
  };

  const clearDelivered = () => setOutbox(prev => prev.filter(n => n.status !== 'Delivered'));

  return { outbox, enqueueOutbox, clearDelivered };
}

export type EnqueueOutbox = ReturnType<typeof useOutbox>['enqueueOutbox'];

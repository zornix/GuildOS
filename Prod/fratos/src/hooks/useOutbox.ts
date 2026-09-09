import { OutboxNotification } from '../types';

/** Notices still enqueue from domain hooks; nothing renders a local outbox. */
export type EnqueueOutbox = (notif: Omit<OutboxNotification, 'id' | 'timestamp' | 'status'>) => void;

export const enqueueOutbox: EnqueueOutbox = () => {};

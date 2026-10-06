import { useState } from 'react';
import { ShowToast } from './useToast';
import { describeError, syncOutcome } from '../lib/sync';

export interface SyncHandlers {
  /** Fires only once the write landed — nothing may claim success before it. */
  onSuccess?: () => void;
  /** Replaces the generic failure toast when the caller has a better message. */
  onError?: (err: unknown) => void;
}

export type SyncApi = (
  call: () => Promise<unknown>,
  refetch: () => Promise<void>,
  /** The success toast (shown after the server answers), or handlers for
   *  callers that translate the outcome themselves. */
  onDone?: string | SyncHandlers
) => Promise<boolean>;

/** Connection state for the initial load plus the shared mutation path. */
export function useBackend(showToast: ShowToast) {
  const [loading, setLoading] = useState<boolean>(true);
  const [backendDown, setBackendDown] = useState<boolean>(false);

  /** Fire a mutation at the API and refetch its domain. Local state was already
   *  updated optimistically, so a failure refetches too — otherwise the screen
   *  keeps showing a change the server never accepted. Resolves true only when
   *  the write landed. */
  const syncApi: SyncApi = async (call, refetch, onDone) => {
    const successMessage = typeof onDone === 'string' ? onDone : undefined;
    const handlers = typeof onDone === 'string' ? undefined : onDone;
    const say = (outcome: 'ok' | 'error', errorMessage?: string) => {
      const { toast } = syncOutcome({ backendDown, outcome, successMessage, errorMessage });
      if (toast) showToast(toast);
    };

    if (backendDown) {
      // The load already failed, so this mostly fails too; it is still tried in
      // case the server came back, and the user is told either way.
      await refetch().catch(() => { /* leave the optimistic row */ });
      say('error');
      return false;
    }
    try {
      await call();
      handlers?.onSuccess?.();
      say('ok');
      await refetch();
      return true;
    } catch (err) {
      console.error('Mutation failed', err);
      await refetch().catch(() => { /* leave the optimistic row */ });
      if (handlers?.onError) handlers.onError(err);
      else say('error', describeError(err));
      return false;
    }
  };

  return { loading, setLoading, backendDown, setBackendDown, syncApi };
}

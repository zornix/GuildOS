import { useState } from 'react';
import { ShowToast } from './useToast';
import { describeError, isNetworkError, syncOutcome } from '../lib/sync';

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
    const say = (outcome: 'ok' | 'error', errorMessage?: string, unreachable = false) => {
      const { toast, backendDown: nextBackendDown } = syncOutcome({ backendDown: unreachable, outcome, successMessage, errorMessage });
      setBackendDown(nextBackendDown);
      if (toast) showToast(toast);
    };

    // backendDown is not a reason to skip the write: the server may be back, and
    // if it is not, the failure below is reported as "unreachable".
    try {
      await call();
    } catch (err) {
      console.error('Mutation failed', err);
      await refetch().catch(() => { /* leave the optimistic row */ });
      setBackendDown(isNetworkError(err));
      if (handlers?.onError) handlers.onError(err);
      else say('error', describeError(err), isNetworkError(err));
      return false;
    }
    // The write landed. A failed re-read is a stale screen, not a refused save.
    handlers?.onSuccess?.();
    say('ok');
    await refetch().catch(err => console.error('Refresh after save failed', err));
    return true;
  };

  return { loading, setLoading, backendDown, setBackendDown, syncApi };
}

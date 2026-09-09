import { useState } from 'react';
import { ShowToast } from './useToast';

export type SyncApi = (
  call: () => Promise<unknown>,
  refetch: () => Promise<void>,
  /** onSuccess fires only once the write landed — nothing may claim success before it.
   *  onError replaces the generic failure toast when the caller has a better message. */
  handlers?: { onSuccess?: () => void; onError?: (err: unknown) => void }
) => void;

/** Connection state for the initial load plus the shared mutation path. */
export function useBackend(showToast: ShowToast) {
  const [loading, setLoading] = useState<boolean>(true);
  const [backendDown, setBackendDown] = useState<boolean>(false);

  /** Fire a mutation at the API and refetch its domain. Local state was already
   *  updated optimistically, so a failure refetches too — otherwise the screen
   *  keeps showing a change the server never accepted. */
  const syncApi: SyncApi = (call, refetch, handlers) => {
    if (backendDown) return;
    (async () => {
      try {
        await call();
        handlers?.onSuccess?.();
        await refetch();
      } catch (err) {
        console.error('Mutation failed', err);
        await refetch().catch(() => { /* leave the optimistic row */ });
        if (handlers?.onError) handlers.onError(err);
        else showToast("Couldn't save that — the server refused the change.");
      }
    })();
  };

  return { loading, setLoading, backendDown, setBackendDown, syncApi };
}

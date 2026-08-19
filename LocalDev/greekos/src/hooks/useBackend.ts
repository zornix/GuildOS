import { useState } from 'react';
import { ShowToast } from './useToast';

export type SyncApi = (call: () => Promise<unknown>, refetch: () => Promise<void>) => void;

/** Connection state for the initial load plus the shared mutation path. */
export function useBackend(showToast: ShowToast) {
  const [loading, setLoading] = useState<boolean>(true);
  const [backendDown, setBackendDown] = useState<boolean>(false);

  /** Fire a mutation at the API and refetch its domain. Local state was already
   *  updated optimistically, so a failure refetches too — otherwise the screen
   *  keeps showing a change the server never accepted. */
  const syncApi: SyncApi = (call, refetch) => {
    if (backendDown) return;
    (async () => {
      try {
        await call();
        await refetch();
      } catch (err) {
        console.error('Mutation failed', err);
        await refetch().catch(() => { /* leave the optimistic row */ });
        showToast("Couldn't save that — the server refused the change.");
      }
    })();
  };

  return { loading, setLoading, backendDown, setBackendDown, syncApi };
}

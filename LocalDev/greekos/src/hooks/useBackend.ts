import { useState } from 'react';
import { ShowToast } from './useToast';

export type SyncApi = (call: () => Promise<unknown>, refetch: () => Promise<void>) => void;

/** Connection state for the initial load plus the shared mutation path. */
export function useBackend(showToast: ShowToast) {
  const [loading, setLoading] = useState<boolean>(true);
  const [backendDown, setBackendDown] = useState<boolean>(false);

  /** Fire a mutation at the API and refetch its domain. Local state was already
   *  updated optimistically, so a backend error only surfaces as a toast. */
  const syncApi: SyncApi = (call, refetch) => {
    if (backendDown) return;
    (async () => {
      try {
        await call();
        await refetch();
      } catch (err) {
        showToast(`Server rejected that: ${(err as Error).message}`);
      }
    })();
  };

  return { loading, setLoading, backendDown, setBackendDown, syncApi };
}

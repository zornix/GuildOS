import { useState } from 'react';

/** One toast at a time. It stays until the next toast replaces it or the
 *  user dismisses it — no timer, so nothing disappears before it is read. */
export function useToast() {
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const showToast = (msg: string) => setToastMessage(msg);
  const dismissToast = () => setToastMessage(null);
  return { toastMessage, showToast, dismissToast };
}

export type ShowToast = ReturnType<typeof useToast>['showToast'];

import { useState } from 'react';

/** Ephemeral toast notification state. */
export function useToast() {
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  return { toastMessage, showToast };
}

export type ShowToast = ReturnType<typeof useToast>['showToast'];

/** What the user is told once a mutation settles, and whether the optimistic
 *  state must be rolled back. Pure: `useBackend.syncApi` only acts on the answer. */

export const UNREACHABLE_MESSAGE = 'Not saved: the server is unreachable.';
export const REFUSED_MESSAGE = "Couldn't save that — the server refused the change.";
export const FORBIDDEN_MESSAGE = "You don't have permission to do that.";

export interface SyncInput {
  backendDown: boolean;
  outcome: 'ok' | 'error';
  /** Shown only on success, i.e. after the server answered. */
  successMessage?: string;
  /** The caller's translation of the error; the refusal copy when absent. */
  errorMessage?: string;
}

export interface SyncOutcome {
  /** null means nothing to say. */
  toast: string | null;
  /** The server is the truth: a refetch drops the optimistic row. */
  rollback: boolean;
}

export function syncOutcome({ backendDown, outcome, successMessage, errorMessage }: SyncInput): SyncOutcome {
  if (backendDown) return { toast: UNREACHABLE_MESSAGE, rollback: true };
  if (outcome === 'error') return { toast: errorMessage ?? REFUSED_MESSAGE, rollback: true };
  return { toast: successMessage ?? null, rollback: false };
}

/** Generic copy for an error the caller did not translate. */
export function describeError(err: unknown): string {
  return (err as { status?: number } | undefined)?.status === 403 ? FORBIDDEN_MESSAGE : REFUSED_MESSAGE;
}

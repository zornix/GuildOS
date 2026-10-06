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
  /** Connection state after this actual outcome. */
  backendDown: boolean;
}

export function syncOutcome({ backendDown, outcome, successMessage, errorMessage }: SyncInput): SyncOutcome {
  if (outcome === 'ok') return { toast: successMessage ?? null, rollback: false, backendDown: false };
  return { toast: errorMessage ?? (backendDown ? UNREACHABLE_MESSAGE : REFUSED_MESSAGE), rollback: true, backendDown };
}

/** The server's own detail from an api.ts error (`METHOD /path failed (NNN): detail`), else the fallback. */
export function serverMessage(err: unknown, fallback: string): string {
  const match = /failed \(\d{3}\): (.+)$/s.exec((err as { message?: string } | undefined)?.message ?? '');
  return match?.[1].trim() || fallback;
}

/** A fetch rejection has no HTTP response; auth calls use status 0. */
export function isNetworkError(err: unknown): boolean {
  const status = (err as { status?: number } | undefined)?.status;
  return status === 0 || (err instanceof TypeError && status === undefined);
}

/** Generic copy for an error the caller did not translate. */
export function describeError(err: unknown): string {
  if (isNetworkError(err)) return UNREACHABLE_MESSAGE;
  return (err as { status?: number } | undefined)?.status === 403 ? FORBIDDEN_MESSAGE : REFUSED_MESSAGE;
}

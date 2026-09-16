/** SMS consent in the UI (#57, ops-runbook §6.1).
 *
 *  The opt-in wording is a compliance artifact, not copy: it must name GuildOS
 *  as the sender, say what gets texted, and carry the rates + STOP lines. It
 *  lives here so the signup form and the member toggle cannot drift apart.
 */

export const SMS_CONSENT_LABEL =
  'Text me at this number. GuildOS sends sign-in codes, dues and event reminders, ' +
  'and chapter announcements. Message and data rates may apply. Reply STOP to opt out.';

/** The roster CSV's header row, consent column included. */
export const ROSTER_CSV_HEADER = 'name,email,phone,role,consent';

export const ROSTER_CONSENT_NOTE =
  'Anyone imported without consent=yes is not texted until they opt in themselves.';

/** message_outbox.last_error written for a member who never opted in. */
export const NO_CONSENT = 'no_consent';

/** How a failed outbox row reads, and whether retrying could ever help.
 *  A no_consent row would fail identically forever — only the member can fix it. */
export function outboxFailure(error?: string): { text: string; retryable: boolean } {
  return error === NO_CONSENT
    ? { text: 'Not sent: member has not opted in to texts.', retryable: false }
    : { text: error || '', retryable: true };
}

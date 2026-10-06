/** SMS consent in the UI (#57, ops-runbook §6.1).
 *
 *  The opt-in wording is a compliance artifact, not copy: it must name GuildOS
 *  as the sender, say what gets texted, and carry the rates + STOP lines. It
 *  lives here so the signup form and the member toggle cannot drift apart.
 *
 *  Texts are now only the manual ones — chapter announcements and event
 *  notices an officer sends. Everything automatic (setup and reset codes,
 *  dues, jobs, security) goes by email and needs no consent.
 */

export const SMS_CONSENT_LABEL =
  'Text me at this number. GuildOS sends chapter announcements and event notices ' +
  'an officer sends out. Message and data rates may apply. Reply STOP to opt out.';

/** The roster CSV's header row, consent column included. */
export const ROSTER_CSV_HEADER = 'name,email,phone,role,consent';

export const ROSTER_CONSENT_NOTE =
  'consent=yes only affects chapter announcement texts. Anyone imported without it ' +
  'is not texted until they opt in themselves; everything else still reaches them by email.';

/** message_outbox.last_error written for a member who never opted in. */
export const NO_CONSENT = 'no_consent';

/** message_outbox.last_error written for an email with no address to send to. */
export const NO_EMAIL = 'no_email';

/** How a failed outbox row reads, and whether retrying could ever help.
 *  no_consent and no_email would fail identically forever — retrying cannot
 *  conjure an opt-in or an address, so both read as explanations instead. */
export function outboxFailure(error?: string, eventType?: string): { text: string; retryable: boolean; hint?: string } {
  const hint = eventType === 'SETUP_CODE' || eventType === 'RESET_CODE'
    ? { hint: 'This message carried a one-time code. Send the member a new code instead.' } : {};
  if (error === NO_CONSENT)
    return { text: 'Not sent: member has not opted in to texts.', retryable: false, ...hint };
  if (error === NO_EMAIL)
    return { text: 'Not sent: member has no email address.', retryable: false, ...hint };
  return { text: error || '', retryable: !hint.hint, ...hint };
}

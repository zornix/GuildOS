# Twilio real delivery requirements

Research note for [#54](https://github.com/zornix/GuildOS/issues/54) (map [#41](https://github.com/zornix/GuildOS/issues/41)).
Researched 2026-09-08. All Twilio/CTIA facts below were read on that date; fees and review
times are set by carriers and The Campaign Registry (TCR) and change without notice, so
re-check the numbers in the Console at registration time.

## The short version

We cannot flip `MESSAGE_DELIVERY_MODE=twilio` and expect messages to arrive. Twilio blocks
outright: *"Twilio blocks messages to U.S. numbers when you send from a +1 10DLC number
that is not associated with an approved A2P 10DLC Campaign."*
([Twilio error 30034](https://www.twilio.com/docs/api/errors/30034))

Two registration paths exist, plus one shortcut for codes only:

| Path | Sender | Setup time | Recurring cost | Fits us? |
| --- | --- | --- | --- | --- |
| A2P 10DLC, Low Volume Standard | regular +1 local number | ~2–3 weeks | ~$2/mo campaign | yes, the normal path |
| Toll-free verification | +1 8xx number | ~3 business days | none beyond the number | yes, and faster |
| Twilio Verify | Twilio-managed | ~none | per-verification | codes only, not announcements |

**Recommendation: start toll-free verification.** It clears in about three business days
instead of two to three weeks, needs no brand/campaign registration, carries no monthly
campaign fee, and one verified toll-free number covers every message type we send. Register
10DLC later only if a chapter objects to an 8xx sender or we outgrow toll-free throughput.

**The real blocker is not registration, it is consent.** Both paths reject submissions
whose opt-in evidence is thin, and today we have none: no consent checkbox, no consent
column in the database, no STOP/HELP handling, no public privacy page. See
[What we are missing](#what-we-are-missing-in-the-product).

## Why registration is required at all

A2P 10DLC is *"the standard that United States telecom carriers have put in place"* to
verify that application-sent SMS over local numbers is legitimate and consented. Everyone
sending application-initiated SMS to US numbers over a 10-digit long code must register —
*"including individuals and hobbyists"*. Unregistered senders face extra carrier fees,
heavy filtering, and (per error 30034) outright blocking.
([Twilio, Programmable Messaging and A2P 10DLC](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc), read 2026-09-08)

Registration has two layers:

- **Brand** — who we are. The legal entity, its EIN, address, website, contact person.
- **Campaign** — what we send. Use case, description, sample messages, and above all how
  recipients consented.

## Path A — A2P 10DLC

### Which brand tier

| Tier | Who qualifies | Limits |
| --- | --- | --- |
| Sole Proprietor | individuals/small businesses **with no Tax ID** | 1 campaign, 1 number, 1 MPS, ~1,000 segments/day to T-Mobile (~3,000 across carriers) |
| Low Volume Standard | US business with an EIN, under ~6,000 segments/day | up to 5 campaigns, 2,000 segments/day to T-Mobile |
| Standard | everyone larger | higher throughput, extra vetting |

A fraternity chapter organization almost certainly has an EIN (it needs one for a bank
account), and *"if you have a Tax ID, you should use a Low Volume Standard Brand instead"*
of Sole Proprietor. So: **Low Volume Standard**.
([Twilio, Sole Proprietor vs Low Volume Standard vs Standard](https://support.twilio.com/hc/en-us/articles/4407882914971-Comparison-between-Sole-Proprietor-Low-Volume-Standard-and-Standard-registration-for-A2P-10DLC), read 2026-09-08)

Volume sanity check: a few chapters at tens to a few hundred members each, sending setup
codes, reset codes, announcements and dues reminders, is nowhere near 2,000 segments/day.
Low Volume Standard is comfortably sized.

### Nonprofit status matters for the fee, not the path

Nonprofits register with business type *"Non-profit Corporation"* and business industry
*"Not for profit"*, and *"have access to additional Special Use Cases, such as
Charity/501(c)(3)"*.
([Twilio, A2P 10DLC registration for government and nonprofit agencies](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/onboarding-for-government-and-non-profit-agencies), read 2026-09-08)

The discount is narrow. Only 501(c)(3) organizations get the Charity use case and its
carrier-fee discounts; other 501(c) designations *"[use] standard campaign use cases only"*.
([Twilio changelog, 2021-08-25](https://www.twilio.com/en-us/changelog/a2p-10dlc-registration-for-all-us-501-c--nonprofit-organizations))

Social fraternities are usually 501(c)(7), not (c)(3), so **assume no discount** unless the
owner's IRS determination letter says 501(c)(3). Worth checking — it is a one-minute look at
a letter and it changes the monthly fee.

### Which campaign use case

TCR use cases relevant to us
([Twilio, list of campaign use case types](https://support.twilio.com/hc/en-us/articles/1260801844470-List-of-campaign-use-case-types-for-A2P-10DLC-registration), read 2026-09-08):

- `2FA` — *"Any authentication or account verification such as one-time-passcodes (OTP)"* —
  covers setup codes and password reset codes.
- `ACCOUNT_NOTIFICATION` — *"Notifications about the status of an account"* — covers dues
  reminders, invoice/payment notices, job and event notifications.
- `CUSTOMER_CARE` — covers officer announcements.
- `MIXED` — *"a campaign that covers multiple use cases"*.

We send all three kinds from one number, so we need **Mixed** — specifically the *Low Volume
Mixed* variant, which *"supports the same multiple use cases as the standard Mixed/Marketing
use case, but has a lower monthly fee"* and is *"fixed at the lowest throughput tier"* (under
2,000 segments/day to T-Mobile). That fits us.

Do not describe any message as promotional or as recruitment marketing in the campaign
description — Mixed campaigns that read as marketing draw stricter review and higher
per-message carrier fees.

### Cost

One-time:

- Low Volume Standard brand registration: **$4** per Twilio's announcement
  ([Twilio blog, New Requirements for A2P 10DLC Registrations](https://www.twilio.com/en-us/blog/new-requirements-for-a2p-10dlc-registrations)),
  reported elsewhere as $4.50; treat as "under $5". No Secondary Vetting (that $40 charge
  applies to Standard brands).
- Campaign vetting: **$15**. *"All Twilio US A2P 10DLC Campaign registrations (Standard, Low
  volume standard, and Sole Proprietor) are subject to a manual vetting process and are
  charged a $15 campaign verification fee at the time of vetting."*
  ([Twilio, A2P 10DLC Campaign Vetting FAQ](https://support.twilio.com/hc/en-us/articles/11587910480155-A2P-10DLC-Campaign-Vetting-FAQ), read 2026-09-08)

Recurring:

- Campaign monthly fee: **$1.50–$10 depending on use case**; Low Volume Mixed sits at the
  bottom of that band (~$2/mo). Charity/501(c)(3), if we qualified, is ~$3/mo but with
  carrier-fee discounts. ([Twilio blog, as above](https://www.twilio.com/en-us/blog/new-requirements-for-a2p-10dlc-registrations))
- Phone number: **$1.15/mo** for a local long code.
- Per message: **from $0.0083** outbound, plus carrier surcharges per segment —
  AT&T $0.0035, T-Mobile $0.0045, Verizon $0.0045, US Cellular $0.005.
  Failed-message processing $0.001.
  ([Twilio US SMS pricing](https://www.twilio.com/en-us/sms/pricing/us), read 2026-09-08)

Realistic total for the pilot: **under $25 to set up, well under $10/month plus traffic.**
Cost is not the obstacle here; time and consent evidence are.

### Timeline

Twilio's own numbers ([Direct Standard and Low-Volume Standard Registration Guide](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/direct-standard-onboarding),
[A2P 10DLC quickstart](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/quickstart), read 2026-09-08):

1. Customer Profile (Trust Hub): *"It may take 72 hours or more for Twilio to approve your
   Customer Profile."*
2. Brand: *"TCR review typically occurs within a few minutes"*; a manual review takes
   *"seven business days or more"*. An OTP is texted to the brand contact and must be
   answered **within 24 hours**.
3. Campaign: *"This process can take between two to three weeks to complete"*, and as of the
   docs read date *"campaign reviews are taking 10–15 days"*.

Active work is about 15 minutes. The rest is waiting. *"Most application failures occur in
step 3 (campaign registration)"* — that is the consent evidence.

The account must be a **paid** Twilio account; trial accounts cannot register.

## Path B — Toll-free verification

Instead of a local number, buy a toll-free (8xx) number and submit a verification. No brand,
no campaign, no TCR, no monthly campaign fee.

**Review time: *"Twilio reviews TFV requests within three business days."*** Approved numbers
*"send Application to Person (A2P) SMS messages with minimal traffic filtering."*
([Twilio, toll-free verification API onboarding](https://www.twilio.com/docs/messaging/compliance/toll-free/api-onboarding), read 2026-09-08)

The submission asks for:

- business name, website, address, contact name/email/phone, notification email
- **business registration number** — an EIN satisfies this. Required for all business types
  except sole proprietorships for new submissions **as of 2026-02-17**
  ([Twilio changelog, Business Registration Numbers Required for Toll-Free Messaging Traffic](https://www.twilio.com/en-us/changelog/business-registration-numbers-required-for-toll-free-messaging-p))
- business type: one of `PRIVATE_PROFIT`, `PUBLIC_PROFIT`, `SOLE_PROPRIETOR`, `NON_PROFIT`,
  `GOVERNMENT`
- use case category (includes `TWO_FACTOR_AUTHENTICATION`), a use case summary, and a
  production message sample
- **opt-in type**: `VERBAL`, `WEB_FORM`, `PAPER_FORM`, `VIA_TEXT`, `MOBILE_QR_CODE`, or `IMPORT`
- **opt-in image URLs** — publicly hosted screenshots of the opt-in workflow
- estimated monthly message volume

Costs: toll-free number **$2.15/mo**; per-message and carrier fees are the same as long
codes (*"Toll-free numbers have identical carrier fees as long codes"*). Verification itself
carries no fee in the published pricing.
([Twilio US SMS pricing](https://www.twilio.com/en-us/sms/pricing/us), read 2026-09-08)

### When toll-free is better, and when it is not

Better when: you want to send within days rather than weeks; you have one sender for a
handful of small chapters; you do not want a monthly campaign fee or TCR paperwork.
That is exactly the pilot.

Worse when: chapters care that texts come from an 8xx number rather than a local one
(members do read 8xx as commercial), or when volume grows past what toll-free comfortably
carries and 10DLC's tiered throughput becomes the point.

Note toll-free's opt-in review is if anything **stricter** than 10DLC's — it wants a
publicly reachable image of the opt-in flow, not just a written description. Whichever path
we take, the opt-in has to be real and photographable.

## Path C — Twilio Verify, for codes only

*"With Twilio Verify, you do not need to worry about A2P registration (Brand or Campaign) or
any other aspect of sender provisioning"*, and *"If you are seeking to register your Brand
solely in the service of an OTP use case ... you should investigate Twilio's Verify service."*
([Twilio, Programmable Messaging and A2P 10DLC](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc), read 2026-09-08)

That covers setup codes and password reset codes with zero registration. It does **not**
cover announcements or dues reminders — Verify only sends verification codes it generates
and checks itself, and it would mean a second delivery path in `twilio_client.py` alongside
the outbox. Not worth it unless registration stalls and unblocking member login becomes
urgent; then it is a genuine escape hatch for codes alone.

## Consent — the part that actually blocks us

### What Twilio requires

Twilio's Messaging Policy (effective **2026-04-13**) requires *"prior express consent from
the message recipient in accordance with all applicable laws and regulations."* Consent
*"must be freely given by each recipient to each sender for each message subject ... and
must be informed and unambiguous."* Recipients must be told who the sender is, what the
messages are about, and how to opt out.
([Twilio Messaging Policy](https://www.twilio.com/en-us/legal/messaging-policy), read 2026-09-08)

Crucially for us, the policy puts **OTPs and reminders in the same consent bucket**:
*"password reset or one-time verification code notifications, appointment reminders, order
confirmations, or payment receipts"* all require prior express consent. A setup code is not
exempt because it is transactional. And *"any consent that you obtain from a recipient is
strictly for the subject matter for which that recipient provided their consent"* — so
consent collected for "login codes" does not cover dues reminders. **Collect consent once,
for all chapter messages, and say so in the wording.**

Twilio requires the sender to keep proof: consent records must be retained *"for as long as
needed to meet your legal requirements and at least until a recipient withdraws their
consent"*, and Twilio may ask for *"the date and the method through which that consent was
obtained."*

Opt-out: the first message must carry *"Reply STOP to unsubscribe"* or equivalent, the
process must be *"straightforward and easily accessible, requiring a single step"*, and after
a STOP only one confirmation message may be sent. STOP, STOPALL, UNSUBSCRIBE, OPTOUT,
CANCEL, END, REVOKE and QUIT must all work. Every message must identify the sender.

### What counts as express consent

From Twilio's toll-free rejection docs, express consent is *"a voluntary, informed end user
choice for a specific purpose"* requiring *"upfront disclosure and intentional action"*.
A web checkbox *"must be unchecked by default"*. Explicitly: *"Listing 'SMS' in your Terms
of Service or Privacy Policy is not Express Consent."*
([Twilio error 30446](https://www.twilio.com/docs/api/errors/30446), read 2026-09-08)

Related rejections worth avoiding: consent cannot be a condition of using the service
([30475](https://www.twilio.com/docs/api/errors/30475)), the opt-in must be optional rather
than required ([30505](https://www.twilio.com/docs/api/errors/30505)), and the flow must
explicitly say "SMS"/"text messages" ([30513](https://www.twilio.com/docs/api/errors/30513)).

CTIA's October 2025 Messaging Principles tightened the wording: opt-in language must state
what type of messages will be sent, at what frequency, and from which brand; the opt-in must
be confirmed in the first message; STOP/UNSUBSCRIBE/CANCEL must be honored and HELP must
return support contact information.
([CTIA Messaging Security Best Practices, October 2025](https://api.ctia.org/wp-content/uploads/2025/10/Messaging-Security-Best-Practices-_October-2025.pdf);
summarized via search 2026-09-08 — the PDF did not extract cleanly, so treat the specifics
as secondary and confirm against [ctia.org/messaging](https://www.ctia.org/messaging) before
finalizing copy.)

### The awkward bit for our onboarding flow

Our pilot flow is: an officer hands over a roster, we text each new member a setup code. The
member never filled in a form. That is not consent, and it is the single most likely reason a
campaign or toll-free submission gets rejected — and the most likely reason a carrier
complaint lands later.

Twilio accepts non-web opt-in types (`VERBAL`, `PAPER_FORM`, `IMPORT`), so the fix does not
require a signup page. It requires that **the chapter collect consent before we import the
roster**, and that we can produce the evidence. Concretely, one of:

- a paper or digital roster form each member signs at chapter onboarding, with the SMS
  consent line and an unchecked/blank opt-in box (`PAPER_FORM`), or
- a short web page members visit once to confirm their number (`WEB_FORM`), which doubles as
  the publicly hosted screenshot toll-free verification wants.

The web page is the better answer if we build anything: it produces a timestamped record
automatically and a screenshot we can link in the submission. The paper form is the answer if
the pilot must start next week.

### Consent wording to use

Put this next to an unchecked box on the form or page, with the chapter's real name:

> ☐ I agree to receive text messages from **[Chapter Name]** about my membership — login and
> password reset codes, chapter announcements, event notices, and dues reminders. Message
> frequency varies (roughly 2–10 messages per month). Message and data rates may apply.
> Reply STOP to opt out, HELP for help.

Records to keep per member, and to be able to export on demand:

- phone number as consented (E.164)
- consent timestamp
- consent method (`WEB_FORM` / `PAPER_FORM` / `VERBAL`) and, for paper, a scan
- the exact wording shown at the time (version it, do not paraphrase later)
- opt-out timestamp if they STOP

### Message copy changes

- **First message to any member must carry the opt-out line.** The setup-code text is that
  first message today. Add "Reply STOP to opt out." to it.
- **Every message must identify the sender** — the chapter name, not "GuildOS". Our current
  templates in `LocalDev/api/cron/core/templates.py` do neither.
- HELP must return support contact information. Twilio's built-in Advanced Opt-Out on a
  Messaging Service handles STOP/HELP replies without app code; use it rather than writing
  our own keyword handler.

## What we are missing in the product

Checked in `LocalDev/` on 2026-09-08:

- **No consent record.** No `opt_in` / `opt_out` / `sms_consent` column anywhere in
  `migrations/`. There is nowhere to store the consent date and method Twilio may ask for.
- **No opt-out state.** `message_outbox` has no consent gate; a drained message goes to
  anyone on the roster. A member who replies STOP is suppressed by Twilio at the carrier
  edge, but we would keep enqueuing and keep paying for failures — and we would not know.
- **No STOP/HELP wiring.** No inbound webhook, no Advanced Opt-Out configured (a Messaging
  Service setting, not code).
- **No sender identity or opt-out line in templates.**
  `LocalDev/api/cron/core/templates.py` renders bodies like `"New charge: $12.34 — dues.
  Log in to view."` — no chapter name, no STOP line.
- **No public privacy policy or terms page.** `greekos-landing/` has neither. Both
  registration paths ask for a website; the campaign `message_flow` field wants links to the
  privacy policy and terms, and toll-free wants a publicly hosted opt-in screenshot.
- **`TWILIO_FROM_NUMBER` is a bare number.** For 10DLC, and for Advanced Opt-Out, the sender
  must belong to a **Messaging Service**; sending from a raw number that is not attached to
  an approved campaign is what error 30034 blocks. Sending via a Messaging Service SID means
  passing `MessagingServiceSid` instead of `From` in
  `LocalDev/api/announcements/services/twilio_client.py`.

None of that is large, and none of it should be built before the owner decides which path.
Sequence: owner picks the sender type and collects consent → we add the consent column,
the STOP line and the sender name → register → flip `MESSAGE_DELIVERY_MODE`.

## Owner checklist (manual steps)

1. Confirm the chapter organization's **legal name, EIN, and address** as they appear on the
   IRS letter, and check whether it is 501(c)(3) — that decides the nonprofit discount.
2. Upgrade the Twilio account to **paid** (trial accounts cannot register or verify).
3. Put a **public page** online with the chapter's privacy policy, terms, and the SMS
   disclosure. Registration reviewers will open it.
4. Decide how members consent: a **signed paper/web form at chapter onboarding**, with an
   unchecked SMS box and the wording above. Nothing sends until this exists.
5. Collect consent from every pilot member, and keep the **date, method, and wording** per
   person. Screenshot or scan the form — the submission needs a publicly reachable image.
6. **Buy a toll-free number** and submit toll-free verification (business info, EIN, use case
   summary, sample message, opt-in type + screenshot, volume estimate). Expect ~3 business days.
7. If a local number is required instead: create the **Trust Hub Customer Profile** (~72h),
   register a **Low Volume Standard brand** (answer the OTP text within 24h), then a **Low
   Volume Mixed campaign** (10–15 days). Budget ~$20 one-time and ~$2/month.
8. Create a **Messaging Service**, attach the verified/registered number, and turn on
   **Advanced Opt-Out** so STOP and HELP are handled by Twilio.
9. Hand us the **Messaging Service SID**; we switch the sender from a bare `From` number and
   flip `MESSAGE_DELIVERY_MODE=twilio`.
10. Re-check all fees in the Console before submitting — carriers and TCR change them.

## Sources

All read 2026-09-08.

- [Twilio — Programmable Messaging and A2P 10DLC](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc)
- [Twilio — A2P 10DLC registration quickstart](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/quickstart)
- [Twilio — Direct Standard and Low-Volume Standard Registration Guide](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/direct-standard-onboarding)
- [Twilio — Gather the required business information](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/collect-business-info)
- [Twilio — Registration for government and nonprofit agencies](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/onboarding-for-government-and-non-profit-agencies)
- [Twilio — Comparison: Sole Proprietor, Low Volume Standard, Standard](https://support.twilio.com/hc/en-us/articles/4407882914971-Comparison-between-Sole-Proprietor-Low-Volume-Standard-and-Standard-registration-for-A2P-10DLC)
- [Twilio — List of campaign use case types](https://support.twilio.com/hc/en-us/articles/1260801844470-List-of-campaign-use-case-types-for-A2P-10DLC-registration)
- [Twilio — A2P 10DLC Campaign Vetting FAQ](https://support.twilio.com/hc/en-us/articles/11587910480155-A2P-10DLC-Campaign-Vetting-FAQ)
- [Twilio blog — New Requirements for A2P 10DLC Registrations](https://www.twilio.com/en-us/blog/new-requirements-for-a2p-10dlc-registrations)
- [Twilio changelog — A2P 10DLC registration for all US 501(c) nonprofits (2021-08-25)](https://www.twilio.com/en-us/changelog/a2p-10dlc-registration-for-all-us-501-c--nonprofit-organizations)
- [Twilio — Toll-free verification via the API](https://www.twilio.com/docs/messaging/compliance/toll-free/api-onboarding)
- [Twilio — Toll-free verification console onboarding](https://www.twilio.com/docs/messaging/compliance/toll-free/console-onboarding)
- [Twilio changelog — Business Registration Numbers required for toll-free (effective 2026-02-17)](https://www.twilio.com/en-us/changelog/business-registration-numbers-required-for-toll-free-messaging-p)
- [Twilio — Messaging Policy (effective 2026-04-13)](https://www.twilio.com/en-us/legal/messaging-policy)
- [Twilio — US SMS pricing](https://www.twilio.com/en-us/sms/pricing/us)
- [Twilio error 30034 — message from an unregistered number](https://www.twilio.com/docs/api/errors/30034)
- [Twilio error 30446 — opt-in not sufficient, express consent required](https://www.twilio.com/docs/api/errors/30446)
- [Twilio error 30475 — cannot combine messaging consent with service requirement](https://www.twilio.com/docs/api/errors/30475)
- [Twilio error 30505 — opt-in must be optional, not required](https://www.twilio.com/docs/api/errors/30505)
- [Twilio error 30513 — opt-in language unclear](https://www.twilio.com/docs/api/errors/30513)
- [Twilio error 30516 — double opt-in required for this use case](https://www.twilio.com/docs/api/errors/30516)
- [CTIA — Messaging Security Best Practices, October 2025](https://api.ctia.org/wp-content/uploads/2025/10/Messaging-Security-Best-Practices-_October-2025.pdf) (secondary; PDF did not extract cleanly)

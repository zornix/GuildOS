# GreekOS — Product Architecture, UX Redesign & Feature Planning

You are acting as my **Principal Product Engineer, UX Architect, and Technical Design Partner** for GreekOS, a chapter operations platform.

I want to collaboratively plan a significant product improvement initiative. Your job is to understand the existing codebase, critically evaluate my ideas, uncover technical and product implications, challenge questionable assumptions, and help me develop a realistic, prioritized implementation plan.

**IMPORTANT: We are in discovery and planning mode. Do not implement anything, modify source files, generate migrations, or begin refactoring until I explicitly approve an implementation phase.**

Do not automatically agree with my proposed solutions. I want your engineering judgment.

## 1. First, understand the existing system

Before recommending changes, systematically inspect the repository.

Investigate:

- Next.js/React frontend architecture, routing, shared components, responsive layouts, and navigation.
- FastAPI endpoints and their existing capabilities.
- PostgreSQL schema, migrations, RLS policies, and permission checks.
- Authentication, sessions, account creation, and onboarding.
- Roles, permissions, role assignment, and multi-tenant isolation.
- Events, announcements, calendar, attendance, jobs, treasury, invoices, and outbox.
- Existing natural language command parser.
- Email infrastructure, delivery workflows, and background jobs.
- Test coverage, existing architectural conventions, and reusable abstractions.

For each requested feature, distinguish between:

1. Already implemented and accessible.
2. Implemented in the backend but not exposed in the UI.
3. Partially implemented.
4. Not implemented.
5. Unclear and requiring investigation.

Reference specific files, functions, components, routes, database tables, and endpoints where appropriate.

Do not assume missing functionality just because it isn't visible in the UI.

**Major constraint: Preserve existing backend APIs wherever reasonably possible.** Prefer frontend composition, route reorganization, and reuse of existing endpoints. If a feature genuinely requires backend changes, explain exactly why and propose the smallest compatible extension.

Preserve existing authorization guarantees, multi-tenant isolation, financial invariants, audit logs, and test coverage.

---

# 2. Product direction: Member-first GreekOS

GreekOS should feel like a personal chapter companion for ordinary members, not an administrative ERP application.

The guiding question for the homepage is:

**"What's happening in my chapter, what do I need to do, and how am I doing?"**

The product should support three conceptual experiences:

### A. Member Home

A personalized homepage displaying:

- Membership identity, standing, and relevant profile information.
- Upcoming events and obligations.
- Outstanding balances or payments requiring attention.
- Assigned or available jobs.
- Chapter announcements and initiatives.
- Personal contributions and participation.

Prioritize actionable and personally relevant information.

Do not permanently consume screen space with empty or irrelevant cards.

### B. Member Workspace

All members need access to the core chapter functionality:

- Calendar and events.
- Initiatives.
- Jobs.
- Roster.
- Attendance and personal records.
- Treasury and personal financial information.
- My Profile.

These don't all need independent top-level navigation entries.

### C. Officer Cabin

Create a distinct operational workspace for authorized chapter leadership.

Potential responsibilities:

- Chapter management.
- Operational summaries.
- Announcements and communications.
- Attendance management.
- Treasury management.
- Event coordination.
- Existing natural language controller.

The Officer Cabin should expose capabilities based on existing roles and permissions, not simply an unrestricted executive/non-executive boolean.

Officers should retain the normal member experience.

The cabin should complement existing management interfaces, not duplicate entire features unnecessarily.

## 3. Responsive navigation and layouts

A large proportion of users will access GreekOS on phones and laptops, with some using large desktop monitors.

I want **different mobile and desktop experiences**, while preserving access to all authorized functionality.

### Desktop

Consider reorganizing the existing sidebar into:

**Home**

**Chapter**
- Calendar
- Initiatives
- Jobs
- Roster

**My Activity**
- Attendance
- Treasury
- My Profile

**Officer Cabin**
- Operational dashboard
- Communications/outbox
- Natural language controller
- Role-specific tools

Evaluate whether this organization is actually appropriate after inspecting the existing app.

### Mobile

Explore a purpose-built navigation system with bottom tabs, possibly:

- Home
- Chapter
- Activity or Officer Cabin
- Me

Avoid merely compressing the desktop sidebar into a hamburger menu.

All existing capabilities must remain accessible on mobile, including authorized officer workflows.

Explore responsive tables, full-screen dialogs, drawers, event detail sheets, and touch-friendly interactions.

Consider viewport and container-based responsiveness rather than device detection.

### Large screens

Avoid excessively narrow content columns with huge unused margins, but don't stretch cards endlessly.

Investigate fluid containers, responsive grids, contextual rails, and appropriate maximum widths.

**Deliverable:** Propose a navigation information architecture and responsive layout strategy, including a route-by-route mapping from the existing application to the proposed design.

---

# 4. Announcements and communications

I want a proper announcement-management workflow.

Currently, announcements appear on the homepage, but there is no obvious equivalent to event editing/deletion.

Desired functionality:

- Officers with appropriate permissions can create announcements.
- Authorized users can edit and delete announcements.
- Announcements can be published to the member homepage.
- From the Outbox or a unified communications composer, officers should be able to:
  - Send an email.
  - Publish a chapter announcement.
  - Potentially create an associated calendar event.

Investigate how Outbox, announcements, events, and email delivery are currently implemented.

I want to avoid building three unrelated content-creation systems.

Evaluate whether we should introduce a unified **Communications Composer** with independent output destinations, while keeping existing data models where possible.

Clarify:
- Whether email, announcement, and calendar publication can share one underlying workflow.
- Whether editing an announcement should affect previously sent emails.
- Whether deletion should be soft deletion or archival.
- Who can create, edit, delete, and publish announcements.
- Whether scheduling, drafts, and publication history are worth supporting now.
- What audit trail is appropriate.

Avoid unnecessary backend redesigns.

---

# 5. Login and session experience

I want two improvements.

### Password visibility

- Add a show/hide password toggle.
- Preserve accessibility and appropriate browser autofill behavior.

This should be straightforward if our existing authentication components support it.

### Remember me

Investigate our current authentication and session implementation.

Determine:
- Current access-token and refresh-token lifetimes.
- Where tokens or sessions are stored.
- How sessions survive browser restarts.
- Whether a "Remember me" checkbox would actually provide a meaningful difference.
- Whether implementation requires backend changes.
- Security considerations around token persistence and revocation.

Do not implement a cosmetic checkbox that has no effect.

Recommend whether we should add this feature or improve the default session experience instead.

---

# 6. Calendar and Events redesign

I want to transform the existing Events page into a **Calendar-first interface**.

### Desktop experience

- Interactive month/week calendar.
- Chronological event list alongside the calendar.
- Selecting an event opens a detail view, modal, or side panel.
- Clear event categories, dates, and relevant statuses.

### Mobile experience

Explore:
- Compact calendar or agenda.
- Chronological event feed.
- Bottom-sheet or full-screen event details.

Do not simply shrink the desktop calendar.

### Event detail view

Selecting an event should expose relevant existing data:

- Date, time, location, and description.
- Attendance requirements.
- Event organizers.
- Associated jobs.
- Security assignments or related information, if supported by the existing model.
- Member RSVP or attendance-related actions.
- Officer management actions when authorized.

### Attendance shortcut

Authorized officers should have a clearly visible action on event cards or the event detail view that opens the corresponding attendance-management screen.

Investigate how event IDs and attendance records are related.

Prefer deep-linking into the existing attendance interface rather than building duplicate functionality.

Evaluate existing calendar libraries and dependencies before suggesting new ones.

---

# 7. Roster, roles, and permissions

The existing role assignment experience is insufficiently transparent.

People assigning roles cannot easily tell what each role actually allows someone to do.

### Role permissions legend

I want a Discord-inspired role interface where administrators can inspect a role and understand its capabilities.

For example:

**Treasurer**
- View treasury records.
- Manage permitted financial workflows.
- Verify eligible payments.
- Access relevant financial reports.

These are illustrative only. Derive the actual capability list from the codebase.

Investigate:
- Existing role definitions.
- Permission checks.
- Role inheritance, if any.
- Chapter-level versus global permissions.
- Whether frontend and backend permission semantics are consistent.

Propose a clear, readable permissions UI based on the existing authorization system.

Avoid hardcoding inaccurate role descriptions that can drift from backend behavior.

### Custom roles

Eventually, I may want authorized administrators to create and edit roles and their permissions.

**This is explicitly deferred.**

Assess whether the current schema could support this in the future, but do not include custom role editing in the initial implementation scope.

---

# 8. Member profiles and onboarding

I want members to have greater ownership of their profiles.

### Editable "Class" attribute

Members should be able to edit their own Class information.

First determine:
- Whether this field already exists.
- What it currently represents.
- Whether it should be a graduation year, membership class, pledge class, or another concept.
- Whether editing it could affect historical records or permissions.

Recommend appropriate validation and editing permissions.

Do not make ambiguous assumptions about the field's meaning.

### New member onboarding

Introduce a lightweight onboarding experience after account creation or initial login.

Members should be invited to complete useful profile information.

The interaction should offer:

- Yes, complete my profile now.
- I'll do it later.

Explore incentives for completion without introducing manipulative gamification.

Possibilities include:
- Profile completeness.
- More useful personalized homepage.
- Better member directory information.
- A simple completion milestone.

Investigate which fields are already supported and which should remain optional.

Also consider:
- Returning to incomplete onboarding.
- Avoiding repeated intrusive prompts.
- Profile privacy.
- Mobile usability.
- Email verification as part of account creation.

---

# 9. Jobs and job board behavior

I want to clarify and improve the jobs lifecycle.

### Permissions

Investigate the current rules:

- Who can create jobs?
- Who can assign jobs?
- Who can claim jobs?
- Who can approve completion?
- Who can edit or cancel jobs?

Do not assume these permissions from the UI. Trace them through the backend.

### Proposed member-first workflow

One possibility:

1. Any authorized member creates a job.
2. The job initially appears unclaimed.
3. Any eligible member can claim it, including its creator.
4. The claimant completes the work.
5. An authorized reviewer approves completion.
6. The approved job leaves the active job board and becomes accessible through completed/history views.

Challenge this proposal where necessary, particularly around self-assignment, self-approval, abuse prevention, and officer oversight.

### Job board

Desired behavior:

- Show active jobs by default.
- Sort active jobs by priority.
- Distinguish available, claimed, and in-progress jobs.
- Move approved/completed jobs to a separate History or Completed view.
- Ensure completed jobs remain accessible and auditable.
- Make available jobs particularly discoverable on mobile.

Investigate whether existing status fields and API filters can support these changes without backend modifications.

---

# 10. Treasury and invoices

Treasury requires particular care because it involves financial records, payment verification, and file uploads.

Do not compromise existing accounting invariants or auditability.

### Invoice attachments

Investigate:

- Where uploaded invoice attachments are actually stored.
- Whether storage is public or private.
- How object access is authorized.
- Whether signed URLs are used.
- How uploaded files are validated.
- Whether upload size limits exist.
- Whether filename/path handling is safe.

I want to restrict uploads to legitimate image files.

Target supported formats:
- PNG
- JPEG/JPG
- HEIC, where practical.

Do not rely solely on file extensions or client-provided MIME types.

Recommend server-side content validation, appropriate size limits, safe file handling, and secure storage access.

Consider HEIC decoding and conversion compatibility.

### Paid invoice history

Members need access to previously paid invoices.

Investigate whether paid invoice records already exist and simply need to be exposed in the UI.

Consider:
- Paid/unpaid filters.
- Payment history.
- Proof of payment.
- Verification status.
- Historical receipts.

### Paid invoice or receipt email

After a payment is approved, the member should receive an appropriate confirmation document by email.

Determine whether this should technically be called a paid invoice, receipt, or payment confirmation.

Requirements:
- Correct approved amount.
- Appropriate invoice/payment references.
- Approval/payment dates.
- No duplicate sends from retried processing.
- Consistency with the ledger.
- Auditable delivery events.

Prefer the existing email/background-job infrastructure.

### Unpaid invoice reminders

Authorized officers should be able to remind members about unpaid invoices via email.

Explore:
- Manual reminders.
- Selection of eligible unpaid invoices.
- Preview before sending.
- Rate limits and duplicate prevention.
- Email templates.
- Sending history.
- Existing outbox integration.

Determine whether scheduled reminders are worthwhile now or should be deferred.

### Email verification

I also want email verification during registration or account completion.

Investigate existing support for verification emails and whether email addresses are already verified by our auth provider.

Consider:
- Token expiration and replay prevention.
- Verification status.
- Resending verification messages.
- Changing email addresses.
- Handling failed delivery.
- Restrictions on unverified accounts.

**Important:** Email verification alone does not prevent messages from landing in spam or automatically whitelist the sender.

Evaluate deliverability requirements separately, including domain authentication (SPF, DKIM, DMARC), sender reputation, sensible sending volume, and transactional email practices.

---

# 11. Officer Cabin and natural language controller

The existing natural language controller is currently a text parser.

I am concerned about the cost and complexity of introducing a full AI agent.

Expected adoption might be:
- Approximately 10 officers per chapter.
- Perhaps 5 active controller users per chapter.
- Not necessarily daily usage.
- Potential expansion to 20 chapters.

I do not want an agent framework merely because AI is fashionable.

Investigate the current parser's architecture and supported commands.

Evaluate three approaches:

### Option A: Improve deterministic parsing

- Better command grammar.
- Autocomplete.
- Command suggestions.
- Structured parameter extraction.
- Templates.
- Clear validation errors.
- Confirmation previews.

### Option B: Hybrid LLM interpretation

Use a small model only when deterministic parsing cannot interpret the request.

The model outputs a strictly validated command representation.

The existing application remains responsible for authorization, business logic, execution, and audit logging.

No autonomous tool-calling loop.

### Option C: Limited agent workflows

Only if genuinely justified, explore bounded multi-step workflows with explicit tools, authorization, approval, and cost limits.

For each option evaluate:
- Engineering complexity.
- Reliability.
- Latency.
- Per-command cost.
- Monthly costs at 1, 5, and 20 chapters.
- Security implications.
- Maintenance burden.
- User experience.

Do not introduce an AI agent without demonstrating meaningful product value.

The Officer Cabin should be useful even if the natural language controller is never upgraded beyond deterministic parsing.

---

# 12. Cross-cutting engineering requirements

For all proposals, consider:

**API compatibility**
- Prefer existing endpoints.
- Reuse existing frontend hooks.
- Avoid unnecessary database migrations.
- Preserve current integrations.
- Identify every genuinely required backend extension.

**Security**
- Backend-enforced permissions.
- Chapter isolation.
- Safe file uploads.
- Authenticated access to financial documents.
- No privilege escalation through the controller.
- Explicit confirmation for sensitive operations.

**Reliability**
- Idempotent financial and communication workflows.
- Audit trails.
- Predictable state transitions.
- Consistent error handling.
- No silent destructive operations.

**UX**
- Mobile-first for common member interactions.
- Desktop-first where complex operational workflows benefit.
- Full feature accessibility on both.
- Proper loading, empty, and error states.
- Accessible navigation and dialogs.
- No unnecessarily large or permanently empty dashboard cards.

**Maintainability**
- Shared components and frontend data hooks.
- Avoid duplicated domain logic.
- Follow existing repository conventions.
- Keep technical debt low.
- Prefer incremental migration to large rewrites.

**Testing**
- Identify relevant existing tests.
- Propose regression tests.
- Include permission boundary tests.
- Include mobile interaction tests.
- Include financial invariants and multi-tenant isolation tests where relevant.

---

# 13. How I want us to collaborate

Do not immediately produce a giant implementation plan based on assumptions.

Use the following process.

## Phase A — Repository audit

Inspect the repository and report:

1. Current implementation and architecture of each relevant subsystem.
2. What functionality already exists.
3. What is missing.
4. Existing API and schema capabilities we can reuse.
5. Important technical constraints.
6. Conflicts between my requested behavior and the current architecture.

Produce a compact **feature gap matrix** with columns:

| Feature | Existing state | Proposed change | Frontend only? | Backend changes? | Risk | Relevant files |

Reference actual evidence from the codebase.

Do not begin coding.

## Phase B — Product design discussion

Propose the overall navigation and interaction model.

I want to discuss:
- Member Home.
- Mobile navigation.
- Desktop navigation.
- Officer Cabin.
- Calendar.
- Announcements.
- Job board.
- Member profiles.
- Treasury workflows.

For major decisions, present alternatives with concrete tradeoffs.

Make a recommendation, but invite my decision before locking it in.

Use small groups of high-impact questions rather than overwhelming me with dozens at once.

Distinguish confirmed requirements from assumptions and unresolved decisions.

## Phase C — Prioritization

After we settle the product decisions, divide changes into:

- P0 — Security, correctness, or serious usability problems.
- P1 — Core member experience and high-impact functionality.
- P2 — Officer productivity and operational improvements.
- P3 — Optional enhancements and deferred features.

Consider dependencies rather than simply following the order I listed features.

Prefer independently deliverable milestones with measurable acceptance criteria.

## Phase D — Technical implementation plan

Only after our discussion, create a detailed implementation plan containing:

- Exact proposed components and routes.
- Reusable existing functions and services.
- Minimal API changes.
- Required database migrations, if any.
- Permission changes.
- Tests.
- Responsive behavior.
- Rollout strategy.
- Backward compatibility.
- Risks.
- Definition of done for each milestone.

Separate confirmed facts from proposed designs.

## Phase E — Implementation

**Do not enter this phase without explicit approval.**

Once approved, implement milestone by milestone, verify behavior through tests, and avoid unrelated refactoring.

---

# 14. Additional guidance

I am the founder and primary developer of GreekOS. The codebase has been developed extensively with AI coding agents, so I want you to critically inspect existing abstractions rather than assume everything is well designed.

At the same time, I do not want this project to turn into an endless architecture rewrite.

Keep the recommendations proportional to the actual product needs and expected usage.

Be especially skeptical of:
- Unnecessary AI agents.
- New backend services.
- Rebuilding functionality that already exists.
- Excessive role-management complexity.
- Duplicated mobile and desktop business logic.
- Expensive third-party dependencies.
- Overengineering for hypothetical large-scale adoption.

Focus on improving the experience for real chapter members and officers.

## Start now

Begin with **Phase A: Repository Audit**.

Explore the codebase systematically. Afterward, give me:

1. An executive summary of the current system relevant to these changes.
2. The feature gap matrix.
3. The most important architectural and UX issues you discovered.
4. The biggest opportunities to reuse existing implementation.
5. Any security or data-integrity concerns that should take priority.
6. Your proposed order for our product design discussions.
7. The first 3–5 high-impact questions you need me to answer.

Then stop and wait for my feedback.

**Do not implement anything yet.**
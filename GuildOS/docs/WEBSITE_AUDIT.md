# Website Audit

Last updated: 2026-04-20

Scope: local development copy in `GuildOS/fratos`, reviewed against the current Web Interface Guidelines.

## Functional Audit

The current website is an attendance and accountability MVP. It supports officer login, dashboard metrics, events, check-in links, attendance rosters, excuses, fines, members, and standing. It does not yet expose dedicated VP or Secretary modules.

Strengths:
- Clear operational shell with officer/member role awareness.
- Events flow already has useful primitives for VP features: event creation, required attendance, fines, check-in links, attendance roster, manual check-in, and excuse handling.
- Dashboard already aggregates upcoming events, pending excuses, and unpaid fines.
- E2E coverage exists for auth, members, events, check-in, excuses, and fines.

Current gaps for requested roadmap:
- No event templates for Party, Philanthropy, or Chapter Meeting.
- No task/checklist model, chair assignment model, reminders, status tracking, event readiness score, or post-event report.
- No communication module, recipient segments, SMS/email provider integration, read receipts, click tracking, or escalation logic.
- Navigation uses local React state, so current page state is not reflected in the URL.
- Mobile/responsive behavior is fragile because the app shell uses a fixed sidebar and fixed desktop grids.

## Web Interface Findings

### `fratos/fraternity-os-frontend.tsx`

`fratos/fraternity-os-frontend.tsx:26` - page navigation stored only in `useState`; tabs are not deep-linkable and browser back/refresh loses state.

`fratos/fraternity-os-frontend.tsx:29` - fixed `height: 100vh` with overflow hidden can clip content on mobile and does not account for safe areas.

`fratos/fraternity-os-frontend.tsx:37` - navigation buttons have no visible focus style.

`fratos/fraternity-os-frontend.tsx:59` - icon-only sign-out button relies on `title`; add `aria-label` and visible focus.

### `fratos/components/ui/card.tsx`

`fratos/components/ui/card.tsx:13` - clickable card is a `div` with `onClick`; use `button`/link semantics or add keyboard handling and role.

`fratos/components/ui/card.tsx:20` - clickable card has no focus-visible styling.

### `fratos/components/ui/btn.tsx`

`fratos/components/ui/btn.tsx:21` - base button has no visible focus style.

`fratos/components/ui/btn.tsx:32` - hover/active states are missing; interactive states should increase contrast.

### `fratos/components/ui/input.tsx`

`fratos/components/ui/input.tsx:12` - label is not associated with the input via `htmlFor`/`id`.

`fratos/components/ui/input.tsx:13` - inputs do not provide `name` or autocomplete defaults; forms should pass meaningful values.

`fratos/components/ui/input.tsx:13` - no visible focus style.

### `fratos/components/ui/modal.tsx`

`fratos/components/ui/modal.tsx:12` - modal overlay is a click handler on a `div`; Escape key and focus management are missing.

`fratos/components/ui/modal.tsx:12` - missing `role="dialog"`, `aria-modal`, and accessible title linkage.

`fratos/components/ui/modal.tsx:35` - scrollable modal should use `overscroll-behavior: contain`.

### `fratos/components/ui/toast.tsx`

`fratos/components/ui/toast.tsx:11` - toast lacks `aria-live="polite"` for async updates.

### `fratos/hooks/use-auth.tsx`

`fratos/hooks/use-auth.tsx:73` - loading copy uses `...`; use `Loading…`.

`fratos/hooks/use-auth.tsx:87` - email input lacks a label or `aria-label`.

`fratos/hooks/use-auth.tsx:87` - email input should include `name="email"`, `autoComplete="email"`, and `spellCheck={false}`.

`fratos/hooks/use-auth.tsx:92` - placeholder should end with ellipsis if used as example guidance.

`fratos/hooks/use-auth.tsx:95` - login error is not connected to the input and has no live region.

`fratos/hooks/use-auth.tsx:101` - loading copy uses `...`; use `Signing In…`.

### `fratos/views/dashboard.tsx`

`fratos/views/dashboard.tsx:28` - currency formatting is hardcoded; use `Intl.NumberFormat`.

`fratos/views/dashboard.tsx:37` - stats grid uses equal columns without responsive fallback.

`fratos/views/dashboard.tsx:50` - two-column grid has no mobile fallback.

`fratos/views/dashboard.tsx:62` - event date/time rendering is hardcoded; use `Intl.DateTimeFormat`.

`fratos/views/dashboard.tsx:102` - currency formatting is hardcoded; use `Intl.NumberFormat`.

### `fratos/views/events.tsx`

`fratos/views/events.tsx:38` - date filtering compares date-only strings with local `Date`; can shift by timezone and misclassify events.

`fratos/views/events.tsx:60` - back button has no visible focus style.

`fratos/views/events.tsx:67` - event date/time rendering is hardcoded; use `Intl.DateTimeFormat`.

`fratos/views/events.tsx:71` - currency formatting is hardcoded; use `Intl.NumberFormat`.

`fratos/views/events.tsx:107` - long check-in URL can overflow; add `break-word`/wrapping.

`fratos/views/events.tsx:127` - check-in time uses `toLocaleTimeString()` without explicit formatter/options.

`fratos/views/events.tsx:181` - loading copy uses `...`; use `Loading…`.

`fratos/views/events.tsx:187` - clickable event cards are `div`-based through `Card`; not keyboard accessible.

`fratos/views/events.tsx:190` - event date/time rendering is hardcoded; use `Intl.DateTimeFormat`.

## Recommended Remediation Order

1. Fix shared primitives first: `Btn`, `Input`, `Card`, `Modal`, `Toast`.
2. Move shell navigation into URL state so new VP/Secretary modules can deep-link.
3. Add responsive shell behavior before adding feature-dense modules.
4. Add typed formatting helpers for dates, times, currency, and percentages.
5. Introduce VP and Secretary modules behind feature routes with mocked data first, then wire backend APIs.

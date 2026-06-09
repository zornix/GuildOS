# FrontendConventions

Reusable frontend architecture conventions for GreekOS. The goal is to make
visual redesigns, theme experiments, and feature iteration possible without
rewriting business logic.

## North Star

The frontend should be boring and predictable:

- Pages compose modules. They should not own detailed visual structure.
- Modules own product workflows. They should not define generic UI styling.
- UI primitives own reusable appearance and interaction states.
- API clients fetch backend data. Adapters convert backend DTOs into stable
  frontend-facing types.
- Mock data can power the same module components used by real API data.
- Theme values live in one place and are consumed by primitives, shells, and
  module components.

## Current State To Preserve

These parts are useful and should be evolved rather than discarded:

- `LocalDev/fratos/app/page.tsx` is thin and only renders the app root.
- `LocalDev/fratos/components/ui` already contains basic primitives:
  `Btn`, `Card`, `Badge`, `Avatar`, `Input`, `Modal`, `Toast`, and `Icon`.
- `LocalDev/fratos/lib/api-client.ts` centralizes request behavior and read
  retries.
- `LocalDev/fratos/lib/types.ts` gives the frontend a typed vocabulary.
- `LocalDev/fratos/e2e` covers important role flows for events, fines, auth,
  excuses, check-in, and members.

## Problems This Convention Solves

The latest audit found these recurring issues:

- `fraternity-os-frontend.tsx` mixes navigation config, officer gating, layout,
  page switching, and inline visual styles.
- `views/events.tsx` owns event list, detail, attendance, polling, modals,
  mutations, and row styling in one file.
- `views/dashboard.tsx`, `views/standing.tsx`, `views/members.tsx`,
  `views/events.tsx`, and `views/fines.tsx` repeat card, row, stat, tab,
  loading, and empty-state styles.
- `hooks/use-auth.tsx` mixes auth session state with login and set-password UI.
- `lib/theme.ts` only centralizes colors. Spacing, radii, typography, shadows,
  layout widths, and component sizes are still hardcoded.
- Backend responses are cast as frontend types with `return data as T`, without
  validation or adapters.
- There is no runtime mock data layer for frontend iteration.
- Treasury backend endpoints exist, but the app has no Treasury frontend module,
  API wrapper, adapters, mocks, or UI contracts.
- `LocalDev/fratos` and `Prod/fratos` duplicate frontend files and can drift.

## Target Folder Structure

Use this structure for the app frontend. If `LocalDev/fratos` and `Prod/fratos`
remain separate, keep this structure identical in both until they are
consolidated.

```text
fratos/
  app/
    layout.tsx
    page.tsx
    providers.tsx
  components/
    ui/
      button.tsx
      card.tsx
      badge.tsx
      input.tsx
      textarea.tsx
      modal.tsx
      toast.tsx
      empty-state.tsx
      loading-state.tsx
      segmented-control.tsx
      data-table.tsx
      stat-card.tsx
    layout/
      app-shell.tsx
      sidebar.tsx
      topbar.tsx
      page-header.tsx
    modules/
      auth/
      dashboard/
      events/
      treasury/
      tasks/
      roster/
      standing/
      fines/
  config/
    navigation.ts
    theme/
      tokens.ts
      variants.ts
  hooks/
  lib/
    api/
      client.ts
      auth.ts
      events.ts
      treasury.ts
      members.ts
      standing.ts
      fines.ts
    adapters/
      auth.ts
      events.ts
      treasury.ts
      members.ts
      standing.ts
      fines.ts
    contracts/
      api.ts
      view-models.ts
    formatters/
      date.ts
      money.ts
      status.ts
  mocks/
    data/
      auth.ts
      events.ts
      treasury.ts
      members.ts
      tasks.ts
    mock-api.ts
```

## Layering Rules

### Pages

Pages should be thin. They may:

- Load route params.
- Select a module component.
- Wrap providers or layout shells.

Pages should not:

- Define repeated card/list/table markup.
- Contain color, spacing, shadow, or typography decisions.
- Call `fetch` or `api.*` directly unless the page is explicitly a data route.

### Layout Components

Layout components live in `components/layout`.

They own:

- App shell frame.
- Sidebar and topbar.
- Page title area.
- Navigation rendering.
- Shell density and layout variants.

They should read navigation from `config/navigation.ts`. Role/capability gating
belongs in navigation config or small guard helpers, not scattered across page
markup.

### Module Components

Module components live in `components/modules/<module>`.

They own product workflow UI:

- Dashboard widgets.
- Event list/detail/attendance.
- Treasury payment review, invoices, balances, statements, expenses.
- Roster rows and role actions.
- Standing scorecards and member standing list.
- Task boards, task lists, and assignment views.

They should compose UI primitives and receive frontend-facing data shapes. A
module component should not know whether its data came from the backend, a mock
adapter, or a story/demo fixture.

### UI Primitives

UI primitives live in `components/ui`.

They own generic appearance and behavior:

- `Button`
- `Card`
- `Badge`
- `Input`
- `Textarea`
- `Modal`
- `Toast`
- `EmptyState`
- `LoadingState`
- `ErrorState`
- `SegmentedControl`
- `StatCard`
- `DataTable`
- `ListRow`
- `ActionBar`

Primitives should accept variants and slots, not product-specific names. For
example, `Badge` can support `tone="warning"`, but should not know about
`excuse_status`.

## Data Contracts

Use three separate type layers:

1. Backend DTOs: the exact wire shape from FastAPI.
2. Frontend contracts: stable shapes the UI consumes.
3. Form/input payloads: mutation input models.

Adapters should be the only place that transforms DTOs into frontend contracts.

Example:

```ts
// lib/adapters/treasury.ts
export function adaptPaymentSubmission(dto: TreasuryPaymentSubmissionDto): PaymentSubmission {
  return {
    id: dto.id,
    memberName: dto.member_name,
    amountCents: dto.claimed_amount_cents,
    amountDisplay: formatMoney(dto.claimed_amount_cents),
    status: adaptTreasuryStatus(dto.status),
    submittedAt: dto.submitted_at,
  };
}
```

Do not let component code repeatedly solve backend details such as:

- cents versus dollars
- snake_case versus camelCase
- nullable nested objects
- backend status strings
- display labels
- date/time formatting

## API Client Conventions

Split `lib/api-client.ts` into:

- `lib/api/client.ts`: shared request, auth headers, retry behavior.
- `lib/api/events.ts`: events and attendance endpoints.
- `lib/api/treasury.ts`: invoices, payment submissions, receipts, balances,
  reports, expenses, adjustments, refunds, rebuild.
- `lib/api/members.ts`: roster/member endpoints.
- `lib/api/fines.ts`: fines endpoints.
- `lib/api/standing.ts`: standing endpoints.

Each resource client should return frontend contracts after adapter conversion
or clearly named DTO methods if the adapter is applied by a hook.

Avoid generic `return data as T` at module boundaries. If runtime validation is
too heavy for now, keep all casts inside API/adapters and never inside UI
components.

## Mock Data Conventions

Every module that is being redesigned should run with mock data.

Add:

- `mocks/data/<module>.ts` for realistic sample records.
- `mocks/mock-api.ts` that implements the same interface as real resource
  clients.
- an env switch such as `NEXT_PUBLIC_USE_MOCK_API=true`.

Mock data should include:

- empty states
- loading states
- error states
- long names and overflowing text
- officer and member role variants
- edge cases such as no upcoming events, delinquent members, failed payment
  proof, expired check-in links, and no assigned tasks

This lets designers and engineers iterate UI without depending on backend
readiness or seeded database state.

## Theme And Token Conventions

Centralize design tokens in `config/theme/tokens.ts` and expose them to CSS
variables or Tailwind theme values.

Use semantic names rather than palette names in components.

Recommended tokens:

```ts
export const tokens = {
  color: {
    bg: "var(--color-bg)",
    surface: "var(--color-surface)",
    surfaceHover: "var(--color-surface-hover)",
    border: "var(--color-border)",
    borderStrong: "var(--color-border-strong)",
    text: "var(--color-text)",
    textMuted: "var(--color-text-muted)",
    accent: "var(--color-accent)",
    accentMuted: "var(--color-accent-muted)",
    success: "var(--color-success)",
    warning: "var(--color-warning)",
    danger: "var(--color-danger)",
    info: "var(--color-info)",
    overlay: "var(--color-overlay)",
    focusRing: "var(--color-focus-ring)",
  },
  space: {
    1: "4px",
    2: "8px",
    3: "12px",
    4: "16px",
    5: "20px",
    6: "24px",
    8: "32px",
    10: "40px",
  },
  radius: {
    sm: "6px",
    md: "8px",
    lg: "12px",
    xl: "16px",
    pill: "999px",
  },
  font: {
    sans: "var(--font-sans)",
    mono: "var(--font-mono)",
  },
  layout: {
    sidebarWidth: "220px",
    contentMax: "900px",
    modalMax: "440px",
    authCardMax: "380px",
    shellPadding: "24px",
    statIconSize: "42px",
  },
  shadow: {
    floating: "0 8px 24px rgba(0,0,0,0.3)",
  },
};
```

When a value appears in multiple files, it should become a token or component
variant. Common current examples include:

- `padding: 40`
- `borderRadius: 8`
- `borderRadius: 12`
- `fontSize: 11`
- `fontSize: 13`
- `fontSize: 22`
- `gap: 6`, `gap: 8`, `gap: 10`, `gap: 16`
- `background: T.bg`
- `background: T.sf`
- `width: 42`, `height: 42`
- `maxWidth: 900`
- `width: 220`

## Component Extraction Priorities

Extract these first:

1. `StatCard`: duplicated by Dashboard and Standing.
2. `SegmentedControl`: duplicated by Events and Fines.
3. `ListRow`: duplicated by Members, Standing, Events attendance, Dashboard
   panels, and Fines.
4. `EmptyState` and `LoadingState`: repeated across every view.
5. `PageHeader`: currently embedded in the app shell.
6. `AppShell`, `Sidebar`, and `Topbar`: currently embedded in
   `fraternity-os-frontend.tsx`.
7. `DataTable`: needed for Treasury, Roster, Standing, payment review queues,
   and admin/officer screens.
8. `MoneyText`: needed for fines and Treasury cents/dollars display.

## GreekOS Module Guidance

### Dashboard

Dashboard should be a composition surface. It should not directly know the
shape of events, fines, or excuses beyond the widget view models it receives.

Target components:

- `DashboardPage`
- `DashboardStats`
- `UpcomingEventsWidget`
- `PendingExcusesWidget`
- `MyFinesWidget`

### Events

Events is currently the highest-risk redesign area because one file owns too
many workflows.

Target components:

- `EventsPage`
- `EventTabs`
- `EventList`
- `EventRow`
- `EventDetail`
- `EventDetailHeader`
- `AttendanceRoster`
- `AttendanceRow`
- `ManualAttendanceModal`
- `CheckInCodeCard`
- `CreateEventForm`
- `CheckInForm`
- `ExcuseForm`

Target hooks:

- `useEvents`
- `useEventAttendance`
- `useActiveCheckinLink`
- `useEventFocusRefresh`

### Treasury

Treasury has backend routes but no app frontend module yet. Build Treasury with
contracts and mocks before trying to polish visuals.

Target components:

- `TreasuryDashboard`
- `TreasuryStats`
- `PaymentReviewQueue`
- `PaymentSubmissionRow`
- `InvoiceList`
- `InvoiceCreateForm`
- `BulkInvoiceForm`
- `MemberStatement`
- `ChapterBalanceCard`
- `ExpenseList`
- `ExpenseCreateForm`
- `TreasuryReportExport`

Target API coverage:

- `GET /api/treasury/dashboard`
- `GET /api/treasury/balance`
- `GET /api/treasury/payments/submissions`
- `POST /api/treasury/payments/submissions`
- `POST /api/treasury/payments/submissions/{id}/verify`
- `POST /api/treasury/payments/submissions/{id}/reject`
- `GET /api/treasury/members/{member_id}/statement`
- `POST /api/treasury/invoices`
- `POST /api/treasury/invoices/bulk`
- `POST /api/treasury/invoices/{id}/cancel`
- `POST /api/treasury/expenses`
- `POST /api/treasury/expenses/{id}/invalidate`
- `GET /api/treasury/report`

All Treasury amounts should move through `formatMoney(cents)` and never be
formatted inline.

### Tasks

Tasks currently appears in the landing page copy and product positioning, but
not as an app module. Start with frontend contracts and mocks:

- `Task`
- `TaskList`
- `TaskBoard`
- `TaskAssignee`
- `TaskStatus`
- `TaskPriority`

This lets task UI be designed before the backend is ready.

### Roster

Treat `MembersPage` as the Roster module.

Target components:

- `RosterPage`
- `MemberList`
- `MemberRow`
- `RoleBadge`
- `RoleActionButton`
- `InviteMembersForm`

### Standing

Standing should reuse `StatCard`, `DataTable` or `ListRow`, `MoneyText`, and
`StandingBadge`.

Do not hardcode standing rules inside render markup. Keep rules and labels in a
module helper or adapter.

### Admin And Officer Views

Officer-only visibility should be configured centrally:

```ts
export const navigation = [
  { id: "dashboard", label: "Dashboard", icon: "home" },
  { id: "events", label: "Events", icon: "calendar" },
  { id: "treasury", label: "Treasury", icon: "wallet", capability: "treasury:read" },
  { id: "tasks", label: "Tasks", icon: "check-square" },
  { id: "roster", label: "Roster", icon: "users" },
  { id: "standing", label: "Standing", icon: "shield", role: "officer" },
];
```

Components should ask for capability metadata rather than repeating
`user.role === "officer"` checks throughout JSX.

## Landing Page Guidance

The landing app is separate from `fratos`, but should share brand tokens where
possible.

Current issue: `greekos-landing/src/app/page.tsx` is a single page with section
data, nav, hero, mockup, features, pricing, CTA, and footer.

Refactor into:

- `components/landing/Header`
- `Hero`
- `ProductMockup`
- `FeatureGrid`
- `AiLayer`
- `Workflow`
- `Pricing`
- `Cta`
- `Footer`
- `config/landing-content.ts`

Keep marketing-specific visuals out of app UI primitives, but share color and
font tokens if the brand should feel consistent.

## Definition Of Done For Frontend Rework Issues

Every frontend rework issue should include:

- Exact files currently causing redesign friction.
- New target folder or component names.
- Whether the issue is UI-only, data-contract work, or module-boundary work.
- Mock data requirements.
- Acceptance checks that do not depend on visual taste alone.
- Test scope: unit, e2e, or manual responsive smoke test.

Use these issue categories:

- `frontend-architecture`
- `design-system`
- `module-boundary`
- `api-contracts`
- `mock-data`
- `treasury`
- `events`
- `dashboard`
- `roster`
- `tasks`

## Suggested Refactor Order

1. Establish tokens and shared primitives.
2. Extract layout shell and navigation config.
3. Extract common state components: loading, empty, error, segmented controls,
   stats, list rows.
4. Split Events into smaller module components.
5. Split auth UI from auth session state.
6. Add API adapters and frontend contracts.
7. Add mock API mode.
8. Add Treasury frontend contracts, mocks, and first module screens.
9. Consolidate `LocalDev/fratos` and `Prod/fratos` or create one shared source.


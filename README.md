# GuildOS

Organization management system for fraternity chapters: events, attendance,
dues/fines treasury, standing, tasks, announcements, roster, and RBAC.

Active development happens in [`LocalDev/`](LocalDev/) (FastAPI + Vite/React
**greekos** + PostgreSQL) — see `LocalDev/CLAUDE.md` for the project guide.
`LocalDev/greekos` is the only tracked frontend. The old Next.js `LocalDev/fratos`
app was archived (2026-09-15, tag `last-with-localdev-fratos`).

The FraternityOS Vercel project roots at [`Prod/`](Prod/): API in `Prod/api`,
hosted UI in `Prod/fratos` (clone of greekos). See `Prod/vercel.json`.

**Temporary (about a week, 2026-09-08):** production Vercel still uses the
**demo** Supabase database. Do not treat that data as a real chapter. A
separate prod project comes after this window.

**Launch the demo locally:** [`docs/launch-demo.md`](docs/launch-demo.md)
(`cd LocalDev && npm run dev`, then sign in as `jake@tke.org` /
`demo-officer-pw`).

Domain language lives in [`CONTEXT.md`](CONTEXT.md); architectural decisions in
[`docs/adr/`](docs/adr/).

## Where the app stands

_2026-09-08._

The product is a working **demo chapter**, not a shippable multi-tenant
release. Officers and members can run the real workflows in greekos against
the demo database: login, roster, events and jobs, security shifts and swaps,
initiatives, attendance and excuses, treasury (dues/fines as invoices),
standing, tasks, and announcements. Permission keys (not
`user.role === "officer"`) gate the UI.

**What is real**

- FastAPI domains in `LocalDev/api` are RPC-backed and tenant-guarded. One
  Postgres client (`api/platform/`). Production boot refuses a weak
  `JWT_SECRET`, missing `DATABASE_URL`, auth bypass, or localhost CORS.
- `LocalDev/greekos` is the product UI (Vite). Events V1 screens talk to the
  API — jobs, calendar chips, security/swaps, announcements. Demo mock
  fallback, Bylaws/Outbox tabs, and the view-as switcher are gone. Vercel
  login is email + password (`dev-login` is 404 on any deploy).
- Hosted site is `Prod/`: `Prod/fratos` is a clone of greekos, `Prod/api` is
  the LocalDev API. Both environments use the **demo** Supabase project until
  a real prod database exists.

**What is not**

- No chapter signup. A real chapter is still hand SQL; seed is demo-only and
  unsafe to re-run on a used DB (`imp-reseed-idempotency.md`).
- No prod database and no `migrate:prod` (`PROD_PROJECT_REFS` is empty).
  Schema and data on the hosted site are the demo chapter.
- No email, so no password reset. Members without a hash still get a grace
  login and must set a password. Invites do not notify anyone.
- SMS is not a launch-ready channel: delivery defaults to `dry_run`, Twilio
  needs A2P 10DLC, and many outbox producers only move when cron drain runs.
- Phone check-in and `members.phone` storage are still inconsistent (digit
  length vs E.164). Do not treat check-in as proven in production.
- Command console is still a nav item (`nl_controller:execute`); it is not a
  working product surface.

**Do not** run `npm run seed` against a database that already has chapter
data. A 2026-07-17 reseed wiped operational rows on demo and had to be
restored by hand.

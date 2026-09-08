# Testing greekos online from several devices at once

Research note for [#53](https://github.com/zornix/GuildOS/issues/53) (map [#41](https://github.com/zornix/GuildOS/issues/41)).
Question: how do we exercise a preview deployment of `LocalDev/greekos` from
several devices simultaneously, and should a smoke suite run in CI?

Everything below assumes the map's ruling: **multi-device testing happens on a
preview deployment against the demo database, never prod.**

---

## 1. What the repo actually supports today

Read this first — three of these facts decide the answer, and none of them are
about test tooling.

| Fact | Where | Consequence |
|---|---|---|
| `vercel.json` builds `api/index.py` and `fratos/` only. greekos is not deployed anywhere. | `LocalDev/vercel.json` | **There is no greekos preview URL to test yet.** Every option in this note is blocked on shipping one. |
| greekos has no login screen. `src/api.ts` calls `POST /api/auth/dev-login` as `jake@tke.org` and caches the token in `localStorage`. | `LocalDev/greekos/src/api.ts:1-22`, `greekos/README.md` | Every browser is the same officer. No second identity, so "several devices at once" is currently one user in several windows. |
| `dev-login` returns 404 on any deployed surface — `if settings.is_deployed: raise HTTPException(404)`, and `is_deployed` covers **preview as well as production**. | `LocalDev/api/auth/api/auth.py:224-232`, `LocalDev/api/config.py:33-36` | greekos as written **cannot log in on a preview deploy at all**, with or without `DEV_AUTH_BYPASS`. It needs the real `POST /api/auth/login`. |

Supporting details:

- **Real login works and the demo data is ready for it.** `POST /api/auth/login`
  takes email + password. Seeded officers share the password
  `demo-officer-pw` (`LocalDev/scripts/seed.py:31-34`); seeded members have no
  `password_hash`, so login succeeds on email alone and answers
  `password_setup_required: true` (`api/auth/api/auth.py:164-222`). The demo
  chapter seeds one officer and seven members
  (`scripts/seed.py:45-52`) — enough distinct identities for a multi-device
  session without inventing anything.
- **Passwordless members are a reason to keep the preview URL protected.** On a
  public preview against the demo DB, anyone who guesses `ryan@tke.org` is
  logged in as Ryan. Fine for a demo chapter, not something to leave open.
- **CORS is a single fixed origin in a deploy**: `_allowed_origins =
  [settings.FRONTEND_URL]` (`LocalDev/api/index.py:142-153`). Preview URLs are
  unique per deployment, so greekos served from a *separate* Vercel project
  would be cross-origin and blocked on every preview. Served from the *same*
  project (a `vercel.json` route, next to fratos) it is same-origin and CORS
  never enters the picture. **Same project is the cheap path.**
- **The boot guard applies to previews.** `production_config_violations` runs
  whenever `is_deployed` (production *or* preview) and hard-fails the build on a
  weak `JWT_SECRET`, missing `DATABASE_URL`, truthy `DEV_AUTH_BYPASS`, short
  `CRON_SECRET`, or a localhost `FRONTEND_URL` (`LocalDev/api/index.py:26-90`).
  A preview needs a complete env config, not a partial one.
  *Doc drift:* `docs/ops-runbook.md:179-183` still says "Preview deployments are
  deliberately not guarded." That is stale — fix it when someone is next in
  that file.
- **Existing e2e**: `LocalDev/fratos` has Playwright 1.59.1 with six specs
  under `fratos/e2e/`, one `chromium` project, `baseURL:
  http://localhost:3000`, and a `webServer` block that boots the app locally
  (`fratos/playwright.config.ts`). CI deliberately skips it — the workflow
  comment says "Playwright e2e is deliberately excluded — it needs a live API +
  DB stack" (`.github/workflows/ci.yml`). The greekos CI job runs `tsc --noEmit`
  and `vite build` only.
- **The repo is private**, so Actions minutes are metered (see §4).

---

## 2. The options

### A. Playwright against the preview URL (emulation + multiple contexts)

Point the existing Playwright install at a deployed URL instead of a local
webServer: set `baseURL` to the preview URL and drop `webServer`. Both are
plain `use` options — `baseURL`, `extraHTTPHeaders`, and `storageState` all
live in `use: {}` ([Playwright: test use
options](https://playwright.dev/docs/test-use-options)).

Two different things get called "many devices at once", and Playwright does
both:

- **A device matrix** — one `projects` entry per device, spreading
  `...devices['iPhone 15']` etc. Playwright "comes with a registry of device
  parameters using `playwright.devices` for selected desktop, tablet and mobile
  devices" and emulates "`userAgent`, `screenSize`, `viewport` and if it
  `hasTouch` enabled" ([Playwright:
  emulation](https://playwright.dev/docs/emulation)). One command runs every
  device.
- **Several users in one scenario** — "Playwright can create multiple browser
  contexts within a single scenario. This is useful when you want to test for
  multi-user functionality, like a chat" ([Playwright: browser
  contexts](https://playwright.dev/docs/browser-contexts)). This is the one that
  answers the real question: officer marks attendance in one context, member
  sees it in another, same run, same preview, same demo chapter.

Limits. Playwright never states an "emulation is not a real device" caveat
outright; the honest citation is two steps. First, emulation only claims to
"simulate the browser behavior such as `userAgent`, `screenSize`, `viewport`
and if it `hasTouch` enabled", and "pre-configured devices assume a specific
platform" ([emulation](https://playwright.dev/docs/emulation)). Second — the
one that matters for a member-facing phone UI — `devices['iPhone 15']` does
**not** run Mobile Safari: "Playwright doesn't work with the branded version of
Safari since it relies on patches. Instead, you can test using the most recent
WebKit build", and "for the closest-to-Safari experience you should run WebKit
on mac" ([browsers](https://playwright.dev/docs/browsers)).

So: an emulated iPhone catches layout and viewport regressions, not real
Mobile Safari quirks, real touch scrolling, on-screen keyboards, safe-area
insets, or a slow phone on campus wifi. Those need option B.

- **Cost**: $0 beyond what is installed.
- **Effort**: small — a `greekos/playwright.config.ts` and a login fixture.
  It is the only option that is *repeatable*.

### B. Real devices on the preview URL (hands-on)

Open the preview URL on your own phone, a second phone, and a laptop. Nothing
to install, nothing to tunnel — the preview is reachable from anywhere, so the
devices do not need to share a network, and there is no ngrok/cloudflared step.

The one real obstacle is access control: preview deployments are protected by
default and each device has to get past that. That is a Vercel setting, not a
tooling problem — §3.1 has the three ways in.

For *local* work the LAN path already exists: `greekos`'s dev script is
`vite --port=3000 --host=0.0.0.0` (`greekos/package.json`), so any phone on the
same Wi-Fi can already hit `http://<laptop-ip>:3000` today. That covers "does
this look right on a real phone" without any deploy at all — but it is the local
DB story, not the preview story, and it has no HTTPS.

- **Cost**: $0.
- **Effort**: near zero once a preview URL exists.
- **Weakness**: not repeatable, not a regression net, and it needs a human each
  time.

### C. Device-cloud services (BrowserStack / LambdaTest / Sauce Labs)

Rented real devices, driven either interactively or from Playwright.

- **Cost**: from $12.50/month; see §5 for the table.
- **Effort**: account setup, then a driver/endpoint change in the config.
- **When it earns its keep**: a real-iOS-Safari bug you cannot reproduce, or a
  device you do not own. Not for "check the roster renders on a phone" — that
  is your own phone (option B) for free.

### D. A shared test chapter on the demo DB

Not a rival to the others — it is the *data* half of whichever one you pick.
The demo seed already provides it: one chapter, one officer, seven members
(`scripts/seed.py:45-52`), reseedable with `npm run seed`, and `db_guard.py`
refuses anything that is not the demo project ref or a local host
(`scripts/db_guard.py:89-101`). Reseeding is destructive — it deletes the
chapter and rebuilds it (`scripts/seed.py:198`) — so it is a between-sessions
command, never a mid-session one.

Worth knowing about concurrency: if a Playwright suite and a human are both
poking the same seeded chapter at the same time, they will collide (the same
event checked in twice, a fine created under someone's feet). Cheap fix when it
starts to hurt: have the smoke suite create its own event with a run-scoped
name rather than mutating the seeded fixtures. Not worth building until it
actually bites.

- **Cost**: $0.
- **Effort**: none — it exists.

---

## 3. Fitting Vercel previews

### 3.1 Preview URLs are not public by default

This is the fact that changes the shape of the answer. Vercel Authentication
with Standard Protection is on by default for new projects and "protects all
deployments **except** production domains. Available on all plans"
([Vercel: deployment protection](https://vercel.com/docs/deployment-protection)).
With it on, "users attempting to access the deployment will encounter a Vercel
login redirect", and access is limited to logged-in team members, people given a
**Shareable Link**, and tools sending the **bypass header**
([Vercel authentication](https://vercel.com/docs/deployment-protection/methods-to-protect-deployments/vercel-authentication)).
The auth cookie "is restricted to one URL and isn't transferable, even between
URLs pointing to the same deployment" — so logging in on one preview does not
carry to the next one.

Given the demo DB lets a passwordless seeded member log in on email alone
(§1), **leave protection on.** Then there are exactly three ways in:

| Who | How |
|---|---|
| Your own phones/laptop | Log in to Vercel once per preview URL, or use a Shareable Link ("Anyone with the link… bypasses deployment protection", [sharable links](https://vercel.com/docs/deployment-protection/methods-to-bypass-deployment-protection/sharable-links)). Hobby is documented as one shareable link per account — and the Hobby/Pro comparison table contradicts that page by listing the feature as Pro-only, so check the dashboard. |
| A pilot chapter member you want to look at it | Same Shareable Link. No Vercel account needed to view. |
| Playwright | Protection Bypass for Automation, **all plans** ([automated agent access](https://vercel.com/docs/deployment-protection/automated-agent-access)). |

### 3.2 The bypass, exactly

Vercel sets `VERCEL_AUTOMATION_BYPASS_SECRET` once you generate the secret in
the project's Deployment Protection settings, and their docs give the Playwright
config verbatim:

```ts
// playwright.config.ts — from Vercel's docs
export default defineConfig({
  use: {
    baseURL: process.env.VERCEL_PREVIEW_URL,
    extraHTTPHeaders: {
      'x-vercel-protection-bypass': process.env.VERCEL_AUTOMATION_BYPASS_SECRET,
      'x-vercel-set-bypass-cookie': 'true',
    },
  },
});
```

The cookie header is not optional: "headless browser tools like Playwright and
Cypress send the bypass header on the initial page load, but subsequent
in-browser navigations (clicking links, form submissions) don't include custom
HTTP headers"
([automated agent access](https://vercel.com/docs/deployment-protection/automated-agent-access)).
Both names also work as query parameters, which is the phone escape hatch —
`?x-vercel-protection-bypass=<secret>&x-vercel-set-bypass-cookie=true` — with
Vercel's own warning attached: the secret then "appears in the URL. URLs are
often logged by proxies, CDNs, and server access logs."

### 3.3 Getting the URL into CI

Vercel's own example triggers on GitHub's `deployment_status` event and reads
`github.event.deployment_status.target_url`, gated on `state == 'success'`
([automated agent access](https://vercel.com/docs/deployment-protection/automated-agent-access)).
Their KB guide for the same question instead uses `repository_dispatch` on
`vercel.deployment.success` with `github.event.client_payload.url`
([Vercel KB: e2e tests after a preview deployment](https://vercel.com/kb/guide/how-can-i-run-end-to-end-tests-after-my-vercel-preview-deployment)).
Either works; `deployment_status` is less wiring.

Two gotchas, both from GitHub's own reference: the workflow file must exist on
the **default branch** for `deployment_status` to fire at all, and a status of
`inactive` triggers nothing
([events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#deployment_status)).
And note `VERCEL_URL` is *not* the answer — it lives inside the deployment, not
in your CI job, and carries the warning "this variable cannot be used in
conjunction with Standard Deployment Protection"
([system environment variables](https://vercel.com/docs/environment-variables/system-environment-variables)).

*Unverified:* Vercel's example says `target_url`; GitHub also defines
`environment_url` and semantically that is the one that should hold the site
URL. Log the payload once on the first run and use whichever actually carries
the preview URL.

### 3.4 Where greekos should be deployed

Vercel's documented answer for two apps in one repo is **two projects**, one per
root directory ([monorepos](https://vercel.com/docs/monorepos)); the `builds`
array this repo uses is legacy and explicitly discouraged
([vercel.json](https://vercel.com/docs/project-configuration/vercel-json#builds)).

But two projects means two origins, and §1 says a deploy trusts exactly one
origin (`FRONTEND_URL`) while preview URLs are unique per deployment. Following
Vercel's recommendation therefore costs a CORS rework and a per-deploy origin
problem.

Cheapest thing that works, given this repo is already on `builds`: **add one
more entry for `greekos` and a route**, so greekos, fratos and the API ship in
one deployment and one origin. Playwright's bypass cookie, the demo login and
CORS then all work with no further thought. (`@vercel/static-build` off
`greekos/package.json` with the Vite `dist` output — the exact incantation needs
verifying, it is the one part of this note nobody has run.) The alternative,
if the `builds` array has to go, is a `rewrites` proxy from the main project to
a second greekos project — same-origin to the browser, one extra hop
([rewrites](https://vercel.com/docs/project-configuration/vercel-json#rewrites)).

Note greekos is a SPA and will need the catch-all rewrite
(`{"source": "/(.*)", "destination": "/index.html"}`) or deep links 404.

### 3.5 Plan

Hobby is free but "restricted to non-commercial personal use only… any
Deployment that is used for the purpose of financial gain of anyone involved in
any part of the production of the project"
([fair use](https://vercel.com/docs/limits/fair-use-guidelines#commercial-usage)).
Pro is $20/month including one seat ([Pro plan](https://vercel.com/docs/plans/pro-plan)).
Pilot chapters are the moment to check which side of that line GuildOS is on.
It is a licensing question, not a testing one, but it is the largest recurring
cost anything in this note implies.

---

## 4. Should a smoke suite run in CI?

**First, the free one nobody is running.** greekos has ten `node:test` files
(`src/**/*.test.ts`, run by `npm test` via tsx) and the greekos CI job does not
run them — it runs `tsc --noEmit` and `vite build` only, under a comment that
says "greekos has no eslint config and **no unit tests yet**"
(`.github/workflows/ci.yml`). That comment is now stale. No browser, no DB, no
network, a few seconds.
**Add `npm test` to the greekos job.** That is the highest-value CI change in
this note and it is one line.

**Then, a browser smoke suite: yes, but small and not on every push.** The
argument the CI file makes against Playwright — "it needs a live API + DB
stack" — stops applying the moment there is a preview deployment: the preview
*is* the live stack. What changes is the trigger.

- **Wrong trigger**: `on: push`. A preview build has to finish first, so a push
  trigger races the deploy.
- **Right trigger**: GitHub's `deployment_status` event, gated on
  `github.event.deployment_status.state == 'success'`, taking the URL from the
  payload — see §3.3 for the exact wiring and its two gotchas.

Cost: the repo is **private**, so minutes are billed against the plan's
allowance — 2,000 minutes/month on GitHub Free, 3,000 on Pro, and $0.006 per
extra Linux 2-core minute
([GitHub Actions billing](https://docs.github.com/en/billing/managing-billing-for-your-products/about-billing-for-github-actions)).
A smoke run is roughly 2-4 minutes including the browser download, so even a
generous 100 preview deploys a month lands inside the free allowance.

Keep it genuinely a smoke suite: log in, land on the member view, one write
that round-trips (check in to an event or claim a job), one officer read. Three
or four specs. The instant it grows into a regression suite it becomes the
flaky job everyone reruns, and the CI file's original instinct wins.

Set `retries: 2` and `workers: 1` in CI, as `fratos/playwright.config.ts`
already does.

---

## 5. Cost and effort summary

| Option | Money | Effort to first use | Repeatable? | Catches real-device bugs? |
|---|---|---|---|---|
| A. Playwright vs preview | $0 (already installed) | Half a day: config + login fixture + bypass secret | Yes | No — emulated Chromium only |
| B. Your own devices | $0 | Minutes, once a preview URL exists | No | Yes |
| C. Device cloud | From $12.50/mo | An hour incl. signup | Yes | Yes |
| D. Shared demo chapter | $0 | None — seeded already | n/a | n/a |
| CI smoke job | $0 within the plan's allowance | An hour of workflow YAML | Yes | No |

Recurring costs that are real regardless of choice: Vercel Pro at $20/month
*if* the commercial-use line applies (§3.5), and Actions minutes past the plan
allowance (§4).

**Device-cloud figures** (all seen 2026-09-08, all annual billing unless
noted):

| Vendor | Cheapest useful tier | Price |
|---|---|---|
| BrowserStack Live | **Freelancer** — 1 user, **100 min/month** of real desktop + mobile | **$12.50/mo** ($19 month-to-month) |
| BrowserStack Live | Desktop & Mobile, unlimited minutes | $39/mo |
| BrowserStack Automate (Playwright) | Chrome, 1 parallel | $59/mo |
| Sauce Labs Live | 1 parallel, unlimited minutes | $39/mo ($49 monthly) |
| TestMu AI (ex-LambdaTest) | Real Device Plus Live | $39/mo; free tier exists but caps Live sessions at 2 min |
| Azure Playwright Workspaces | pay-per-minute cloud browsers | $0.01/Linux test-minute |

Sources: [BrowserStack pricing](https://www.browserstack.com/pricing),
[Sauce Labs pricing](https://saucelabs.com/pricing),
[TestMu AI pricing](https://www.testmuai.com/pricing/),
[Azure App Testing](https://azure.microsoft.com/en-us/pricing/details/app-testing/).
(BrowserStack also runs an [open-source program](https://www.browserstack.com/open-source)
granting 5 users and 5 parallels free, but it is application-gated and this
repo is private, so assume it does not apply.)

Two things worth knowing before ruling C out for good:

- **No tunnel is needed.** Local Testing / UnderPass exists for hosts that are
  not publicly routable ([BrowserStack local
  testing](https://www.browserstack.com/docs/live/local-testing)). A Vercel
  preview is publicly routable and merely returns a 401 challenge, so the
  bypass query param (§3.2) is enough for any of these tools — no tunnel, no
  header configuration.
- **The real floor is $12.50/month, not $40.** That is cheap enough that "we
  might need real iOS Safari someday" is not a reason to buy now — it is a
  reason not to worry about it.

Against all of it: the phones already in the room cost $0 and are *actual*
Mobile Safari, which is precisely the thing Playwright cannot give you. For a
closed pilot of two to five chapters, a device cloud rents hardware you own.

---

## 6. Recommendation

**Your own devices on a protected preview URL, plus a three-spec Playwright
smoke suite triggered by `deployment_status`. Buy nothing.**

That is options B + A + D together, which is the honest answer: B is how a
human sees whether it works on a phone, A is how it stays working, D is the
data both use. C (a device cloud) buys nothing you cannot already do with the
phones in the room.

But the ticket asks a testing question whose answer is mostly not about
testing. In order:

1. **Add `npm test` to the greekos CI job.** Ten test files exist and CI does
   not run them. One line, free, do it today — independent of everything else
   here.
2. **Deploy greekos.** One more `builds` entry plus a route in
   `LocalDev/vercel.json`, so it shares the deployment and the origin with the
   API (§3.4). Until this lands there is no preview URL and nothing else in
   this note is possible.
3. **Give greekos a login screen** against `POST /api/auth/login`. `dev-login`
   404s on every deploy including previews (§1), so this is not optional, and
   it is also the only way "several devices" means several *people* rather than
   one officer in several windows.
4. **Then test by hand**, first pass: officer on the laptop, two members on two
   phones, all on one Shareable Link, against the seeded demo chapter. Keep
   Vercel Authentication on — the demo DB lets a passwordless member log in on
   email alone.
5. **Then add the smoke suite**: `greekos/playwright.config.ts`, two projects
   (`Desktop Chrome` + one mobile device), Vercel's bypass header *and* cookie,
   three or four specs, on `deployment_status`. Two browser contexts in one
   spec cover the officer/member handoff.
6. **Revisit a device cloud only** when a real iOS-Safari bug appears that you
   cannot reproduce on a phone you own. BrowserStack Live Freelancer is
   $12.50/month for 100 minutes of real devices and needs no tunnel — a
   same-afternoon purchase if that day comes, which is exactly why it is not a
   setup step now.

Steps 2 and 3 are separate tickets — they are product work, not test work, and
they are what actually unblocks #41's "testable online from several devices at
once."

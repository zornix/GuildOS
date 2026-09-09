# GuildOS (repo root)

Active development happens in `LocalDev/` — see `LocalDev/CLAUDE.md` for the
project guide, commands, and conventions. `Prod/` is the Vercel root for
FraternityOS: FastAPI in `Prod/api` plus the hosted UI in `Prod/fratos` (a
clone of `LocalDev/greekos`). `local-dev-scripts/` holds the shared
dev-runner tooling. The old Next.js `Prod/fratos` and `greekos-landing/`
copies were archived (2026-09-08). The pre-switch Prod FastAPI
(`routes/`, `postgres_client.py`) is snapshotted in gitignored
`archive/Prod/`; `Prod/api` is the LocalDev API.

## Agent skills

### Issue tracker

GitHub issues on `zornix/GuildOS` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical names used as-is (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

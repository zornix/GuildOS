# GuildOS (repo root)

Active development happens in `LocalDev/` — see `LocalDev/CLAUDE.md` for the
project guide, commands, and conventions. `Prod/` is produced from `LocalDev/`
by `LocalDev/scripts/build_prod.sh`. The CI drift check is planned after the
next production sync; it does not run yet (see `LocalDev/docs/ops-runbook.md`). Running the sync, migrating
production and deploying each need the user's explicit go-ahead. Until the
sync runs, `Prod/` is a stale hand copy. `local-dev-scripts/` holds the shared
dev-runner tooling.

## Agent skills

### Issue tracker

GitHub issues on zornix/GuildOS via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical names used as-is (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

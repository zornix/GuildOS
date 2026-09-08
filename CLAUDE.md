# GuildOS (repo root)

Active development happens in `LocalDev/` — see `LocalDev/CLAUDE.md` for the
project guide, commands, and conventions. `Prod/` holds the sibling backend
copy; `local-dev-scripts/` holds the shared dev-runner tooling. The stale
`Prod/fratos` and `greekos-landing/` copies were moved out of the repo into a
gitignored `archive/` (2026-09-08).

## Agent skills

### Issue tracker

GitHub issues on `zornix/GuildOS` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical names used as-is (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

# GuildOS (repo root)

Active development happens in `LocalDev/` — see `LocalDev/CLAUDE.md` for the
project guide, commands, and conventions. Other top-level directories
(`Prod/`, `GreekV1/`, `greekos-landing/`, `local-dev/`) are sibling copies and
tooling for the same product.

## Agent skills

### Issue tracker

Issues are tracked as GitHub issues on `zornix/GuildOS` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles use their default names (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

# GuildOS Workspace

GuildOS is the local development and testing workspace for the FraternityOS attendance MVP.

## What This Folder Contains

- `api/` - FastAPI backend
- `fratos/` - Next.js frontend
- `migrations/` - SQL migrations
- `scripts/` - migration and seed helpers
- `deploy/` - local-dev and deploy scripts
- `docs/` - implementation audits and feature preparation docs
- `deferred/` - intentionally deferred work outside active MVP runtime

## Local Development

```bash
bash deploy/local-dev.sh
```

Seeded local data:

```bash
SEED_LOCAL_DB=1 bash deploy/local-dev.sh
```

Services:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8001`
- API docs: `http://localhost:8001/api/docs`

## Website and Feature Planning Docs

- Website audit: `docs/WEBSITE_AUDIT.md`
- VP + Secretary prep: `docs/VP_SECRETARY_FEATURE_PREP.md`
- Deployment details: `deploy/README.md`

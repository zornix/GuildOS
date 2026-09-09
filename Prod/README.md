# GuildOS / FraternityOS — Prod

Vercel root for the live FraternityOS site. Hosting watches this folder.

## Layout

```
Prod/
  vercel.json     # FastAPI (`api/index.py`) + Vite static build (`fratos/`)
  api/            # Same FastAPI app as LocalDev/api (demo DB for now)
  fratos/         # Clone of LocalDev/greekos (Vite + React)
  requirements.txt
  scripts/        # Operational scripts (health check, migrate, passwords)
```

- **Frontend** (`fratos/`): clone of `LocalDev/greekos`. Same-origin `/api`.
- **Backend** (`api/`): FastAPI, same app as `LocalDev/api`. Temporary:
  `DATABASE_URL` is the **demo** Supabase project, same as LocalDev.
- **Old API:** snapshot in gitignored `archive/Prod/` (see
  `docs/archive/Prod/README.md`).
- **Development** stays in `LocalDev/`. Copy greekos → `Prod/fratos` (and
  `LocalDev/api` → `Prod/api` when the backend needs to ship) when you want
  those changes on the hosted site.

See `LocalDev/CLAUDE.md` for the current API package layout. Do not add
tables on a real prod database from this folder.

## Health check

From `Prod/`:

```bash
python scripts/check_prod_status.py
python scripts/check_prod_status.py --base-url https://your-api.vercel.app
```

# GuildOS (FraternityOS) Documentation Hub

Welcome to the GuildOS documentation! This folder contains all the reference material needed for developers and AI agents to continue building and maintaining the project.

## 🧭 Navigation

*   [Architecture Overview](ARCHITECTURE.md) - System architecture, tech stack, and network flows.
*   [Treasury Architecture](TREASURY_ARCHITECTURE.md) - Deep dive into the ledger, invoicing, and balance engine.
*   [Services Design](services/README.md) - The canonical domain-package pattern for all backend services.
*   [Service Map](services/service-map.md) - How different domains (events, attendance, treasury) interact.
*   [Permissions & RBAC](services/permissions-matrix.md) - Role-Based Access Control matrix.
*   [MVP Operating Loop](services/mvp-operating-loop.md) - The weekly chapter cycle the software supports.
*   [Future Agents](services/future-agents.md) - Design constraints and hooks for future AI agents.

## 🚀 Quick Start for Developers & Agents

If you are a new developer or agent jumping into the codebase, here is how the repository is structured:

```mermaid
graph LR
    A[GuildOS Repo Root] --> B(LocalDev)
    B --> C[api/]
    B --> D[fratos/]
    B --> E[migrations/]
    B --> F[tests/]
    B --> G[docs/]
    
    style B fill:#2a2a45,stroke:#6c5ce7,stroke-width:2px
    style C fill:#1a1a2e,stroke:#444
    style D fill:#1a1a2e,stroke:#444
```

1.  **Backend (`api/`)**: A Python FastAPI application structured around domain-driven design (e.g., `api/treasury/`, `api/rbac/`).
2.  **Frontend (`fratos/`)**: A Next.js App Router application written in TypeScript and React.
3.  **Database (`migrations/`)**: Raw SQL migrations applied sequentially. We use PostgreSQL.
4.  **Testing (`tests/`)**: Pytest suite for the backend.

### Running Locally

You can spin up the entire stack locally using the scripts in `package.json`:

```bash
# Verify the sandbox (CI-equivalent check)
npm run verify

# Interactive dev mode (Supabase demo DB, FastAPI, and Next.js)
npm run dev

# Seed the Supabase demo DB (usually unnecessary — demo already has data)
npm run seed
```

## 🤖 Guide for Future Agents

When modifying this project, keep these core rules in mind:
1.  **Follow the Canonical Package Shape**: New backend features should live in their own domain folder `api/<domain>/` with `router.py`, `schemas.py`, `services/`, and `db/` (see [Services README](services/README.md)).
2.  **Integer Cents for Money**: Never use floats for currency. Use the `Money` primitive in `api/treasury/core/money.py`.
3.  **Do Not Modify Applied Migrations**: If you need to change the DB schema, create a *new* migration file. Never edit existing ones.
4.  **No Fabricated Business Logic**: If a behavior isn't implemented (like bylaws Q&A), return a `not_implemented` status explicitly.

---

> **Note to Agents:** Always read [ARCHITECTURE.md](ARCHITECTURE.md) and [Services README](services/README.md) before designing new features!

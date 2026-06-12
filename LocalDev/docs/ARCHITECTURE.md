# GuildOS System Architecture

Last updated: 2026-06-12

This document provides a high-level overview of the FraternityOS (GuildOS) architecture. For treasury-specific details, see [TREASURY_ARCHITECTURE.md](TREASURY_ARCHITECTURE.md).

---

## 1. System Overview

GuildOS is a monolithic Next.js and FastAPI application backed by PostgreSQL.

```mermaid
flowchart TD
    Client[Web Browser / Mobile Phone] -->|HTTP / REST| Frontend
    
    subgraph LocalDev [Deployment Boundary]
        Frontend[Next.js App Router\nPort: 3000]
        Backend[FastAPI Backend\nPort: 8001]
        DB[(PostgreSQL)]
        
        Frontend -->|API Calls\nNEXT_PUBLIC_API_BASE| Backend
        Backend -->|psycopg2\nDATABASE_URL| DB
    end

    style Frontend fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#fff
    style Backend fill:#0f172a,stroke:#10b981,stroke-width:2px,color:#fff
    style DB fill:#0f172a,stroke:#f59e0b,stroke-width:2px,color:#fff
```

### Layer Responsibilities

| Layer | Technology | Responsibilities |
|-------|------------|------------------|
| **Frontend** | Next.js 16, React 19, Tailwind/CSS | UI shell, dashboard views, short-link check-in forms. |
| **Backend** | Python, FastAPI | Business logic, authentication, CRUD operations, cron jobs. |
| **Database** | PostgreSQL | Persistence, atomic multi-row mutations via plpgsql RPCs, audit logging. |

---

## 2. Phone Check-In Architecture (No-Auth Flow)

One of the core features is the frictionless, zero-login phone check-in for members attending events.

```mermaid
sequenceDiagram
    participant Officer
    participant DB as PostgreSQL
    participant FastAPI
    participant MemberPhone as Member's Phone

    Officer->>FastAPI: POST /api/attendance/sessions (Open Check-In)
    FastAPI->>DB: Create short-lived checkin_link
    FastAPI-->>Officer: Returns 6-char short code (e.g., "ABCDEF")
    
    Note over Officer,MemberPhone: Officer verbally shares code or shows QR
    
    MemberPhone->>FastAPI: Opens /c/ABCDEF
    FastAPI-->>MemberPhone: Serves lightweight HTML page
    
    MemberPhone->>FastAPI: POST /api/attendance/checkin/ABCDEF/phone {phone: "5551234567"}
    FastAPI->>DB: 1. Validate Link TTL & Active Status
    FastAPI->>DB: 2. Lookup Member by Phone
    FastAPI->>DB: 3. Upsert Attendance Record
    FastAPI-->>MemberPhone: 200 OK (Checked In!)
```

---

## 3. Backend Module Structure

The backend is migrating towards a **Domain-Driven Design (DDD)** pattern, where each domain has its own independent router, services, and schemas.

```mermaid
graph TD
    API[api/index.py (App Factory)] --> Auth[api/auth/]
    API --> Treasury[api/treasury/]
    API --> RBAC[api/rbac/]
    API --> Operations[api/routes/operations.py]
    API --> Events[api/events/]
    
    subgraph Canonical Domain Shape [e.g. api/treasury/]
        Router[router.py]
        Services[services/]
        Schemas[schemas.py]
        Core[core/]
        DB_Helpers[db/]
    end
    
    Treasury --> Canonical Domain Shape
```

### Key Architectural Rules for Backend Services

1. **Isolation**: A domain (like `api/treasury/`) should not import schemas or logic from another domain directly if it can be avoided. Seams should use clear public interfaces.
2. **RPC Mutations**: Multi-row writes must be handled via PostgreSQL RPCs (`call_rpc`) to ensure atomic rollbacks and proper `audit_logs` tracking.
3. **Tenant Integrity**: Every tenant table carries `chapter_id`. Requests resolve `chapter_id` from the authenticated user token, *never* from the client payload.

---

## 4. Frontend Structure (`fratos/`)

The frontend uses Next.js App Router but keeps most logic abstracted in hooks and typed API clients.

```mermaid
graph LR
    A[app/layout.tsx] --> B[Views]
    
    subgraph Views [views/]
        Dash[dashboard.tsx]
        Events[events.tsx]
        Fines[fines.tsx]
        Members[members.tsx]
        Standing[standing.tsx]
    end
    
    B --> C[Components]
    
    subgraph Shared [Shared UI]
        C[components/ui/]
        Forms[components/forms/]
        Hooks[hooks/use-api.ts]
        APIClient[lib/api-client.ts]
    end
```

---

## 5. Security & Auth Flow

1. **JWT Auth**: Officers/Members log in via `POST /api/auth/login`. The server returns an HS256 JWT containing `sub=member.id`.
2. **RBAC Guard**: The `api/rbac` module verifies permissions. API endpoints use `require_permission("domain:action")`.
3. **Service Role DB**: The API uses a service-role PostgreSQL client. Row-Level Security (RLS) is present but bypassed by the backend; instead, backend routes strictly filter by the token's `chapter_id`.

```mermaid
flowchart LR
    Request[HTTP Request + JWT] --> AuthDep[FastAPI Dependency: get_current_user]
    AuthDep --> Token[Decode JWT -> member_id, chapter_id]
    Token --> PermCheck[has_permission(member_id, 'action')]
    PermCheck -->|Allowed| Handler[Execute Route Handler]
    PermCheck -->|Denied| 403[403 Forbidden]
```

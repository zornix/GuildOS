# Feature Status — FraternityOS Attendance MVP

Last updated: 2026-04-06

## MVP Features (Active)

| Feature | Backend | Frontend | Status |
|---------|---------|----------|--------|
| Officer email login | POST /api/auth/login | Login form in use-auth.tsx | COMPLETE |
| GET /api/auth/me | Validates JWT, returns member | Used for session init | COMPLETE |
| Member invite | POST /api/auth/invite | Not exposed in UI | BACKEND ONLY |
| Events CRUD | Full REST endpoints | List, detail, create, delete | COMPLETE |
| Check-in links | Generate/deactivate short codes | Open/close UI with countdown | COMPLETE |
| Phone check-in | POST /api/attendance/checkin/{code}/phone | /c/{code} HTML page | COMPLETE |
| JWT check-in | POST /api/attendance/checkin/{code} | Check-in form in events view | COMPLETE |
| Attendance roster | GET /api/attendance/event/{id} | Per-event roster view | COMPLETE |
| Manual check-in | POST /api/attendance/event/{id}/manual/{mid} | Officer button on roster | COMPLETE |
| Excuse submit | POST /api/excuses/event/{id} | Excuse form modal | COMPLETE |
| Excuse review | PUT /api/excuses/{id}/review | Approve/deny on dashboard | COMPLETE |
| Excuse list | GET /api/excuses | Officer sees all, member sees own | COMPLETE |
| Fines list | GET /api/fines | Filter by status; pay (member) / waive (officer) | COMPLETE |
| Fine pay/waive | POST /api/fines/{id}/pay, /waive | Pay for self; officers waive only | COMPLETE |
| Fine summary | GET /api/fines/summary | Not exposed in UI | BACKEND ONLY |
| Manual fine processing | POST /api/fines/process-event/{id} | Button on past event detail | COMPLETE |
| Auto-fine cron | GET /api/cron/process-fines | Vercel Cron every 15 min | COMPLETE |
| Members roster | GET /api/members | List with role badges | COMPLETE |
| Role management | PUT /api/members/{id}/role | Promote/demote buttons | COMPLETE |
| Member standing | GET /api/standing | Standing tab (officers only) with rules | COMPLETE |

## Deferred Features (in deferred/)

- Delinquency scoring engine (weighted engagement scores)
- Security auto-assignment
- Reminder/notification system
- Mock API mode
- Supabase SSR auth (magic link flow)
- Advanced per-member event breakdown

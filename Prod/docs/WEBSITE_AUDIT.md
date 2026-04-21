# Website Specification Audit (Current State)

Date: 2026-04-20
Audit scope: Repository-defined product specs and user-facing documentation for the current FraternityOS/GuildOS app.

## 1) Website Purpose

The website is positioned as an internal chapter operations platform for Greek-letter organizations (primarily fraternities). Its core purpose is to help officers manage chapter accountability workflows around events and attendance with low-friction member participation.

Key purpose statements:

- `Prod/README.md`: "FraternityOS is a chapter operations tool for Greek-letter organizations: events, attendance (including phone check-in via short links), excuses, fines, member roster, and simple standing rules."
- `GuildOS/fratos/app/layout.tsx`: metadata description is "Chapter operations platform."
- `GuildOS/README.MD`: "Attendance tracking, excuses, and fines for fraternity chapters."

## 2) Services Offered (Current MVP)

The current app specifications describe a chapter-operations MVP focused on officer administration and attendance compliance.

Primary services:

1. Officer authentication (email login + JWT-backed session)
2. Member roster management (list members, role updates)
3. Events CRUD (create, list, detail, update/delete)
4. Check-in link management (open/close short-lived links)
5. Phone-based check-in for members (no member login required)
6. Attendance roster and manual officer check-ins
7. Excuse submission and officer review (approve/deny)
8. Fine administration (manual and scheduled processing)
9. Member standing view

Supporting sources:

- `Prod/docs/FEATURES.md` (MVP status table, endpoint/UI mapping)
- `GuildOS/README.MD` (feature list and endpoint groups)
- `GuildOS/fratos/fraternity-os-frontend.tsx` (main navigation: Dashboard, Events, Fines, Members, Standing)

## 3) Creators / Ownership / Operator Identity

Current repository artifacts do not clearly identify the public operator, legal entity, or named creators of the website.

Findings:

- No visible license file found in repository root(s).
- Package manifests are private/minimal and do not declare `author` metadata.
- No obvious public-facing `about`, `privacy`, or `terms` pages were found.
- Existing docs are technical and product-focused rather than legal/ownership-focused.

Auditor note:
Ownership details should be treated as "not explicitly documented in-repo" until supplied from an external source (company docs, legal pages, or domain registration/business records).

## 4) Unique Benefits / Differentiators

The strongest documented differentiator is a phone-first attendance flow that reduces check-in friction for members while preserving officer control.

Core differentiators:

- No-login member check-in via short-lived officer-issued links (`/c/{code}`).
- Lightweight standalone check-in page (HTML + vanilla JS) for fast mobile use.
- Unified operations workflow: attendance + excuses + fines + standing in one system.
- Fast time-to-action messaging (check-in in seconds) in product docs.

Supporting sources:

- `Prod/docs/PHONE_LOGIN.md` (problem, solution, flow, and rationale)
- `GuildOS/deferred/docs/ROADMAP.md` (zero-friction onboarding/check-in vision)
- `Prod/docs/FEATURES.md` (integrated workflow across attendance, excuses, fines, and standing)

## 5) Brand and Specification Consistency Notes

A website auditor should be aware of several spec inconsistencies:

- Naming variance: repository references both "GuildOS" and "FraternityOS."
- Phone format inconsistency across docs/code in some areas (9-digit vs 10-digit references).
- Some roadmap/deferred documents include future-state scope; production audit should prioritize `Prod/docs/FEATURES.md` and active app code paths.

## 6) Compliance and Audit Readiness Gaps

The following items are not clearly represented in current website specs:

- Data controller identity (company/person name)
- Public contact channel for compliance requests
- Privacy policy and data retention statement
- Terms of service / acceptable use terms
- Explicit subprocessor disclosure (beyond technical deployment references)

## 7) Recommended Auditor-Facing Positioning (Based on Current Specs)

Purpose statement:
"FraternityOS is a chapter operations platform that helps fraternity officers run attendance and accountability workflows with low-friction member check-in."

Service statement:
"The service provides officer login, member roster management, event operations, short-link mobile check-ins, excuse review, fine processing, and standing visibility."

Creator/ownership statement:
"Not explicitly documented in this repository; ownership and legal operator information should be supplied separately for formal audit use."

Unique benefits statement:
"The product's key advantage is a fast, phone-first check-in flow that removes member login friction while keeping attendance control with officers through short-lived check-in links."

-- 0001_mvp_schema.sql
-- Abort if this migration appears to have already been applied
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'chapters'
    ) THEN
        RAISE EXCEPTION
            '0001_mvp_schema.sql aborted: target database is not empty or migration was already applied (table "chapters" already exists).';
    END IF;
END $$;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =========================================================
-- Chapters
-- =========================================================
CREATE TABLE chapters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    organization TEXT NOT NULL,
    school TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================================================
-- Members
-- =========================================================
CREATE TABLE members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    role TEXT NOT NULL DEFAULT 'member',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT members_role_check
        CHECK (role IN ('officer', 'member')),

    CONSTRAINT members_status_check
        CHECK (status IN ('active', 'inactive', 'alumni'))
);

CREATE INDEX ix_members_chapter_id ON members(chapter_id);

-- =========================================================
-- Events
-- =========================================================
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    event_date DATE NOT NULL,
    event_time TIME NOT NULL,
    location TEXT NOT NULL,
    required BOOLEAN NOT NULL DEFAULT FALSE,
    fine_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_events_chapter_id ON events(chapter_id);
CREATE INDEX ix_events_event_date ON events(event_date);

-- =========================================================
-- Attendance
-- =========================================================
CREATE TABLE attendance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    checked_in BOOLEAN NOT NULL DEFAULT FALSE,
    checked_in_at TIMESTAMPTZ,
    method TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT attendance_unique_event_member UNIQUE (event_id, member_id),

    CONSTRAINT attendance_method_check
        CHECK (method IN ('manual', 'link'))
);

CREATE INDEX ix_attendance_event_id ON attendance(event_id);
CREATE INDEX ix_attendance_member_id ON attendance(member_id);

-- =========================================================
-- Excuses
-- =========================================================
CREATE TABLE excuses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_by UUID REFERENCES members(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT excuses_unique_event_member UNIQUE (event_id, member_id),

    CONSTRAINT excuses_status_check
        CHECK (status IN ('pending', 'approved', 'denied'))
);

CREATE INDEX ix_excuses_event_id ON excuses(event_id);
CREATE INDEX ix_excuses_member_id ON excuses(member_id);

-- =========================================================
-- Fines
-- =========================================================
CREATE TABLE fines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES events(id) ON DELETE SET NULL,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    amount NUMERIC(10,2) NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unpaid',
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at TIMESTAMPTZ,
    waived_by UUID REFERENCES members(id) ON DELETE SET NULL,

    CONSTRAINT fines_amount_check
        CHECK (amount >= 0),

    CONSTRAINT fines_status_check
        CHECK (status IN ('unpaid', 'paid', 'waived'))
);

CREATE INDEX ix_fines_member_id ON fines(member_id);
CREATE INDEX ix_fines_chapter_id ON fines(chapter_id);
CREATE INDEX ix_fines_status ON fines(status);
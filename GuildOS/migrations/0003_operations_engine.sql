-- 0003_operations_engine.sql
-- VP Operations Engine baseline schema + starter templates.

CREATE TABLE IF NOT EXISTS event_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID REFERENCES chapters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    event_type TEXT NOT NULL,
    default_required BOOLEAN NOT NULL DEFAULT TRUE,
    default_fine_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_event_templates_chapter_id ON event_templates(chapter_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_event_templates_global_type
    ON event_templates(event_type)
    WHERE chapter_id IS NULL;

CREATE TABLE IF NOT EXISTS event_template_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID NOT NULL REFERENCES event_templates(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    min_assignees INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT event_template_roles_min_assignees_check CHECK (min_assignees > 0),
    CONSTRAINT event_template_roles_unique_name UNIQUE (template_id, name)
);

CREATE INDEX IF NOT EXISTS ix_event_template_roles_template_id ON event_template_roles(template_id);

CREATE TABLE IF NOT EXISTS event_template_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID NOT NULL REFERENCES event_templates(id) ON DELETE CASCADE,
    role_name TEXT,
    title TEXT NOT NULL,
    description TEXT,
    due_offset_hours INT NOT NULL DEFAULT 0,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT event_template_tasks_unique_title UNIQUE (template_id, title)
);

CREATE INDEX IF NOT EXISTS ix_event_template_tasks_template_id ON event_template_tasks(template_id);

CREATE TABLE IF NOT EXISTS event_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    assigned_member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    reliability_score NUMERIC(5,2) NOT NULL DEFAULT 0,
    completion_rate NUMERIC(5,2) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'unassigned',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT event_roles_status_check CHECK (status IN ('unassigned', 'assigned', 'complete')),
    CONSTRAINT event_roles_unique_name UNIQUE (event_id, name)
);

CREATE INDEX IF NOT EXISTS ix_event_roles_event_id ON event_roles(event_id);
CREATE INDEX IF NOT EXISTS ix_event_roles_assigned_member_id ON event_roles(assigned_member_id);

CREATE TABLE IF NOT EXISTS event_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    role_id UUID REFERENCES event_roles(id) ON DELETE SET NULL,
    assigned_member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT,
    due_at TIMESTAMPTZ,
    due_offset_hours INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'not_started',
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT event_tasks_status_check CHECK (status IN ('not_started', 'in_progress', 'done'))
);

CREATE INDEX IF NOT EXISTS ix_event_tasks_event_id ON event_tasks(event_id);
CREATE INDEX IF NOT EXISTS ix_event_tasks_role_id ON event_tasks(role_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_event_tasks_dedupe
    ON event_tasks(event_id, title, COALESCE(role_id, '00000000-0000-0000-0000-000000000000'::uuid));

CREATE TABLE IF NOT EXISTS post_event_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    attendance_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    issues JSONB NOT NULL DEFAULT '[]'::jsonb,
    missed_responsibilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT post_event_reports_unique_event UNIQUE (event_id)
);

CREATE INDEX IF NOT EXISTS ix_post_event_reports_event_id ON post_event_reports(event_id);

DO $$
DECLARE
    party_template_id UUID;
    philanthropy_template_id UUID;
    meeting_template_id UUID;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM event_templates WHERE event_type = 'party' AND chapter_id IS NULL
    ) THEN
        INSERT INTO event_templates (name, description, event_type, default_required, default_fine_amount)
        VALUES (
            'Party',
            'Prebuilt flow for chapter social events with safety and teardown coverage.',
            'party',
            TRUE,
            25
        )
        RETURNING id INTO party_template_id;

        INSERT INTO event_template_roles (template_id, name, description, min_assignees) VALUES
            (party_template_id, 'security', 'Entry control and incident handling.', 2),
            (party_template_id, 'setup', 'Venue setup and pre-event preparation.', 2),
            (party_template_id, 'cleanup', 'Post-event cleanup and reset.', 2),
            (party_template_id, 'sober monitor', 'Safety checks throughout the event.', 2);

        INSERT INTO event_template_tasks (template_id, role_name, title, description, due_offset_hours, sort_order) VALUES
            (party_template_id, 'security', 'Build guest list', 'Finalize approved guest list and doorman notes.', -24, 1),
            (party_template_id, 'security', 'Risk walkthrough', 'Review exits, safety plan, and escalation steps.', -6, 2),
            (party_template_id, 'setup', 'Prepare check-in station', 'Set up check-in table and signage.', -2, 3),
            (party_template_id, 'cleanup', 'Run cleanup inspection', 'Confirm all cleanup zones completed.', 2, 4);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM event_templates WHERE event_type = 'philanthropy' AND chapter_id IS NULL
    ) THEN
        INSERT INTO event_templates (name, description, event_type, default_required, default_fine_amount)
        VALUES (
            'Philanthropy',
            'Prebuilt flow for philanthropic events and partner coordination.',
            'philanthropy',
            TRUE,
            15
        )
        RETURNING id INTO philanthropy_template_id;

        INSERT INTO event_template_roles (template_id, name, description, min_assignees) VALUES
            (philanthropy_template_id, 'coordinator', 'Owns timeline and event completion.', 1),
            (philanthropy_template_id, 'volunteer captain', 'Manages volunteer shifts.', 1),
            (philanthropy_template_id, 'setup', 'Handles materials and venue prep.', 2),
            (philanthropy_template_id, 'partner liaison', 'Coordinates with community partner.', 1);

        INSERT INTO event_template_tasks (template_id, role_name, title, description, due_offset_hours, sort_order) VALUES
            (philanthropy_template_id, 'partner liaison', 'Confirm partner details', 'Finalize partner deliverables and timeline.', -72, 1),
            (philanthropy_template_id, 'volunteer captain', 'Publish shift list', 'Share volunteer shifts and assignments.', -24, 2),
            (philanthropy_template_id, 'coordinator', 'Publish attendance requirement', 'Confirm attendance/fine policy for members.', -24, 3),
            (philanthropy_template_id, 'coordinator', 'Post event media/report', 'Collect recap photos and final impact report.', 6, 4);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM event_templates WHERE event_type = 'chapter_meeting' AND chapter_id IS NULL
    ) THEN
        INSERT INTO event_templates (name, description, event_type, default_required, default_fine_amount)
        VALUES (
            'Chapter Meeting',
            'Prebuilt flow for chapter meetings with agenda and minutes discipline.',
            'chapter_meeting',
            TRUE,
            10
        )
        RETURNING id INTO meeting_template_id;

        INSERT INTO event_template_roles (template_id, name, description, min_assignees) VALUES
            (meeting_template_id, 'agenda owner', 'Owns meeting agenda and sequencing.', 1),
            (meeting_template_id, 'attendance lead', 'Runs check-in and attendance verification.', 1),
            (meeting_template_id, 'minutes owner', 'Captures and publishes official notes.', 1);

        INSERT INTO event_template_tasks (template_id, role_name, title, description, due_offset_hours, sort_order) VALUES
            (meeting_template_id, 'agenda owner', 'Publish agenda', 'Share agenda and expected prep before meeting.', -24, 1),
            (meeting_template_id, 'attendance lead', 'Open check-in link', 'Generate and verify check-in link at start.', 0, 2),
            (meeting_template_id, 'minutes owner', 'Record motions', 'Capture motions, votes, and action items.', 1, 3),
            (meeting_template_id, 'minutes owner', 'Distribute minutes', 'Publish minutes and assigned follow-ups.', 12, 4);
    END IF;
END $$;

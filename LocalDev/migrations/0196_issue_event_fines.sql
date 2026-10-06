-- F-057: one atomic invoice batch; the event lock serializes concurrent issuers.
CREATE OR REPLACE FUNCTION tr_issue_event_fines(
    p_chapter_id UUID, p_event_id UUID, p_member_ids JSONB,
    p_amount_cents BIGINT, p_description TEXT, p_actor_id UUID
) RETURNS JSONB
LANGUAGE plpgsql AS $$
DECLARE
    v_member UUID;
    v_invoice JSONB;
    v_issued JSONB := '[]'::jsonb;
    v_skipped JSONB := '[]'::jsonb;
BEGIN
    PERFORM 1 FROM events
     WHERE id = p_event_id AND chapter_id = p_chapter_id AND NOT cancelled
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'event % not found in chapter %', p_event_id, p_chapter_id;
    END IF;
    FOR v_member IN SELECT value::uuid FROM jsonb_array_elements_text(p_member_ids)
    LOOP
        IF NOT EXISTS (SELECT 1 FROM members WHERE id = v_member AND chapter_id = p_chapter_id) THEN
            RAISE EXCEPTION 'member % is not in chapter %', v_member, p_chapter_id;
        END IF;
        IF EXISTS (SELECT 1 FROM unpaid_invoices
                    WHERE chapter_id = p_chapter_id AND source_event_id = p_event_id
                      AND member_id = v_member AND kind = 'fine' AND status <> 'cancelled') THEN
            v_skipped := v_skipped || jsonb_build_array(v_member);
        ELSE
            v_invoice := tr_create_invoice_v2(
                p_chapter_id, v_member, 'fine', p_amount_cents, p_description, p_actor_id,
                NULL, p_actor_id, NULL, 'fine:' || p_event_id || ':' || v_member, p_event_id);
            v_issued := v_issued || jsonb_build_array(v_invoice);
        END IF;
    END LOOP;
    RETURN jsonb_build_object('issued', v_issued, 'skipped_member_ids', v_skipped);
END;
$$;
REVOKE ALL ON FUNCTION tr_issue_event_fines(UUID, UUID, JSONB, BIGINT, TEXT, UUID) FROM PUBLIC;

-- Keep only the newest active link per event, then make that a rule.
UPDATE checkin_links c SET active = false
 WHERE c.active
   AND EXISTS (SELECT 1 FROM checkin_links n
                WHERE n.event_id = c.event_id AND n.active
                  AND (n.created_at, n.id) > (c.created_at, c.id));
CREATE UNIQUE INDEX IF NOT EXISTS uq_checkin_links_one_active_per_event
    ON checkin_links(event_id) WHERE active;

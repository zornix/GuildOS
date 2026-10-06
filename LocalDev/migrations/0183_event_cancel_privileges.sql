-- 0181 left ev_delete_or_cancel_event executable by PUBLIC; only the app role calls it.
REVOKE ALL ON FUNCTION ev_delete_or_cancel_event(UUID, UUID, UUID) FROM PUBLIC;

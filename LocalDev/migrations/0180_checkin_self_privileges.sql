-- 0178 left at_checkin_self executable by PUBLIC; only the app role calls it.
REVOKE ALL ON FUNCTION at_checkin_self(UUID, UUID, UUID) FROM PUBLIC;

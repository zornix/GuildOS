from api.config import settings

_pg_client = None


def _get_pg():
    global _pg_client
    if _pg_client is None:
        from api.postgres_client import PostgresClient
        _pg_client = PostgresClient(settings.DATABASE_URL, settings.JWT_SECRET)
    return _pg_client


def get_supabase():
    if settings.use_local_db:
        return _get_pg()
    from supabase import create_client
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


def get_supabase_admin():
    if settings.use_local_db:
        return _get_pg()
    from supabase import create_client
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

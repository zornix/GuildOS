from api.config import settings

_pg_client = None


def get_supabase():
    global _pg_client
    if _pg_client is None:
        from api.postgres_client import PostgresClient
        _pg_client = PostgresClient(settings.POSTGRES_URL_NON_POOLING, settings.SUPABASE_JWT_SECRET)
    return _pg_client


def get_supabase_admin():
    return get_supabase()

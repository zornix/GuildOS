"""#109: a blocking DB call inside an `async def` handler freezes the whole server.

Handlers and dependencies are plain `def` (FastAPI runs them in its threadpool)
unless they truly await something, and those never touch the DB client directly.
"""
import inspect

from fastapi.routing import APIRoute

from api.index import app


def _callables(dependant):
    yield dependant.call
    for sub in dependant.dependencies:
        yield from _callables(sub)


def test_async_handlers_only_where_they_await_and_never_hit_the_db_directly():
    offenders = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for fn in _callables(route.dependant):
            if fn is None or not inspect.iscoroutinefunction(fn):
                continue
            src = inspect.getsource(fn)
            on_loop = "\n".join(l for l in src.splitlines() if "to_thread" not in l)
            if "await " not in src or "get_db()" in on_loop or "call_rpc(" in on_loop:
                offenders.append(f"{route.path}: {fn.__qualname__}")
    assert offenders == [], f"async handlers that block the event loop: {offenders}"

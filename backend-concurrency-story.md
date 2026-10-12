# The backend that answered one request at a time

*Issue #109, fixed 2026-10-07. Written up as a debugging story.*

## The symptom

Opening the app showed "connecting to the server" for about three and a half
seconds on a local machine, against a database that answers a round trip in
35 ms. The single-page app fires 14 requests when it boots: who am I, my
permissions, the roster, events, dues, tasks, announcements, and so on. Each
one alone took between 50 ms and 700 ms. Together they took the **sum** of
those times, as if the browser had sent them one after another. It had not.
It sent all 14 at once.

## Measuring before guessing

The first thing I did was make the number reproducible. A small script logs in
with the demo officer, then fires the same 14 GETs twice: once sequentially,
once from 14 threads at the same time, and prints both totals and the slowest
single request.

| Run (before) | Total |
|---|---|
| 14 requests, one after another | 6.97 s |
| 14 requests, all at once | 5.70 s |
| Slowest single request | 1.72 s |

Concurrent was barely faster than sequential. Something serialised the whole
server. With a healthy backend the concurrent total should be close to the
slowest single request, not to the sum.

## The cause

The backend is FastAPI over PostgreSQL through psycopg2. FastAPI has one rule
that matters here:

- an `async def` handler runs **on the event loop**; if it blocks, everything
  blocks;
- a plain `def` handler is handed to a **threadpool**, and the loop keeps
  serving other requests while it waits.

All 138 route handlers were `async def`. None of them awaited anything. Every
one of them called the blocking psycopg2 client. So each database query froze
the event loop for the length of a round trip to Supabase, and the 14 startup
requests queued up behind each other. The authentication dependency,
`get_current_user`, was also `async def` and also hit the database, so even a
handler that did nothing paid that toll serially.

Nobody had decided this. The first commit followed the FastAPI tutorial's
`async def` template while using a database client that was also blocking.
A later migration to psycopg2 kept the same interface, and the pattern came
along for the ride. It is the kind of bug that does not show up in a test
suite, because tests send one request at a time.

## The approach

The lazy fix is the correct fix: do not add infrastructure, remove the word
`async` where it is lying.

1. **Handlers and dependencies become plain `def`.** FastAPI then runs them in
   its threadpool. This was mechanical across 36 route files, plus the auth
   dependency, the permission dependency and the cron secret check.
2. **Fake-async services become plain functions.** The check-in link, session
   and member-standing services were `async def` wrappers around blocking
   queries; callers awaited them for no reason. They are ordinary functions
   now, and so are the handlers that used them.
3. **Keep `async` only where something is truly awaited.** The cron drain
   already used `asyncio.to_thread`. The Twilio inbound webhook must `await
   request.form()`, so its database write moved into a helper that runs via
   `asyncio.to_thread`. The roster CSV upload read its file with `await
   file.read()`; a plain `def` handler can read the spooled file directly.
4. **A guard test so it cannot creep back.** One test walks every registered
   route and dependency: if a callable is a coroutine, its source must contain
   an `await`, and it may not call the database client except on a
   `to_thread` line.
5. **Tests that awaited handlers directly** now just call them. About fifty
   lines across twelve files.

## The twist

After the change, the concurrent run got **worse**: 32 seconds, with some
requests failing with "connection pool exhausted".

The handlers were now parallel, so they exposed a second problem that the
serial server had hidden. The connection pool was psycopg2's
`ThreadedConnectionPool(1, 10)`, and two of its behaviours bit at once:

- when an eleventh thread asks for a connection it **raises immediately**
  rather than waiting;
- when a connection is returned and the pool already holds `minconn` idle
  connections (here: one), it **closes it**.

So under load, nearly every query opened a brand-new TLS connection to the
Supabase pooler, roughly a second each, used it once, and threw it away. The
serial server never noticed because it only ever needed one connection.

The fix was a small subclass: `getconn` waits on a bounded semaphore for up to
ten seconds before failing, and the pool keeps every connection it has opened
instead of closing all but one. Connections are still opened lazily, so a cold
start costs nothing extra. One unit test with a fake connection covers both
behaviours.

## The result

Same script, same 14 requests, after the change and with warm connections:

| Run (after) | Total |
|---|---|
| 14 requests, one after another | 3.50 s |
| 14 requests, all at once | **0.77 s** |
| Slowest single request | 0.65 s |

The concurrent total is now the slowest request plus a little, which is what
a server that actually works in parallel looks like. The first concurrent
burst after a cold start takes about three seconds while the pool opens its
connections; every burst after that is under a second.

The sequential total also halved, because `get_current_user` no longer
serialises the token check in front of every handler.

## What I would say in an interview

- **Measure first, with a script you can rerun.** The before and after
  numbers came from the same twenty lines of Python. Without them I could not
  have told the real fix from a plausible one, and I would not have caught the
  pool regression at all.
- **Read the framework's one relevant rule.** The whole bug is "async def
  without an await". Knowing how FastAPI schedules sync versus async handlers
  turned a mysterious slowness into a mechanical edit.
- **Fixing the bottleneck exposes the next one.** Parallel handlers found a
  pool that had never been exercised in parallel. Expect the second problem
  and keep the measurement running while you fix the first.
- **Leave a guard, not a comment.** The test that walks the routes costs
  nothing and makes the mistake impossible to repeat quietly.
- **Prefer deleting to adding.** The fix removed `async` from about 150
  functions and added one small pool class. No new dependency, no task queue,
  no caching layer.

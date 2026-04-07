"""
FraternityOS Backend — FastAPI + Supabase
==========================================
Entry point: api/index.py (Vercel serverless function)

Deploy:  vercel --prod
Local:   uvicorn api.index:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.routes import auth, events, attendance, excuses, fines, members, checkin_page, cron, standing

app = FastAPI(
    title="FraternityOS API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(attendance.router, prefix="/api/attendance", tags=["Attendance"])
app.include_router(excuses.router, prefix="/api/excuses", tags=["Excuses"])
app.include_router(fines.router, prefix="/api/fines", tags=["Fines"])
app.include_router(members.router, prefix="/api/members", tags=["Members"])
app.include_router(checkin_page.router, prefix="/c", tags=["Check-In Page"])
app.include_router(cron.router, prefix="/api/cron", tags=["Cron"])
app.include_router(standing.router, prefix="/api/standing", tags=["Standing"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}

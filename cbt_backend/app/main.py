from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_health import router as health_router
from app.api.routes_sessions import router as sessions_router
from app.api.routes_ws import router as ws_router
from app.api.routes_runs import router as runs_router

from app.persistence.checkpointer import checkpointer_manager
from app.persistence.db import exec_sql
from app.persistence.run_tables import RUNS_TABLE_SQL, RUN_EVENTS_TABLE_SQL, RUNS_ALTER_SQL


SESSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
  thread_id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  mode TEXT NOT NULL DEFAULT 'human_optional'
);
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    checkpointer_manager.start()

    exec_sql(SESSIONS_TABLE_SQL)
    exec_sql(RUNS_TABLE_SQL)
    exec_sql(RUN_EVENTS_TABLE_SQL)
    exec_sql(RUNS_ALTER_SQL)

    yield

    checkpointer_manager.stop()


app = FastAPI(title="CBT Protocol Backend", lifespan=lifespan)

# ✅ CORS (Vite usually runs on 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(sessions_router)
app.include_router(ws_router)
app.include_router(runs_router)

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routes_health import router as health_router
from app.api.routes_sessions import router as sessions_router
from app.persistence.checkpointer import checkpointer_manager
from app.persistence.db import exec_sql


SESSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
  thread_id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  mode TEXT NOT NULL DEFAULT 'human_optional'  -- future: 'auto'/'human_required'
);
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: init checkpointer + create checkpoint tables
    checkpointer_manager.start()

    # App tables
    exec_sql(SESSIONS_TABLE_SQL)

    yield

    # Shutdown
    checkpointer_manager.stop()


app = FastAPI(title="CBT Protocol Backend", lifespan=lifespan)

app.include_router(health_router)
app.include_router(sessions_router)

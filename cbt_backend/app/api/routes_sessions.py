from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.schemas import CreateSessionRequest, CreateSessionResponse, SessionListItem
from app.persistence.db import exec_sql, fetch_all, fetch_one
from app.persistence.checkpointer import checkpointer_manager
from app.utils.ids import new_thread_id

router = APIRouter(prefix="/sessions", tags=["sessions"])

class RunRequest(BaseModel):
    input_text: str

@router.post("", response_model=CreateSessionResponse)
def create_session(body: CreateSessionRequest):
    thread_id = new_thread_id()
    exec_sql(
        "INSERT INTO sessions (thread_id, mode) VALUES (%s, %s)",
        [thread_id, body.mode],
    )
    return CreateSessionResponse(thread_id=thread_id)


@router.get("/history", response_model=list[SessionListItem])
def list_sessions(limit: int = 20):
    limit = max(1, min(limit, 200))
    rows = fetch_all(
        "SELECT thread_id, created_at::text, mode FROM sessions ORDER BY created_at DESC LIMIT %s",
        [limit],
    )
    return [SessionListItem(thread_id=r["thread_id"], created_at=r["created_at"], mode=r["mode"]) for r in rows]


@router.get("/{thread_id}/state")
def get_state(thread_id: str):
    # Ensure session exists
    row = fetch_one("SELECT thread_id FROM sessions WHERE thread_id=%s", [thread_id])
    if not row:
        raise HTTPException(status_code=404, detail="Unknown thread_id")

    # Pull latest checkpoint from LangGraph checkpointer
    # (No checkpoint exists until we run the graph at least once)
    checkpointer = checkpointer_manager.get()

    config = {"configurable": {"thread_id": thread_id}}
    checkpoint_tuple = checkpointer.get_tuple(config)

    if checkpoint_tuple is None:
        return {
            "thread_id": thread_id,
            "has_checkpoint": False,
            "checkpoint": None,
        }

    # checkpoint_tuple usually contains (checkpoint, metadata, parent_config)
    # We'll return it as-is for now; later we'll shape it.
    return {
        "thread_id": thread_id,
        "has_checkpoint": True,
        "checkpoint": {
            "checkpoint": checkpoint_tuple.checkpoint,
            "metadata": checkpoint_tuple.metadata,
            "parent_config": checkpoint_tuple.parent_config,
        },
    }


@router.post("/{thread_id}/run")
def run_session(thread_id: str, body: RunRequest):
    # Ensure session exists
    row = fetch_one("SELECT thread_id FROM sessions WHERE thread_id=%s", [thread_id])
    if not row:
        raise HTTPException(status_code=404, detail="Unknown thread_id")

    from app.services.runner import run_once

    result = run_once(thread_id=thread_id, input_text=body.input_text)
    return {"thread_id": thread_id, "result": result}

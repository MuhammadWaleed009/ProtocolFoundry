from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.api.schemas import CreateSessionRequest, CreateSessionResponse, SessionListItem
from app.persistence.db import exec_sql, fetch_all, fetch_one
from app.persistence.checkpointer import checkpointer_manager
from app.utils.ids import new_thread_id
from app.persistence.run_store import list_runs
from app.persistence.run_store import get_latest_run, get_latest_halted_run, get_run
from app.services.runner import resume_with_ws

router = APIRouter(prefix="/sessions", tags=["sessions"])

class HumanDecisionBody(BaseModel):
    approved: bool
    edited_text: Optional[str] = None
    feedback: Optional[str] = None

class RunRequest(BaseModel):
    input_text: str
    require_human_approval: bool | None = None

class ApproveRequest(BaseModel):
    approved: bool
    edited_text: str | None = None
    feedback: str | None = None

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
    row = fetch_one("SELECT thread_id FROM sessions WHERE thread_id=%s", [thread_id])
    if not row:
        raise HTTPException(status_code=404, detail="Unknown thread_id")

    checkpointer = checkpointer_manager.get()
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint_tuple = checkpointer.get_tuple(config)

    if checkpoint_tuple is None:
        return {
            "thread_id": thread_id,
            "has_checkpoint": False,
            "checkpoint": None,
        }

    ct = checkpoint_tuple.checkpoint

    return {
        "thread_id": thread_id,
        "has_checkpoint": True,
        "checkpoint_id": ct.get("id"),
        "ts": ct.get("ts"),
        "channel_values": ct.get("channel_values"),
        "updated_channels": ct.get("updated_channels"),
        "metadata": checkpoint_tuple.metadata,
        "parent_config": checkpoint_tuple.parent_config,
    }


@router.post("/{thread_id}/run")
async def run_session(thread_id: str, body: RunRequest):
    row = fetch_one("SELECT thread_id, mode FROM sessions WHERE thread_id=%s", [thread_id])
    if not row:
        raise HTTPException(status_code=404, detail="Unknown thread_id")

    mode = row["mode"]

    if mode == "human_required":
        require_human_approval = True
    elif mode == "auto":
        require_human_approval = False
    else:
        require_human_approval = bool(body.require_human_approval) if body.require_human_approval is not None else True

    from app.services.runner import run_with_ws

    result = await run_with_ws(
        thread_id=thread_id,
        input_text=body.input_text,
        require_human_approval=require_human_approval,
    )
    return {"thread_id": thread_id, "require_human_approval": require_human_approval, "result": result}


@router.post("/{thread_id}/approve")
async def approve_and_resume(thread_id: str, body: ApproveRequest):
    row = fetch_one("SELECT thread_id FROM sessions WHERE thread_id=%s", [thread_id])
    if not row:
        raise HTTPException(status_code=404, detail="Unknown thread_id")

    # ✅ Prevent "run_id=unknown" / approving when nothing is pending
    halted = get_latest_halted_run(thread_id)
    if not halted:
        raise HTTPException(status_code=409, detail="No pending approval for this thread")



    result = await resume_with_ws(
        thread_id=thread_id,
        run_id=halted["run_id"],      # ✅ always resume the latest halted run
        approved=body.approved,
        edited_text=body.edited_text,
        feedback=body.feedback,       # ✅ pass feedback through
    )
    return {"thread_id": thread_id, "result": result}



@router.get("/{thread_id}/runs")
def list_session_runs(thread_id: str, limit: int = 20):
    row = fetch_one("SELECT thread_id FROM sessions WHERE thread_id=%s", [thread_id])
    if not row:
        raise HTTPException(status_code=404, detail="Unknown thread_id")
    return {"thread_id": thread_id, "runs": list_runs(thread_id, limit=limit)}


@router.get("/{thread_id}/latest-run")
def latest_run(thread_id: str):
    row = fetch_one("SELECT thread_id FROM sessions WHERE thread_id=%s", [thread_id])
    if not row:
        raise HTTPException(status_code=404, detail="Unknown thread_id")
    r = get_latest_run(thread_id)
    return {"thread_id": thread_id, "latest": r}


@router.get("/{thread_id}/pending-approval")
def pending_approval(thread_id: str):
    row = fetch_one("SELECT thread_id FROM sessions WHERE thread_id=%s", [thread_id])
    if not row:
        raise HTTPException(status_code=404, detail="Unknown thread_id")

    halted = get_latest_halted_run(thread_id)
    if not halted:
        return {"thread_id": thread_id, "pending": None}

    run = get_run(halted["run_id"])
    return {"thread_id": thread_id, "pending": run}

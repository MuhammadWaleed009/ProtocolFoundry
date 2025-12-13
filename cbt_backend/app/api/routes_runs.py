from fastapi import APIRouter, HTTPException

from app.persistence.run_store import get_run, list_run_events

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}")
def get_run_detail(run_id: str):
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    return row


@router.get("/{run_id}/events")
def get_run_events(run_id: str, limit: int = 200):
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    return {"run_id": run_id, "events": list_run_events(run_id, limit=limit)}

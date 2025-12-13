from __future__ import annotations

from datetime import datetime, timezone
from app.graphs.state import GraphState


def finalize_node(state: GraphState) -> dict:
    drafts = state.get("drafts") or []
    latest = drafts[-1] if drafts else {}

    final = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "markdown": latest.get("markdown", ""),
        "data": latest.get("data", {}),
        "reviews": state.get("reviews", {}),
        "metrics": state.get("metrics", {}),
        "supervisor": state.get("supervisor", {}),
    }
    return {"final": final, "status": "COMPLETED"}

from __future__ import annotations

from datetime import datetime, timezone
from app.graphs.state import GraphState


def finalize_node(state: GraphState) -> GraphState:
    # Dummy final output for now (we’ll replace with CBT formatting later)
    req = state.get("request", {})
    state["final"] = {
        "title": "CBT Exercise (Skeleton)",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "echo": req.get("text", ""),
        "note": "This is a placeholder output to prove checkpointing works.",
    }
    state["status"] = "COMPLETED"
    return state

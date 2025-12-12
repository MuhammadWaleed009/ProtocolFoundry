from __future__ import annotations

from datetime import datetime, timezone
from app.graphs.state import GraphState


def intake_node(state: GraphState) -> GraphState:
    text = state.get("input_text", "").strip()

    state["request"] = {
        "type": "cbt_protocol_request",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "text": text,
    }
    state["status"] = "RUNNING"
    return state

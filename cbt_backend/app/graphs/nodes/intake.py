from __future__ import annotations

from datetime import datetime, timezone
from app.graphs.state import GraphState


def intake_node(state: GraphState) -> dict:
    text = state.get("input_text", "").strip()
    return {
        "request": {
            "type": "cbt_protocol_request",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "text": text,
        },
        "status": "RUNNING",
        "metrics": {"iteration": 1},
    }

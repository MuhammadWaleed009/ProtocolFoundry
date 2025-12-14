from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.graphs.state import GraphState


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(x: Any) -> dict:
    return x if isinstance(x, dict) else {}


def finalize_node(state: GraphState) -> dict:
    ts = _now_iso()

    drafts = state.get("drafts") or []
    latest = drafts[-1] if drafts else {}

    version = latest.get("version")
    try:
        v = int(version) if version is not None else None
    except Exception:
        v = None

    markdown = latest.get("markdown") if isinstance(latest.get("markdown"), str) else ""
    data = _as_dict(latest.get("data"))

    reviews = _as_dict(state.get("reviews"))
    supervisor = _as_dict(state.get("supervisor"))

    final = {
        "created_at": ts,
        "markdown": (markdown or "").strip(),
        "data": data,
        "reviews": reviews,
        "supervisor": supervisor,
        "human_edit": {},
    }

    summary = f"Final payload assembled{f' from draft v{v}' if v is not None else ''}."

    return {
        "current_node": "finalize",
        "status": "RUNNING",
        "final": final,
        "trace": [{"ts": ts, "node": "finalize", "summary": summary}],
        "scratchpad": {"finalize": [summary]},
    }

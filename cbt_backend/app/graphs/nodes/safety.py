from __future__ import annotations

from app.graphs.state import GraphState
from app.graphs.prompts import SAFETY_SYSTEM
from app.services.llm import chat_json


def safety_node(state: GraphState) -> dict:
    latest = (state.get("drafts") or [])[-1]
    draft_md = latest.get("markdown", "")

    out = chat_json(SAFETY_SYSTEM, f"Draft:\n{draft_md}")

    reviews = state.get("reviews") or {}
    reviews["safety"] = out

    metrics = state.get("metrics") or {}
    metrics["safety_score"] = out.get("safety_score")

    return {"reviews": reviews, "metrics": metrics}

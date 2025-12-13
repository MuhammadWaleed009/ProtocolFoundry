from __future__ import annotations

from app.graphs.state import GraphState
from app.graphs.prompts import CRITIC_SYSTEM
from app.services.llm import chat_json


def critic_node(state: GraphState) -> dict:
    latest = (state.get("drafts") or [])[-1]
    draft_md = latest.get("markdown", "")

    out = chat_json(CRITIC_SYSTEM, f"Draft:\n{draft_md}")

    reviews = state.get("reviews") or {}
    reviews["critic"] = out

    metrics = state.get("metrics") or {}
    metrics["quality_score"] = out.get("quality_score")

    return {"reviews": reviews, "metrics": metrics}

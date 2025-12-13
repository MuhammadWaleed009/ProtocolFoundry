from __future__ import annotations

from app.core.config import get_settings
from app.graphs.state import GraphState
from app.graphs.prompts import SUPERVISOR_SYSTEM
from app.services.llm import chat_json


def supervisor_node(state: GraphState) -> dict:
    s = get_settings()
    metrics = state.get("metrics") or {}
    iteration = int(metrics.get("iteration", 1))

    safety = (state.get("reviews") or {}).get("safety", {}) or {}
    critic = (state.get("reviews") or {}).get("critic", {}) or {}

    safety_pass = bool(safety.get("safety_pass", False))
    quality_pass = bool(critic.get("quality_pass", False))

    if iteration >= s.MAX_ITERATIONS:
        return {"supervisor": {"action": "finalize", "rationale": "Reached MAX_ITERATIONS."}}

    if safety_pass and quality_pass:
        return {"supervisor": {"action": "finalize", "rationale": "Safety and quality passed."}}

    summary = {"iteration": iteration, "safety": safety, "critic": critic}
    out = chat_json(SUPERVISOR_SYSTEM, f"State summary:\n{summary}")

    action = out.get("action", "revise")
    if action not in ("revise", "finalize"):
        action = "revise"

    return {"supervisor": {"action": action, "rationale": out.get("rationale", "")}}

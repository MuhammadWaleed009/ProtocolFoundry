from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core import config as s
from app.graphs.prompts import SUPERVISOR_SYSTEM
from app.graphs.state import GraphState
from app.services.llm import chat_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(x: Any, default: str = "") -> str:
    if isinstance(x, str):
        t = x.strip()
        return t if t else default
    return default


def _truncate(s: str, n: int = 160) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else (s[: n - 1] + "…")


def supervisor_node(state: GraphState) -> dict:
    ts = _now_iso()

    req = state.get("request") or {"text": state.get("input_text") or ""}
    reviews = state.get("reviews") or {}
    metrics = state.get("metrics") or {}

    safety = reviews.get("safety") or {}
    critic = reviews.get("critic") or {}

    iteration = int(metrics.get("iteration") or 1)
    max_iters = int(getattr(s, "MAX_ITERATIONS", 3))

    safety_pass = bool(safety.get("safety_pass", True))
    quality_pass = bool(critic.get("quality_pass", True))

    if iteration >= max_iters:
        supervisor = {"action": "finalize", "rationale": f"Max iterations reached ({iteration}/{max_iters})."}
        summary = f"Decision: finalize — max iterations reached ({iteration}/{max_iters})."
        return {
            "current_node": "supervisor",
            "status": "RUNNING",
            "supervisor": supervisor,
            "trace": [{"ts": ts, "node": "supervisor", "summary": summary}],
            "scratchpad": {"supervisor": [summary]},
        }

    if safety_pass and quality_pass:
        supervisor = {"action": "finalize", "rationale": "Safety and quality passed."}
        summary = "Decision: finalize — safety and quality passed ✅"
        return {
            "current_node": "supervisor",
            "status": "RUNNING",
            "supervisor": supervisor,
            "trace": [{"ts": ts, "node": "supervisor", "summary": summary}],
            "scratchpad": {"supervisor": [summary]},
        }

    decision = chat_json(
        system=SUPERVISOR_SYSTEM,
        user=(
            f"Request:\n{req}\n\n"
            f"Safety review:\n{safety}\n\n"
            f"Critic review:\n{critic}\n\n"
            f"Metrics:\n{metrics}\n\n"
            "Return ONLY JSON: {action: 'finalize'|'revise', rationale: string}."
        ),
    ) or {}

    action = decision.get("action")
    if action not in ("finalize", "revise"):
        action = "revise"

    rationale = _safe_str(decision.get("rationale"))
    if not rationale:
        rationale = "Supervisor requested revision." if action == "revise" else "Supervisor approved finalize."

    supervisor = {"action": action, "rationale": rationale.strip()}
    summary = f"Decision: {action} — {_truncate(supervisor['rationale'])}"

    return {
        "current_node": "supervisor",
        "status": "RUNNING",
        "supervisor": supervisor,
        "trace": [{"ts": ts, "node": "supervisor", "summary": summary}],
        "scratchpad": {"supervisor": [summary]},
    }

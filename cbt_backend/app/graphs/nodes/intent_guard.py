from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.graphs.state import GraphState
from app.services.llm import chat_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(x: Any, default: bool = True) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    return default


def _classify_relevance(text: str) -> tuple[bool, str]:
    """
    Use a lightweight classifier to decide if the request is CBT-related.
    Falls back to keyword check on failure.
    """
    prompt = (
        "Classify if this request is asking for CBT, mental health coping, or therapy-related guidance.\n"
        "Return ONLY JSON: {relevant: boolean, reason: string}\n\n"
        f"Request:\n{text}"
    )
    try:
        resp = chat_json(
            system="You are a strict classifier. Decide if the user is asking for CBT/mental health support.",
            user=prompt,
            model=None,
        ) or {}
        relevant = _safe_bool(resp.get("relevant"), default=False)
        reason = resp.get("reason") if isinstance(resp.get("reason"), str) else ""
        return relevant, reason
    except Exception:
        # fallback: simple keyword heuristic
        lowered = text.lower()
        keywords = ["cbt", "therapy", "mental", "anxiety", "depression", "panic", "exposure", "grounding", "coping"]
        relevant = any(k in lowered for k in keywords)
        return relevant, "keyword fallback (no LLM)"


def intent_guard_node(state: GraphState) -> dict:
    ts = _now_iso()
    text = (state.get("input_text") or "").strip()

    relevant, reason = _classify_relevance(text)

    if relevant:
        summary = "Request accepted for CBT pipeline."
        return {
            "current_node": "intent_guard",
            "status": "RUNNING",
            "is_cbt_relevant": True,
            "trace": [{"ts": ts, "node": "intent_guard", "summary": summary}],
            "scratchpad": {"intake": [summary]},
        }

    # Out-of-scope response
    message = (
        "I’m focused on CBT-style exercises and mental health coping plans. "
        "Please share a CBT-related goal (e.g., grounding for panic, exposure steps for phobia)."
    )
    markdown = (
        "## Out of scope\n\n"
        f"{message}\n\n"
        "Example prompts:\n"
        "- \"Create a grounding exercise for social anxiety\"\n"
        "- \"Design a thought-challenging worksheet for panic triggers\"\n"
        "- \"Build an exposure ladder for flying\"\n"
    )

    summary = "Request redirected — not CBT related."

    return {
        "current_node": "intent_guard",
        "status": "COMPLETED",
        "is_cbt_relevant": False,
        "final": {
            "created_at": ts,
            "markdown": markdown,
            "data": {"message": message, "reason": reason or "out_of_scope"},
            "reviews": {},
            "supervisor": {"action": "finalize", "rationale": "Out-of-scope request; provided guidance instead."},
            "human_edit": {},
        },
        "trace": [{"ts": ts, "node": "intent_guard", "summary": summary}],
        "scratchpad": {"intake": [summary]},
    }

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langgraph.types import interrupt
from app.graphs.state import GraphState


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(x: Any) -> dict:
    return x if isinstance(x, dict) else {}


def _truncate(s: str, n: int = 160) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else (s[: n - 1] + "…")


def human_review_node(state: GraphState) -> dict:
    halt_ts = _now_iso()

    final = _as_dict(state.get("final"))
    req = state.get("request") or {"text": state.get("input_text") or ""}
    req = _as_dict(req)

    # This payload becomes the pending_interrupt.value (UI can show it while halted)
    payload = {
        "kind": "human_approval",
        "message": "Review the draft before finalizing.",
        "draft": final,
        "request": req,
        "public": {
            "ts": halt_ts,
            "node": "human_review",
            "summary": "Draft ready — awaiting approval.",
        },
    }

    decision = interrupt(payload)

    resume_ts = _now_iso()
    human_response = decision if isinstance(decision, dict) else {"value": decision}

    approved = bool(human_response.get("approved", False))
    edited_text = human_response.get("edited_text")
    feedback = human_response.get("feedback")

    if not approved:
        fb = feedback if isinstance(feedback, str) and feedback.strip() else "Please revise the draft based on reviewer feedback."
        summary = "Rejected — returning to drafter with feedback."
        return {
            "current_node": "human_review",
            "status": "RUNNING",
            "halt_payload": None,
            "human_response": human_response,
            "human_feedback": fb,
            "trace": [{"ts": resume_ts, "node": "human_review", "summary": summary}],
            "scratchpad": {"human": [f"Rejected: {_truncate(fb)}"]},
        }

    # Approved
    note = "Approved."
    final_out = final
    if isinstance(edited_text, str) and edited_text.strip():
        final_out = dict(final)
        final_out["markdown"] = edited_text.strip()
        final_out["human_edit"] = {"applied": True, "note": "Final markdown updated by human reviewer.", "ts": resume_ts}
        note = "Approved — applied human edits."

    return {
        "current_node": "human_review",
        "status": "COMPLETED",
        "halt_payload": None,
        "human_response": human_response,
        "human_feedback": None,
        "final": final_out,
        "trace": [{"ts": resume_ts, "node": "human_review", "summary": note}],
        "scratchpad": {"human": [note]},
    }

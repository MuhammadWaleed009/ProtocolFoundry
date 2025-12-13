from __future__ import annotations

from app.graphs.state import GraphState
from langgraph.types import interrupt


def human_review_node(state: GraphState) -> GraphState:
    payload = {
        "kind": "human_approval",
        "message": "Review the draft before finalizing.",
        "draft": state.get("final"),
        "request": state.get("request"),
    }

    state["halt_payload"] = payload
    state["status"] = "HALTED"

    decision = interrupt(payload)

    human_response = decision if isinstance(decision, dict) else {"value": decision}
    state["human_response"] = human_response

    approved = bool(human_response.get("approved", False))
    edited_text = human_response.get("edited_text")
    feedback = human_response.get("feedback")

    # Clear halt payload after resume
    state["halt_payload"] = None

    if not approved:
        state["human_feedback"] = feedback or "Please revise the draft based on reviewer feedback."
        state["status"] = "RUNNING"
        return state

    # Approved path
    state["human_feedback"] = None

    if edited_text:
        final = state.get("final")
        if isinstance(final, dict):
            final["markdown"] = edited_text
            final["human_edit"] = {"applied": True, "note": "Final markdown updated by human reviewer."}
            state["final"] = final

    state["status"] = "COMPLETED"
    return state

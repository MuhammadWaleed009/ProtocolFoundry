from __future__ import annotations

from langgraph.graph import StateGraph, END

from app.graphs.state import GraphState
from app.graphs.nodes.intake import intake_node
from app.graphs.nodes.drafter import drafter_node
from app.graphs.nodes.safety import safety_node
from app.graphs.nodes.critic import critic_node
from app.graphs.nodes.supervisor import supervisor_node
from app.graphs.nodes.human_review import human_review_node
from app.graphs.nodes.finalize import finalize_node


def build_graph():
    g = StateGraph(GraphState)

    g.add_node("intake", intake_node)
    g.add_node("drafter", drafter_node)
    g.add_node("safety", safety_node)
    g.add_node("critic", critic_node)
    g.add_node("supervisor", supervisor_node)
    g.add_node("finalize", finalize_node)
    g.add_node("human_review", human_review_node)

    g.set_entry_point("intake")

    # Sequential review pipeline
    g.add_edge("intake", "drafter")
    g.add_edge("drafter", "safety")
    g.add_edge("safety", "critic")
    g.add_edge("critic", "supervisor")

    def route_after_supervisor(state: GraphState) -> str:
        action = (state.get("supervisor") or {}).get("action", "revise")
        return "finalize" if action == "finalize" else "drafter"

    g.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {"finalize": "finalize", "drafter": "drafter"},
    )

    # Human gate after finalize
    def route_after_finalize(state: GraphState) -> str:
        return "human_review" if state.get("require_human_approval") else "end"

    g.add_conditional_edges(
        "finalize",
        route_after_finalize,
        {"human_review": "human_review", "end": END},
    )

    # If rejected => back to drafter; if approved => END
    def route_after_human_review(state: GraphState) -> str:
        hr = state.get("human_response") or {}
        approved = bool(hr.get("approved", False))
        return "end" if approved else "drafter"

    g.add_conditional_edges(
        "human_review",
        route_after_human_review,
        {"end": END, "drafter": "drafter"},
    )

    return g

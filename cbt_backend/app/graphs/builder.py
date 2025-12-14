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


DEFAULT_MAX_ITERATIONS = 3


def _iteration(state: GraphState) -> int:
    """
    Prefer metrics.iteration if your nodes maintain it,
    otherwise derive from number of drafts (v1 -> iteration 0, v2 -> 1, ...).
    """
    metrics = state.get("metrics") or {}
    it = metrics.get("iteration")
    if isinstance(it, int):
        return max(0, it)

    drafts = state.get("drafts") or []
    # if drafts has 1 item => iter 0, 2 items => iter 1, ...
    return max(0, len(drafts) - 1)


def _max_iterations(state: GraphState) -> int:
    metrics = state.get("metrics") or {}
    mi = metrics.get("max_iterations")
    if isinstance(mi, int) and mi > 0:
        return mi
    return DEFAULT_MAX_ITERATIONS


def _safety_pass(state: GraphState) -> bool | None:
    return (state.get("reviews") or {}).get("safety", {}).get("safety_pass")


def _quality_pass(state: GraphState) -> bool | None:
    return (state.get("reviews") or {}).get("critic", {}).get("quality_pass")


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

    # core pipeline
    g.add_edge("intake", "drafter")
    g.add_edge("drafter", "safety")
    g.add_edge("safety", "critic")
    g.add_edge("critic", "supervisor")

    def route_after_supervisor(state: GraphState) -> str:
        """
        Non-trivial autonomy:
        - If safety/quality fail => must revise (loop)
        - Otherwise follow supervisor action
        - Hard stop after max iterations => finalize (best-effort)
        """
        it = _iteration(state)
        mx = _max_iterations(state)

        # Stop condition: prevent infinite loops
        if it >= mx:
            return "finalize"

        sp = _safety_pass(state)
        qp = _quality_pass(state)

        # If any reviewer explicitly failed -> revise
        if sp is False or qp is False:
            return "drafter"

        action = (state.get("supervisor") or {}).get("action", "revise")
        return "finalize" if action == "finalize" else "drafter"

    g.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {"finalize": "finalize", "drafter": "drafter"},
    )

    # human gate AFTER finalize (only if required)
    def route_after_finalize(state: GraphState) -> str:
        return "human_review" if bool(state.get("require_human_approval")) else "end"

    g.add_conditional_edges(
        "finalize",
        route_after_finalize,
        {"human_review": "human_review", "end": END},
    )

    # approval routing
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

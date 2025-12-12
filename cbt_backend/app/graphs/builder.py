from __future__ import annotations

from langgraph.graph import StateGraph, END

from app.graphs.state import GraphState
from app.graphs.nodes.intake import intake_node
from app.graphs.nodes.finalize import finalize_node


def build_graph():
    g = StateGraph(GraphState)

    g.add_node("intake", intake_node)
    g.add_node("finalize", finalize_node)

    g.set_entry_point("intake")
    g.add_edge("intake", "finalize")
    g.add_edge("finalize", END)

    return g

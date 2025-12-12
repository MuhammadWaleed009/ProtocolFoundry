from __future__ import annotations

from typing import Any, Dict

from app.graphs.builder import build_graph
from app.persistence.checkpointer import checkpointer_manager


def run_once(thread_id: str, input_text: str) -> Dict[str, Any]:
    graph = build_graph().compile(checkpointer=checkpointer_manager.get())

    config = {"configurable": {"thread_id": thread_id}}

    # This will create the first checkpoint for this thread_id
    result = graph.invoke({"input_text": input_text}, config=config)
    return result

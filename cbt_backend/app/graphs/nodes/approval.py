from datetime import datetime
from app.graphs.state import GraphState


def await_human_approval(state: GraphState) -> GraphState:
    """
    HARD HALT NODE

    If the session is not approved yet, the graph will stop here.
    LangGraph will checkpoint this state and wait.
    """

    # If not approved yet → halt execution
    if not state.get("approved", False):
        state["awaiting_approval"] = True
        state["updated_at"] = datetime.utcnow().isoformat()
        return state

    # If approved → allow graph to continue
    state["awaiting_approval"] = False
    state["updated_at"] = datetime.utcnow().isoformat()
    return state

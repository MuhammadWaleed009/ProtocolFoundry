from __future__ import annotations
from typing import Any, TypedDict

class GraphState(TypedDict, total=False):
    input_text: str
    require_human_approval: bool

    request: dict
    drafts: list[dict]
    reviews: dict
    supervisor: dict
    final: dict

    status: str

    # Existing human-gate fields
    halt_payload: dict
    human_response: dict

    # NEW
    human_feedback: str | None

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class GraphState(TypedDict, total=False):
    # Core
    input_text: str

    # Normalized request
    request: Dict[str, Any]

    # Draft versions (later)
    drafts: List[Dict[str, Any]]

    # Final result (later)
    final: Dict[str, Any]

    # Metrics (later)
    metrics: Dict[str, Any]

    # Status flags
    status: str  # RUNNING | HALTED | COMPLETED | FAILED

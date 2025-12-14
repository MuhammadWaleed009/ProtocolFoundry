from __future__ import annotations

from typing import Any, Literal, TypedDict, Annotated


# ----------------------------
# Reducers (LangGraph)
# ----------------------------
def _append_list(a: Any, b: Any) -> list:
    a_list = a if isinstance(a, list) else []
    b_list = b if isinstance(b, list) else []
    return a_list + b_list


def _merge_dict(a: Any, b: Any) -> dict:
    a_dict = a if isinstance(a, dict) else {}
    b_dict = b if isinstance(b, dict) else {}
    return {**a_dict, **b_dict}


def _merge_scratchpad(a: Any, b: Any) -> dict:
    """
    scratchpad is a dict of lists[str]. We want to append per-key safely.
    Node returns only delta like {"safety": ["..."]}.
    """
    out: dict = dict(a) if isinstance(a, dict) else {}
    delta: dict = b if isinstance(b, dict) else {}
    for k, v in delta.items():
        prev = out.get(k)
        prev_list = prev if isinstance(prev, list) else []
        if isinstance(v, list):
            # avoid duplicate adjacent entries to keep UI tidy
            merged = list(prev_list)
            for item in v:
                if merged and merged[-1] == item:
                    continue
                merged.append(item)
            out[k] = merged
        else:
            if not (prev_list and prev_list[-1] == v):
                out[k] = prev_list + [str(v)]
            else:
                out[k] = prev_list
    return out


def _replace(_a: Any, b: Any) -> Any:
    return b


# ----------------------------
# Types
# ----------------------------
class Draft(TypedDict, total=False):
    version: int
    created_at: str
    markdown: str
    data: dict
    source: str
    notes: str


class SafetyReview(TypedDict, total=False):
    safety_pass: bool
    safety_score: float
    flags: list[str]
    safety_note: str
    required_changes: list[str]


class CriticReview(TypedDict, total=False):
    quality_pass: bool
    quality_score: float
    issues: list[str]
    suggestions: list[str]


class Reviews(TypedDict, total=False):
    safety: SafetyReview
    critic: CriticReview


class SupervisorDecision(TypedDict, total=False):
    action: Literal["finalize", "revise"]
    rationale: str


class FinalPayload(TypedDict, total=False):
    created_at: str
    markdown: str
    data: dict
    reviews: Reviews
    supervisor: SupervisorDecision
    human_edit: dict


class TraceItem(TypedDict, total=False):
    ts: str
    node: str
    summary: str


class Scratchpad(TypedDict, total=False):
    intake: list[str]
    drafter: list[str]
    safety: list[str]
    critic: list[str]
    supervisor: list[str]
    finalize: list[str]
    human: list[str]


class Metrics(TypedDict, total=False):
    iteration: int
    max_iterations: int
    safety_score: float
    quality_score: float


class GraphState(TypedDict, total=False):
    # inputs
    input_text: Annotated[str, _replace]
    require_human_approval: Annotated[bool, _replace]

    # blackboard
    request: Annotated[dict, _merge_dict]
    drafts: Annotated[list[Draft], _append_list]
    reviews: Annotated[Reviews, _merge_dict]
    supervisor: Annotated[SupervisorDecision, _replace]
    final: Annotated[FinalPayload, _replace]

    scratchpad: Annotated[Scratchpad, _merge_scratchpad]
    metrics: Annotated[Metrics, _merge_dict]
    trace: Annotated[list[TraceItem], _append_list]

    current_node: Annotated[str, _replace]
    status: Annotated[str, _replace]

    # intent guard
    is_cbt_relevant: Annotated[bool, _replace]

    # human gate
    halt_payload: Annotated[dict | None, _replace]
    human_response: Annotated[dict | None, _replace]
    human_feedback: Annotated[str | None, _replace]

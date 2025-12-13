from __future__ import annotations

from datetime import datetime, timezone
from app.graphs.state import GraphState
from app.graphs.prompts import DRAFTER_SYSTEM
from app.services.llm import chat_json


def drafter_node(state: GraphState) -> dict:
    text = (state.get("input_text") or "").strip()
    reviews = state.get("reviews") or {}
    metrics = state.get("metrics") or {}
    iteration = int(metrics.get("iteration", 1))

    critic_notes = reviews.get("critic") or {}
    safety_notes = reviews.get("safety") or {}

    human_feedback = state.get("human_feedback")
    feedback_block = ""
    if human_feedback:
        feedback_block = (
            "\nHUMAN REVIEWER FEEDBACK (MUST ADDRESS EXACTLY):\n"
            f"- {human_feedback}\n"
        )

    drafts = state.get("drafts") or []
    last_markdown = ""
    if drafts:
        last_markdown = drafts[-1].get("markdown", "") or ""

    prev_block = ""
    if last_markdown:
        prev_block = (
            "\nPREVIOUS DRAFT (REVISE THIS, DO NOT START FROM SCRATCH):\n"
            f"{last_markdown}\n"
        )

    user = f"""
User situation:
{text}

Iteration: {iteration}
{feedback_block}

Incorporate reviewer notes if present:
Safety required_changes: {safety_notes.get("required_changes")}
Critic suggestions: {critic_notes.get("suggestions")}
Critic issues: {critic_notes.get("issues")}
{prev_block}
""".strip()

    out = chat_json(DRAFTER_SYSTEM, user)

    drafts.append(
        {
            "version": len(drafts) + 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "markdown": out.get("markdown", ""),
            "data": out.get("data", {}),
        }
    )

    metrics["iteration"] = iteration + 1

    return {
        "drafts": drafts,
        "metrics": metrics,
        "human_feedback": None,  # clear after using once
        "status": "RUNNING",
    }

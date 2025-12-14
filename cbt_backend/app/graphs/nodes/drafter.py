from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.graphs.prompts import DRAFTER_SYSTEM
from app.graphs.state import GraphState
from app.services.llm import chat_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _truncate(s: str, n: int = 2500) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else (s[: n - 20] + "\n…(truncated)…\n" + s[-20:])


def _safe_str_list(x: Any) -> list[str]:
    if not isinstance(x, list):
        return []
    out: list[str] = []
    for v in x:
        if isinstance(v, str):
            t = v.strip()
            if t:
                out.append(t)
        else:
            out.append(str(v))
    return out


def _fallback_markdown(title: str) -> str:
    return (
        f"# {title or 'CBT Exercise'}\n\n"
        "## Goal\n"
        "- Create a short, practical CBT exercise.\n\n"
        "## Steps\n"
        "1. Identify the situation and the automatic thought.\n"
        "2. Rate belief (0–100%).\n"
        "3. Evidence for vs evidence against.\n"
        "4. Create a balanced thought.\n"
        "5. Choose one small action to try.\n\n"
        "## Reflection prompts\n"
        "- What was the strongest emotion and why?\n"
        "- What alternative explanation fits the facts?\n"
        "- What’s one small next step?\n\n"
        "## Safety note\n"
        "If you feel unsafe or at risk of harm, seek immediate local help.\n"
    )


def drafter_node(state: GraphState) -> dict:
    ts = _now_iso()

    text = (state.get("input_text") or "").strip()
    reviews = state.get("reviews") or {}
    metrics_in = state.get("metrics") or {}
    human_feedback = state.get("human_feedback")

    prev_drafts = state.get("drafts") or []
    prev_md = (prev_drafts[-1].get("markdown") or "") if prev_drafts else ""

    # iteration counter
    iteration = _coerce_int(metrics_in.get("iteration"), 0) + 1

    # pull “revision guidance” from reviews (safe + concise)
    safety = (reviews.get("safety") or {}) if isinstance(reviews.get("safety"), dict) else {}
    critic = (reviews.get("critic") or {}) if isinstance(reviews.get("critic"), dict) else {}

    safety_required = _safe_str_list(safety.get("required_changes"))
    critic_issues = _safe_str_list(critic.get("issues"))
    critic_suggestions = _safe_str_list(critic.get("suggestions"))

    prev_block = f"\n\nPrevious draft (for revision):\n{_truncate(prev_md)}\n" if prev_md else ""
    feedback_block = f"\n\nHuman feedback to incorporate:\n{human_feedback}\n" if human_feedback else ""

    safety_block = ""
    if safety_required:
        safety_block = "\n\nSafety required changes (must address):\n- " + "\n- ".join(safety_required[:10]) + "\n"

    critic_block = ""
    if critic_issues or critic_suggestions:
        parts: list[str] = []
        if critic_issues:
            parts.append("Critic issues:\n- " + "\n- ".join(critic_issues[:10]))
        if critic_suggestions:
            parts.append("Critic suggestions:\n- " + "\n- ".join(critic_suggestions[:10]))
        critic_block = "\n\n" + "\n\n".join(parts) + "\n"

    user_prompt = (
        "Create a CBT protocol exercise as structured Markdown.\n\n"
        f"User request:\n{text}\n\n"
        f"Iteration: {iteration}\n"
        f"{prev_block}{feedback_block}{safety_block}{critic_block}\n"
        "Return ONLY valid JSON with: {markdown: string, data: object}.\n"
        "- markdown must include: title, goal, steps, reflection prompts, safety note.\n"
        "- data must include: title, goal, steps[], reflection_prompts[], safety_note.\n"
        "- Keep it practical, clear, and safe.\n"
    )

    resp = chat_json(system=DRAFTER_SYSTEM, user=user_prompt) or {}

    markdown = resp.get("markdown") or resp.get("final_markdown") or ""
    if not isinstance(markdown, str):
        markdown = str(markdown)

    data = resp.get("data")
    if not isinstance(data, dict):
        data = {}

    # defensive fallback
    if not markdown.strip():
        title = data.get("title") if isinstance(data.get("title"), str) else "CBT Exercise"
        markdown = _fallback_markdown(title)

    draft = {
        "version": iteration,
        "created_at": ts,
        "markdown": markdown.strip(),
        "data": data,
        "source": "drafter",
        "notes": "Revised using human feedback."
        if human_feedback
        else ("Revised using reviews." if prev_md else "Initial draft."),
    }

    # SAFE progress artifacts for UI (not chain-of-thought)
    trace_item = {"ts": ts, "node": "drafter", "summary": f"Draft v{iteration} generated."}
    scratch_note = f"Draft v{iteration} created" + (" (incorporated human feedback)" if human_feedback else "")

    # metrics delta (reducers will MERGE this, not replace the whole dict)
    metrics_out = {
        "iteration": iteration,
        "updated_at": ts,
        "last_node": "drafter",
    }

    # reducers will append/merge these fields
    return {
        "current_node": "drafter",
        "status": "RUNNING",
        "metrics": metrics_out,
        "drafts": [draft],
        "trace": [trace_item],
        "scratchpad": {"drafter": [scratch_note]},
        "human_feedback": None,  # clear after incorporating
    }

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.graphs.prompts import SAFETY_SYSTEM
from app.graphs.state import GraphState
from app.services.llm import chat_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(x: Any, default: float) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _safe_str_list(x: Any) -> list[str]:
    if not isinstance(x, list):
        return []
    out: list[str] = []
    for v in x:
        if isinstance(v, str):
            s = v.strip()
            if s:
                out.append(s)
        else:
            out.append(str(v))
    return out


def _truncate(s: str, n: int = 2500) -> str:
    s = s or ""
    return s if len(s) <= n else (s[: n - 20] + "\n…(truncated)…\n" + s[-20:])


def safety_node(state: GraphState) -> dict:
    ts = _now_iso()

    text = (state.get("input_text") or "").strip()
    drafts = state.get("drafts") or []
    metrics_in = state.get("metrics") or {}

    # Ensure we don't wipe other reviews by replacing the whole "reviews" object
    # (GraphState uses _merge_dict for reviews)
    if not drafts:
        safety = {
            "safety_pass": False,
            "safety_score": 0.0,
            "flags": ["missing_draft"],
            "required_changes": ["No draft available to review."],
            "safety_note": "Draft was missing; please generate a draft before running safety.",
        }

        summary = "Safety check failed: missing draft."

        return {
            "current_node": "safety",
            "status": "RUNNING",
            "reviews": {"safety": safety},
            "metrics": {
                **metrics_in,
                "safety_score": 0.0,
                "last_node": "safety",
                "updated_at": ts,
            },
            "trace": [{"ts": ts, "node": "safety", "summary": summary}],
            "scratchpad": {"safety": ["No draft found — safety cannot run."]},
        }

    md = (drafts[-1].get("markdown") or "").strip()

    user_prompt = (
        f"User request:\n{text}\n\n"
        f"Draft to review:\n{_truncate(md)}\n\n"
        "Return ONLY valid JSON with:\n"
        "{safety_pass: bool, safety_score: number, flags: string[], required_changes: string[], safety_note: string}\n"
    )

    resp = chat_json(system=SAFETY_SYSTEM, user=user_prompt) or {}

    safety_pass = bool(resp.get("safety_pass", True))
    safety_score = _safe_float(resp.get("safety_score"), 1.0 if safety_pass else 0.0)

    flags = _safe_str_list(resp.get("flags"))
    required_changes = _safe_str_list(resp.get("required_changes"))

    safety_note = resp.get("safety_note")
    if not isinstance(safety_note, str):
        safety_note = ""

    safety = {
        "safety_pass": safety_pass,
        "safety_score": safety_score,
        "flags": flags,
        "required_changes": required_changes,
        "safety_note": safety_note.strip(),
    }

    # Public, UI-safe progress line
    if safety_pass:
        summary = "Safety passed ✅"
    else:
        summary = f"Safety needs changes ⚠️{f' ({len(required_changes)})' if required_changes else ''}"

    return {
        "current_node": "safety",
        "status": "RUNNING",
        # merge into existing reviews
        "reviews": {"safety": safety},
        "metrics": {
            **metrics_in,
            "safety_score": safety_score,
            "last_node": "safety",
            "updated_at": ts,
        },
        # append-only (reducer caps it)
        "trace": [{"ts": ts, "node": "safety", "summary": summary}],
        # append into scratchpad.safety
        "scratchpad": {"safety": [summary]},
    }

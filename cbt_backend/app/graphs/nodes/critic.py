from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.graphs.prompts import CRITIC_SYSTEM
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


def critic_node(state: GraphState) -> dict:
    ts = _now_iso()

    text = (state.get("input_text") or "").strip()
    drafts = state.get("drafts") or []
    metrics_in = state.get("metrics") or {}

    if not drafts:
        critic = {
            "quality_pass": False,
            "quality_score": 0.0,
            "issues": ["missing_draft"],
            "suggestions": ["No draft available to review."],
        }
        summary = "Quality review failed: missing draft."

        return {
            "current_node": "critic",
            "status": "RUNNING",
            # merge into existing reviews
            "reviews": {"critic": critic},
            "metrics": {
                **metrics_in,
                "quality_score": 0.0,
                "last_node": "critic",
                "updated_at": ts,
            },
            "trace": [{"ts": ts, "node": "critic", "summary": summary}],
            "scratchpad": {"critic": ["No draft found — critic cannot run."]},
        }

    md = (drafts[-1].get("markdown") or "").strip()

    user_prompt = (
        f"User request:\n{text}\n\n"
        f"Draft to review:\n{_truncate(md)}\n\n"
        "Return ONLY valid JSON with:\n"
        "{quality_pass: bool, quality_score: number, issues: string[], suggestions: string[]}\n"
    )

    resp = chat_json(system=CRITIC_SYSTEM, user=user_prompt) or {}

    quality_pass = bool(resp.get("quality_pass", True))
    quality_score = _safe_float(resp.get("quality_score"), 1.0 if quality_pass else 0.0)

    issues = _safe_str_list(resp.get("issues"))
    suggestions = _safe_str_list(resp.get("suggestions"))

    critic = {
        "quality_pass": quality_pass,
        "quality_score": quality_score,
        "issues": issues,
        "suggestions": suggestions,
    }

    if quality_pass:
        summary = f"Quality passed ✅ (score {quality_score:.2f})"
    else:
        summary = f"Quality needs work ⚠️{f' ({len(issues)} issues)' if issues else ''}"

    return {
        "current_node": "critic",
        "status": "RUNNING",
        "reviews": {"critic": critic},
        "metrics": {
            **metrics_in,
            "quality_score": quality_score,
            "last_node": "critic",
            "updated_at": ts,
        },
        "trace": [{"ts": ts, "node": "critic", "summary": summary}],
        "scratchpad": {"critic": [summary]},
    }

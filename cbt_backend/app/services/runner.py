from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi.encoders import jsonable_encoder
from langgraph.types import Command

from app.graphs.builder import build_graph
from app.persistence.checkpointer import checkpointer_manager
from app.persistence.run_store import (
    create_run,
    get_latest_halted_run,
    log_event,
    update_run_from_state,
    set_pending_interrupt,
)
from app.services.websocket_manager import ws_manager


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _interrupts_to_json(update: dict) -> list[dict]:
    intrs = update.get("__interrupt__") or ()
    out: list[dict] = []
    for intr in intrs:
        out.append(
            {
                "value": intr.value,
                "resumable": getattr(intr, "resumable", True),
                "ns": getattr(intr, "ns", []),
            }
        )
    return out


def _read_latest_state(thread_id: str) -> dict | None:
    checkpointer = checkpointer_manager.get()
    config = {"configurable": {"thread_id": thread_id}}
    ct = checkpointer.get_tuple(config)
    if not ct:
        return None
    checkpoint = ct.checkpoint or {}
    return checkpoint.get("channel_values")  # clean state snapshot


def _node_name_from_update(update: dict) -> str | None:
    # update is typically {"node_name": {...}} (stream_mode="updates")
    if not isinstance(update, dict):
        return None
    for k in update.keys():
        if k != "__interrupt__":
            return k
    return None

def _safe_first_str(x: Any, max_len: int = 140) -> str | None:
    if isinstance(x, str):
        s = x.strip()
        return s[:max_len] if s else None
    return None

def _public_summary(node: str, payload: Any) -> str:
    # Keep this “public trace” only: stage + safe signals.
    try:
        if node == "intake":
            return "Parsing request…"

        if node == "drafter":
            return "Generating draft…"

        if node == "safety":
            sp = None
            req_count = None
            if isinstance(payload, dict):
                safety = (payload.get("reviews") or {}).get("safety") or payload.get("safety")
                if isinstance(safety, dict):
                    sp = safety.get("safety_pass")
                    req = safety.get("required_changes")
                    if isinstance(req, list):
                        req_count = len(req)

            if sp is True:
                return "Safety passed ✅"
            if sp is False:
                return f"Safety needs changes ⚠️{f' ({req_count})' if req_count is not None else ''}"
            return "Running safety checks…"

        if node == "critic":
            qp = None
            score = None
            issues_count = None
            if isinstance(payload, dict):
                critic = (payload.get("reviews") or {}).get("critic") or payload.get("critic")
                if isinstance(critic, dict):
                    qp = critic.get("quality_pass")
                    score = critic.get("quality_score")
                    issues = critic.get("issues")
                    if isinstance(issues, list):
                        issues_count = len(issues)

            if qp is True:
                return f"Quality passed ✅{f' (score {score})' if isinstance(score, (int, float)) else ''}"
            if qp is False:
                return f"Quality needs work ⚠️{f' ({issues_count} issues)' if issues_count is not None else ''}"
            return "Reviewing quality…"

        if node == "supervisor":
            action = None
            rationale = None
            if isinstance(payload, dict):
                sup = payload.get("supervisor") or payload
                if isinstance(sup, dict):
                    action = sup.get("action")
                    rationale = _safe_first_str(sup.get("rationale"))
            if action:
                return f"Decision: {action}{f' — {rationale}' if rationale else ''}"
            return "Deciding finalize vs revise…"

        if node == "finalize":
            return "Finalizing output…"

        if node == "human_review":
            return "Waiting for your approval…"

        return f"Working on {node}…"
    except Exception:
        return f"Working on {node}…"


def _safe_update(update: dict) -> dict:
    """
    Ensure the WS payload is JSON-serializable.
    This prevents ws.send_json from failing on weird objects.
    """
    try:
        return jsonable_encoder(update)
    except Exception:
        # fallback: stringify the update (still useful for debugging)
        return {"_non_serializable_update": str(update)}


async def run_with_ws(thread_id: str, input_text: str, require_human_approval: bool) -> Dict[str, Any]:
    graph = build_graph().compile(checkpointer=checkpointer_manager.get())
    config = {"configurable": {"thread_id": thread_id}}

    run_id = create_run(thread_id=thread_id, input_text=input_text, require_human_approval=require_human_approval)

    seq = 0
    seq += 1
    await ws_manager.broadcast(thread_id, {"type": "run_started", "ts": _now_iso(), "seq": seq, "run_id": run_id})
    log_event(run_id, "run_started", payload={"require_human_approval": require_human_approval}, seq=seq)

    # If we are starting a new run, clear any stale pending interrupt
    set_pending_interrupt(run_id, None)

    initial = {"input_text": input_text, "require_human_approval": require_human_approval}

    try:
        for update in graph.stream(initial, config, stream_mode="updates"):
            seq += 1

            # HALT
            if "__interrupt__" in update:
                intrs = _interrupts_to_json(update)

                # ✅ persist pending interrupt on HALTED
                set_pending_interrupt(run_id, {"interrupts": intrs})

                await ws_manager.broadcast(
                    thread_id,
                    {"type": "halt_required", "ts": _now_iso(), "seq": seq, "run_id": run_id, "interrupts": intrs},
                )
                log_event(run_id, "halt_required", payload={"interrupts": intrs}, seq=seq)

                state = _read_latest_state(thread_id)
                update_run_from_state(run_id, status="HALTED", state=state)
                return {"run_id": run_id, "status": "HALTED", "interrupts": intrs}

            # ✅ lightweight agent/node tracking
            node = _node_name_from_update(update)
            if node:
                payload = update.get(node) if isinstance(update, dict) else None
                summary = _public_summary(node, payload)

                await ws_manager.broadcast(
                    thread_id,
                    {
                        "type": "node_update",
                        "ts": _now_iso(),
                        "seq": seq,
                        "run_id": run_id,
                        "node": node,
                        "summary": summary,
                    },
                )
                log_event(run_id, "node_update", payload={"node": node, "summary": summary}, seq=seq)

            # richer payload (safe-encoded)
            await ws_manager.broadcast(
                thread_id,
                {"type": "state_update", "ts": _now_iso(), "seq": seq, "run_id": run_id, "update": _safe_update(update)},
            )

        # COMPLETED
        seq += 1
        await ws_manager.broadcast(thread_id, {"type": "run_completed", "ts": _now_iso(), "seq": seq, "run_id": run_id})
        log_event(run_id, "run_completed", payload=None, seq=seq)

        # ✅ clear pending interrupt on completion
        set_pending_interrupt(run_id, None)

        state = _read_latest_state(thread_id)
        update_run_from_state(run_id, status="COMPLETED", state=state)
        return {"run_id": run_id, "status": "COMPLETED"}

    except Exception as e:
        seq += 1
        await ws_manager.broadcast(
            thread_id,
            {"type": "run_failed", "ts": _now_iso(), "seq": seq, "run_id": run_id, "error": str(e)},
        )
        log_event(run_id, "run_failed", payload={"error": str(e)}, seq=seq)

        # ✅ clear pending interrupt on failure too
        set_pending_interrupt(run_id, None)

        state = _read_latest_state(thread_id)
        update_run_from_state(run_id, status="FAILED", state=state, error=str(e))
        raise


async def resume_with_ws(
    thread_id: str,
    approved: bool,
    edited_text: str | None = None,
    feedback: str | None = None,
    run_id: str | None = None,
) -> Dict[str, Any]:
    graph = build_graph().compile(checkpointer=checkpointer_manager.get())
    config = {"configurable": {"thread_id": thread_id}}

    if run_id is None:
        latest = get_latest_halted_run(thread_id)
        run_id = latest["run_id"] if latest else None

    if run_id is None:
        # route_sessions should prevent this; keep it defensive
        raise ValueError("No halted run found to resume for this thread")

    seq = 0
    seq += 1
    await ws_manager.broadcast(thread_id, {"type": "resume_started", "ts": _now_iso(), "seq": seq, "run_id": run_id})
    log_event(run_id, "resume_started", payload={"approved": approved}, seq=seq)

    # ✅ clear old pending interrupt as soon as we attempt a resume
    set_pending_interrupt(run_id, None)

    cmd = Command(resume={"approved": approved, "edited_text": edited_text, "feedback": feedback})

    try:
        for update in graph.stream(cmd, config, stream_mode="updates"):
            seq += 1

            # HALT again
            if "__interrupt__" in update:
                intrs = _interrupts_to_json(update)

                # ✅ persist pending interrupt on HALTED (resume path too)
                set_pending_interrupt(run_id, {"interrupts": intrs})

                await ws_manager.broadcast(
                    thread_id,
                    {"type": "halt_required", "ts": _now_iso(), "seq": seq, "run_id": run_id, "interrupts": intrs},
                )
                log_event(run_id, "halt_required", payload={"interrupts": intrs}, seq=seq)

                state = _read_latest_state(thread_id)
                update_run_from_state(run_id, status="HALTED", state=state)
                return {"run_id": run_id, "status": "HALTED", "interrupts": intrs}

            # ✅ node_update for resume path
            node = _node_name_from_update(update)
            if node:
                payload = update.get(node) if isinstance(update, dict) else None
                summary = _public_summary(node, payload)

                await ws_manager.broadcast(
                    thread_id,
                    {
                        "type": "node_update",
                        "ts": _now_iso(),
                        "seq": seq,
                        "run_id": run_id,
                        "node": node,
                        "summary": summary,
                    },
                )
                log_event(run_id, "node_update", payload={"node": node, "summary": summary}, seq=seq)

            await ws_manager.broadcast(
                thread_id,
                {"type": "state_update", "ts": _now_iso(), "seq": seq, "run_id": run_id, "update": _safe_update(update)},
            )

        # COMPLETED
        seq += 1
        await ws_manager.broadcast(thread_id, {"type": "resume_completed", "ts": _now_iso(), "seq": seq, "run_id": run_id})
        log_event(run_id, "resume_completed", payload=None, seq=seq)

        # ✅ clear pending interrupt on completion
        set_pending_interrupt(run_id, None)

        state = _read_latest_state(thread_id)
        update_run_from_state(run_id, status="COMPLETED", state=state)
        return {"run_id": run_id, "status": "COMPLETED"}

    except Exception as e:
        seq += 1
        await ws_manager.broadcast(
            thread_id,
            {"type": "resume_failed", "ts": _now_iso(), "seq": seq, "run_id": run_id, "error": str(e)},
        )
        log_event(run_id, "resume_failed", payload={"error": str(e)}, seq=seq)

        # ✅ clear pending interrupt on failure
        set_pending_interrupt(run_id, None)

        state = _read_latest_state(thread_id)
        update_run_from_state(run_id, status="FAILED", state=state, error=str(e))
        raise

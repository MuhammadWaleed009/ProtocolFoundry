from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from langgraph.types import Command

from app.graphs.builder import build_graph
from app.persistence.checkpointer import checkpointer_manager
from app.persistence.run_store import create_run, get_latest_halted_run, log_event, update_run_from_state
from app.services.websocket_manager import ws_manager
from app.persistence.run_store import set_pending_interrupt


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


async def run_with_ws(thread_id: str, input_text: str, require_human_approval: bool) -> Dict[str, Any]:
    graph = build_graph().compile(checkpointer=checkpointer_manager.get())
    config = {"configurable": {"thread_id": thread_id}}

    run_id = create_run(thread_id=thread_id, input_text=input_text, require_human_approval=require_human_approval)

    seq = 0
    seq += 1
    msg = {"type": "run_started", "ts": _now_iso(), "seq": seq, "run_id": run_id}
    await ws_manager.broadcast(thread_id, msg)
    log_event(run_id, "run_started", payload={"require_human_approval": require_human_approval}, seq=seq)

    initial = {"input_text": input_text, "require_human_approval": require_human_approval}

    try:
        for update in graph.stream(initial, config, stream_mode="updates"):
            seq += 1

            if "__interrupt__" in update:
                intrs = _interrupts_to_json(update)
                set_pending_interrupt(run_id, {"interrupts": intrs})

                await ws_manager.broadcast(
                    thread_id,
                    {"type": "halt_required", "ts": _now_iso(), "seq": seq, "run_id": run_id, "interrupts": intrs},
                )
                log_event(run_id, "halt_required", payload={"interrupts": intrs}, seq=seq)

                state = _read_latest_state(thread_id)
                update_run_from_state(run_id, status="HALTED", state=state)
                return {"run_id": run_id, "status": "HALTED", "interrupts": intrs}

            await ws_manager.broadcast(thread_id, {"type": "state_update", "ts": _now_iso(), "seq": seq, "run_id": run_id, "update": update})
            # log a lightweight event (node name only)
            node = next(iter(update.keys()), None)
            if node:
                log_event(run_id, "node_update", payload={"node": node}, seq=seq)

        seq += 1
        await ws_manager.broadcast(thread_id, {"type": "run_completed", "ts": _now_iso(), "seq": seq, "run_id": run_id})
        log_event(run_id, "run_completed", payload=None, seq=seq)

        state = _read_latest_state(thread_id)
        update_run_from_state(run_id, status="COMPLETED", state=state)
        return {"run_id": run_id, "status": "COMPLETED"}

    except Exception as e:
        seq += 1
        await ws_manager.broadcast(thread_id, {"type": "run_failed", "ts": _now_iso(), "seq": seq, "run_id": run_id, "error": str(e)})
        log_event(run_id, "run_failed", payload={"error": str(e)}, seq=seq)
        state = _read_latest_state(thread_id)
        update_run_from_state(run_id, status="FAILED", state=state, error=str(e))
        raise


async def resume_with_ws(
    thread_id: str,
    approved: bool,
    edited_text: str | None = None,
    feedback: str | None = None,          # ✅ add
    run_id: str | None = None,
) -> Dict[str, Any]:
    graph = build_graph().compile(checkpointer=checkpointer_manager.get())
    config = {"configurable": {"thread_id": thread_id}}

    # If caller didn't provide run_id, resume most recent halted run for this thread
    if run_id is None:
        latest = get_latest_halted_run(thread_id)
        run_id = latest["run_id"] if latest else None

    if run_id is None:
        run_id = "unknown"

    seq = 0
    seq += 1
    await ws_manager.broadcast(thread_id, {"type": "resume_started", "ts": _now_iso(), "seq": seq, "run_id": run_id})

    if run_id != "unknown":
        # ✅ clear pending interrupt once we start resuming
        set_pending_interrupt(run_id, None)

        log_event(
            run_id,
            "resume_started",
            payload={"approved": approved, "has_feedback": bool(feedback), "has_edit": bool(edited_text)},
            seq=seq,
        )

    # ✅ include feedback in resume payload
    cmd = Command(resume={"approved": approved, "edited_text": edited_text, "feedback": feedback})

    try:
        for update in graph.stream(cmd, config, stream_mode="updates"):
            seq += 1

            if "__interrupt__" in update:
                intrs = _interrupts_to_json(update)

                await ws_manager.broadcast(
                    thread_id,
                    {"type": "halt_required", "ts": _now_iso(), "seq": seq, "run_id": run_id, "interrupts": intrs},
                )

                if run_id != "unknown":
                    set_pending_interrupt(run_id, {"interrupts": intrs})
                    log_event(run_id, "halt_required", payload={"interrupts": intrs}, seq=seq)
                    state = _read_latest_state(thread_id)
                    update_run_from_state(run_id, status="HALTED", state=state)

                return {"run_id": run_id, "status": "HALTED", "interrupts": intrs}

            await ws_manager.broadcast(
                thread_id,
                {"type": "state_update", "ts": _now_iso(), "seq": seq, "run_id": run_id, "update": update},
            )

            node = next(iter(update.keys()), None)
            if node and run_id != "unknown":
                log_event(run_id, "node_update", payload={"node": node}, seq=seq)

        seq += 1
        await ws_manager.broadcast(thread_id, {"type": "resume_completed", "ts": _now_iso(), "seq": seq, "run_id": run_id})

        if run_id != "unknown":
            log_event(run_id, "resume_completed", payload=None, seq=seq)
            state = _read_latest_state(thread_id)
            update_run_from_state(run_id, status="COMPLETED", state=state)

        return {"run_id": run_id, "status": "COMPLETED"}

    except Exception as e:
        seq += 1
        await ws_manager.broadcast(thread_id, {"type": "resume_failed", "ts": _now_iso(), "seq": seq, "run_id": run_id, "error": str(e)})

        if run_id != "unknown":
            log_event(run_id, "resume_failed", payload={"error": str(e)}, seq=seq)
            state = _read_latest_state(thread_id)
            update_run_from_state(run_id, status="FAILED", state=state, error=str(e))
        raise


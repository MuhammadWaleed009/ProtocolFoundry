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
    """
    Reads the latest state snapshot from the checkpointer.
    This snapshot already includes reducer merges.
    """
    checkpointer = checkpointer_manager.get()
    config = {"configurable": {"thread_id": thread_id}}
    ct = checkpointer.get_tuple(config)
    if not ct:
        return None
    checkpoint = ct.checkpoint or {}
    return checkpoint.get("channel_values")


def _node_name_from_update(update: dict) -> str | None:
    # update is typically {"node_name": {...}} (stream_mode="updates")
    if not isinstance(update, dict):
        return None
    for k in update.keys():
        if k != "__interrupt__":
            return k
    return None


def _safe_first_str(x: Any, max_len: int = 180) -> str | None:
    if isinstance(x, str):
        s = x.strip()
        return s[:max_len] if s else None
    return None


def _safe_encode(x: Any) -> Any:
    """
    JSON-encodes arbitrary objects safely (FastAPI encoder).
    """
    try:
        return jsonable_encoder(x)
    except Exception:
        return str(x)


def _summary_from_payload(node: str, payload: Any) -> str:
    """
    Prefer the node's own trace summary (safe/public), falling back to a generic message.
    This is how we get "GPT-like" stage updates without chain-of-thought.
    """
    if isinstance(payload, dict):
        tr = payload.get("trace")
        if isinstance(tr, list) and tr:
            first = tr[0]
            if isinstance(first, dict):
                s = first.get("summary")
                if isinstance(s, str) and s.strip():
                    return s.strip()

        # fallback: node-local scratchpad note
        sp = payload.get("scratchpad")
        if isinstance(sp, dict):
            notes = sp.get(node)
            if isinstance(notes, list) and notes:
                s = notes[-1]
                if isinstance(s, str) and s.strip():
                    return s.strip()

    # generic fallback
    mapping = {
        "intake": "Parsing request…",
        "drafter": "Generating draft…",
        "safety": "Running safety checks…",
        "critic": "Reviewing quality…",
        "supervisor": "Making finalize vs revise decision…",
        "finalize": "Finalizing output…",
        "human_review": "Waiting for your approval…",
    }
    return mapping.get(node, f"Working on {node}…")


def _public_signals(node: str, payload: Any) -> dict:
    """
    Machine-readable, safe signals used by the UI to render a live pipeline line.
    These are intentionally shallow and stable.
    """
    if not isinstance(payload, dict):
        return {}

    try:
        if node == "drafter":
            metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
            drafts = payload.get("drafts") if isinstance(payload.get("drafts"), list) else []
            v = None
            if drafts and isinstance(drafts[-1], dict):
                v = drafts[-1].get("version")
            return {
                "iteration": metrics.get("iteration"),
                "draft_version": v,
            }

        if node == "safety":
            reviews = payload.get("reviews")
            safety = None
            if isinstance(reviews, dict):
                safety = reviews.get("safety")
            if isinstance(safety, dict):
                req = safety.get("required_changes")
                return {
                    "safety_pass": safety.get("safety_pass"),
                    "safety_score": safety.get("safety_score"),
                    "required_changes_count": len(req) if isinstance(req, list) else None,
                }
            return {}

        if node == "critic":
            reviews = payload.get("reviews")
            critic = None
            if isinstance(reviews, dict):
                critic = reviews.get("critic")
            if isinstance(critic, dict):
                issues = critic.get("issues")
                return {
                    "quality_pass": critic.get("quality_pass"),
                    "quality_score": critic.get("quality_score"),
                    "issues_count": len(issues) if isinstance(issues, list) else None,
                }
            return {}

        if node == "supervisor":
            sup = payload.get("supervisor")
            if isinstance(sup, dict):
                return {
                    "action": sup.get("action"),
                    "rationale": _safe_first_str(sup.get("rationale"), max_len=240),
                }
            return {}

        if node == "finalize":
            fin = payload.get("final")
            if isinstance(fin, dict):
                md = fin.get("markdown")
                return {"final_ready": bool(isinstance(md, str) and md.strip())}
            return {}

        return {}
    except Exception:
        return {}


def _interrupt_public(intrs: list[dict]) -> tuple[str, str, dict]:
    """
    Extract safe public info from the interrupt payload (human_review payload.public).
    Returns (node, summary, extra).
    """
    try:
        if not intrs:
            return "human_review", "Waiting for your approval…", {}
        v = intrs[0].get("value")
        if not isinstance(v, dict):
            return "human_review", "Waiting for your approval…", {}
        pub = v.get("public")
        if not isinstance(pub, dict):
            return "human_review", "Waiting for your approval…", {}
        node = pub.get("node") if isinstance(pub.get("node"), str) else "human_review"
        summary = pub.get("summary") if isinstance(pub.get("summary"), str) else "Waiting for your approval…"
        extra = {k: pub.get(k) for k in ("ts",) if k in pub}
        return node, summary, extra
    except Exception:
        return "human_review", "Waiting for your approval…", {}


async def run_with_ws(thread_id: str, input_text: str, require_human_approval: bool) -> Dict[str, Any]:
    graph = build_graph().compile(checkpointer=checkpointer_manager.get())
    config = {"configurable": {"thread_id": thread_id}}

    run_id = create_run(thread_id=thread_id, input_text=input_text, require_human_approval=require_human_approval)

    seq = 1
    await ws_manager.broadcast(thread_id, {"type": "run_started", "ts": _now_iso(), "seq": seq, "run_id": run_id})
    log_event(run_id, "run_started", payload={"require_human_approval": require_human_approval}, seq=seq)

    # starting new run => clear stale pending interrupt
    set_pending_interrupt(run_id, None)

    initial = {"input_text": input_text, "require_human_approval": require_human_approval}

    try:
        for update in graph.stream(initial, config, stream_mode="updates"):
            seq += 1

            # HALT (human_review interrupt)
            if "__interrupt__" in update:
                intrs = _interrupts_to_json(update)
                set_pending_interrupt(run_id, {"interrupts": intrs})

                # emit a final node_update for human_review using interrupt.public
                node, summary, extra = _interrupt_public(intrs)
                state_snap = _safe_encode(_read_latest_state(thread_id))

                await ws_manager.broadcast(
                    thread_id,
                    {
                        "type": "node_update",
                        "ts": _now_iso(),
                        "seq": seq,
                        "run_id": run_id,
                        "node": node,
                        "summary": summary,
                        "signals": {"halted": True},
                        "patch": {},
                        "state": state_snap,
                        **extra,
                    },
                )
                log_event(run_id, "node_update", payload={"node": node, "summary": summary, "signals": {"halted": True}}, seq=seq)

                # then emit halt_required
                await ws_manager.broadcast(
                    thread_id,
                    {"type": "halt_required", "ts": _now_iso(), "seq": seq, "run_id": run_id, "interrupts": intrs},
                )
                log_event(run_id, "halt_required", payload={"interrupts": intrs}, seq=seq)

                state = _read_latest_state(thread_id)
                update_run_from_state(run_id, status="HALTED", state=state)
                return {"run_id": run_id, "status": "HALTED", "interrupts": intrs}

            # node_update (summary + signals + patch + state snapshot)
            node = _node_name_from_update(update)
            if node:
                payload = update.get(node) if isinstance(update, dict) else None
                summary = _summary_from_payload(node, payload)
                signals = _public_signals(node, payload)

                # reducers-friendly patch (node output)
                patch = _safe_encode(payload)

                # full state snapshot (already merged by reducers)
                state_snap = _safe_encode(_read_latest_state(thread_id))

                await ws_manager.broadcast(
                    thread_id,
                    {
                        "type": "node_update",
                        "ts": _now_iso(),
                        "seq": seq,
                        "run_id": run_id,
                        "node": node,
                        "summary": summary,
                        "signals": signals,
                        "patch": patch,
                        "state": state_snap,
                    },
                )
                log_event(
                    run_id,
                    "node_update",
                    payload={"node": node, "summary": summary, "signals": signals},
                    seq=seq,
                )

            # state_update (debug)
            await ws_manager.broadcast(
                thread_id,
                {"type": "state_update", "ts": _now_iso(), "seq": seq, "run_id": run_id, "update": _safe_encode(update)},
            )

        # COMPLETED
        seq += 1
        await ws_manager.broadcast(thread_id, {"type": "run_completed", "ts": _now_iso(), "seq": seq, "run_id": run_id})
        log_event(run_id, "run_completed", payload=None, seq=seq)

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
        raise ValueError("No halted run found to resume for this thread")

    seq = 1
    await ws_manager.broadcast(thread_id, {"type": "resume_started", "ts": _now_iso(), "seq": seq, "run_id": run_id})
    log_event(run_id, "resume_started", payload={"approved": approved}, seq=seq)

    # attempting resume => clear old pending interrupt
    set_pending_interrupt(run_id, None)

    cmd = Command(resume={"approved": approved, "edited_text": edited_text, "feedback": feedback})

    try:
        for update in graph.stream(cmd, config, stream_mode="updates"):
            seq += 1

            # HALT again
            if "__interrupt__" in update:
                intrs = _interrupts_to_json(update)
                set_pending_interrupt(run_id, {"interrupts": intrs})

                node, summary, extra = _interrupt_public(intrs)
                state_snap = _safe_encode(_read_latest_state(thread_id))

                await ws_manager.broadcast(
                    thread_id,
                    {
                        "type": "node_update",
                        "ts": _now_iso(),
                        "seq": seq,
                        "run_id": run_id,
                        "node": node,
                        "summary": summary,
                        "signals": {"halted": True},
                        "patch": {},
                        "state": state_snap,
                        **extra,
                    },
                )
                log_event(run_id, "node_update", payload={"node": node, "summary": summary, "signals": {"halted": True}}, seq=seq)

                await ws_manager.broadcast(
                    thread_id,
                    {"type": "halt_required", "ts": _now_iso(), "seq": seq, "run_id": run_id, "interrupts": intrs},
                )
                log_event(run_id, "halt_required", payload={"interrupts": intrs}, seq=seq)

                state = _read_latest_state(thread_id)
                update_run_from_state(run_id, status="HALTED", state=state)
                return {"run_id": run_id, "status": "HALTED", "interrupts": intrs}

            # node_update on resume path too
            node = _node_name_from_update(update)
            if node:
                payload = update.get(node) if isinstance(update, dict) else None
                summary = _summary_from_payload(node, payload)
                signals = _public_signals(node, payload)

                patch = _safe_encode(payload)
                state_snap = _safe_encode(_read_latest_state(thread_id))

                await ws_manager.broadcast(
                    thread_id,
                    {
                        "type": "node_update",
                        "ts": _now_iso(),
                        "seq": seq,
                        "run_id": run_id,
                        "node": node,
                        "summary": summary,
                        "signals": signals,
                        "patch": patch,
                        "state": state_snap,
                    },
                )
                log_event(run_id, "node_update", payload={"node": node, "summary": summary, "signals": signals}, seq=seq)

            await ws_manager.broadcast(
                thread_id,
                {"type": "state_update", "ts": _now_iso(), "seq": seq, "run_id": run_id, "update": _safe_encode(update)},
            )

        # COMPLETED
        seq += 1
        await ws_manager.broadcast(thread_id, {"type": "resume_completed", "ts": _now_iso(), "seq": seq, "run_id": run_id})
        log_event(run_id, "resume_completed", payload=None, seq=seq)

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

        set_pending_interrupt(run_id, None)

        state = _read_latest_state(thread_id)
        update_run_from_state(run_id, status="FAILED", state=state, error=str(e))
        raise

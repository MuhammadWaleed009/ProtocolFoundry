from __future__ import annotations

import uuid
from typing import Any, Dict

from psycopg.types.json import Jsonb

from app.persistence.db import exec_sql, fetch_all, fetch_one


def create_run(
    thread_id: str,
    input_text: str,
    require_human_approval: bool,
) -> str:
    run_id = str(uuid.uuid4())
    exec_sql(
        """
        INSERT INTO runs (run_id, thread_id, status, require_human_approval, input_text)
        VALUES (%s, %s, %s, %s, %s)
        """,
        [run_id, thread_id, "RUNNING", require_human_approval, input_text],
    )
    return run_id


def update_run_from_state(
    run_id: str,
    status: str,
    state: Dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    iteration = None
    safety_score = None
    quality_score = None
    final_markdown = None
    final_data = None
    reviews = None
    supervisor = None
    human_edit = None

    if state:
        metrics = state.get("metrics") or {}
        iteration = metrics.get("iteration")
        safety_score = metrics.get("safety_score")
        quality_score = metrics.get("quality_score")

        final = state.get("final") or {}
        if isinstance(final, dict):
            final_markdown = final.get("markdown")
            final_data = final.get("data")
            reviews = final.get("reviews") or state.get("reviews")
            supervisor = final.get("supervisor") or state.get("supervisor")
            human_edit = final.get("human_edit")

    exec_sql(
        """
        UPDATE runs
        SET
          status=%s,
          updated_at=now(),
          iteration=%s,
          safety_score=%s,
          quality_score=%s,
          final_markdown=%s,
          final_data=%s,
          reviews=%s,
          supervisor=%s,
          human_edit=%s,
          error=%s
        WHERE run_id=%s
        """,
        [
            status,
            iteration,
            safety_score,
            quality_score,
            final_markdown,
            Jsonb(final_data) if final_data is not None else None,
            Jsonb(reviews) if reviews is not None else None,
            Jsonb(supervisor) if supervisor is not None else None,
            Jsonb(human_edit) if human_edit is not None else None,
            error,
            run_id,
        ],
    )


def log_event(run_id: str, event_type: str, payload: dict | None = None, seq: int | None = None) -> None:
    exec_sql(
        """
        INSERT INTO run_events (run_id, seq, event_type, payload)
        VALUES (%s, %s, %s, %s)
        """,
        [run_id, seq, event_type, Jsonb(payload) if payload is not None else None],
    )


def get_latest_run(thread_id: str) -> dict | None:
    # ✅ FIX: filter by thread_id (not run_id)
    return fetch_one(
        """
        SELECT run_id::text AS run_id, thread_id, created_at::text AS created_at, updated_at::text AS updated_at,
               status, require_human_approval, input_text,
               iteration, safety_score, quality_score,
               final_markdown, final_data, reviews, supervisor, human_edit,
               pending_interrupt,
               error
        FROM runs
        WHERE thread_id=%s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [thread_id],
    )


def get_latest_halted_run(thread_id: str) -> dict | None:
    return fetch_one(
        """
        SELECT run_id::text AS run_id
        FROM runs
        WHERE thread_id=%s AND status='HALTED'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [thread_id],
    )


def list_runs(thread_id: str, limit: int = 20) -> list[dict]:
    limit = max(1, min(limit, 200))
    return fetch_all(
        """
        SELECT run_id::text AS run_id,
               created_at::text AS created_at,
               updated_at::text AS updated_at,
               status,
               require_human_approval,
               iteration, safety_score, quality_score
        FROM runs
        WHERE thread_id=%s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        [thread_id, limit],
    )


def get_run(run_id: str) -> dict | None:
    return fetch_one(
        """
        SELECT run_id::text AS run_id, thread_id, created_at::text AS created_at, updated_at::text AS updated_at,
               status, require_human_approval, input_text,
               iteration, safety_score, quality_score,
               final_markdown, final_data, reviews, supervisor, human_edit,
               pending_interrupt,
               error
        FROM runs
        WHERE run_id=%s::uuid
        """,
        [run_id],
    )


def list_run_events(run_id: str, limit: int = 100) -> list[dict]:
    limit = max(1, min(limit, 500))
    return fetch_all(
        """
        SELECT id, ts::text AS ts, seq, event_type, payload
        FROM run_events
        WHERE run_id=%s::uuid
        ORDER BY id ASC
        LIMIT %s
        """,
        [run_id, limit],
    )


def set_pending_interrupt(run_id: str, interrupt_payload: dict | None) -> None:
    if interrupt_payload is None:
        exec_sql(
            "UPDATE runs SET pending_interrupt=NULL, updated_at=now() WHERE run_id=%s",
            [run_id],
        )
        return

    exec_sql(
        "UPDATE runs SET pending_interrupt=%s, updated_at=now() WHERE run_id=%s",
        [Jsonb(interrupt_payload), run_id],
    )

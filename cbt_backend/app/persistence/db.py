from __future__ import annotations

from typing import Any, Sequence

import psycopg
from psycopg.rows import dict_row

from app.core.config import get_settings


def get_conn() -> psycopg.Connection:
    """
    Lightweight helper for short-lived connections (used by REST endpoints).
    For higher throughput we can add a pool later.
    """
    s = get_settings()
    return psycopg.connect(s.DATABASE_URL, row_factory=dict_row)


def exec_sql(sql: str, params: Sequence[Any] | None = None) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
        conn.commit()


def fetch_all(sql: str, params: Sequence[Any] | None = None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            rows = cur.fetchall()
        return list(rows)


def fetch_one(sql: str, params: Sequence[Any] | None = None) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            row = cur.fetchone()
        return row

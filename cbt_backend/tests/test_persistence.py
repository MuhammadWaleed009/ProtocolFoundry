import os

import pytest

from app.main import SESSIONS_TABLE_SQL
from app.persistence.db import exec_sql
from app.persistence.run_store import create_run, get_run, set_pending_interrupt
from app.persistence.run_tables import RUNS_ALTER_SQL, RUNS_TABLE_SQL, RUN_EVENTS_TABLE_SQL
from app.utils.ids import new_thread_id


@pytest.fixture(scope="module")
def db_ready():
    # Skip if no database URL is provided
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set; skipping persistence tests.")

    # Minimal bootstrap to match app startup
    exec_sql(SESSIONS_TABLE_SQL)
    exec_sql(RUNS_TABLE_SQL)
    exec_sql(RUN_EVENTS_TABLE_SQL)
    exec_sql(RUNS_ALTER_SQL)


def test_pending_interrupt_round_trip(db_ready):
    thread_id = new_thread_id()
    exec_sql("INSERT INTO sessions (thread_id, mode) VALUES (%s, %s)", [thread_id, "human_optional"])

    run_id = create_run(thread_id=thread_id, input_text="persistence check", require_human_approval=True)

    payload = {"interrupts": [{"value": {"foo": "bar"}}]}
    set_pending_interrupt(run_id, payload)
    row = get_run(run_id)
    assert row is not None
    assert row["pending_interrupt"]["interrupts"][0]["value"]["foo"] == "bar"

    set_pending_interrupt(run_id, None)
    row2 = get_run(run_id)
    assert row2 is not None
    assert row2["pending_interrupt"] is None

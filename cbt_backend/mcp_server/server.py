from __future__ import annotations

import asyncio
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from app.main import SESSIONS_TABLE_SQL
from app.persistence.checkpointer import checkpointer_manager
from app.persistence.db import exec_sql
from app.persistence.run_store import get_run
from app.persistence.run_tables import RUNS_TABLE_SQL, RUN_EVENTS_TABLE_SQL
from app.services.runner import resume_with_ws, run_with_ws
from app.utils.ids import new_thread_id


# print('running mcp server\n')
server = FastMCP("cerina-protocol-foundry")

_BOOTSTRAPPED = False
_BOOTSTRAP_LOCK = asyncio.Lock()

async def _bootstrap_backend() -> None:
    """
    Ensure LangGraph checkpointer + DB tables exist when MCP server launches.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    async with _BOOTSTRAP_LOCK:
        if _BOOTSTRAPPED:
            return
        checkpointer_manager.start()
        exec_sql(SESSIONS_TABLE_SQL)
        exec_sql(RUNS_TABLE_SQL)
        exec_sql(RUN_EVENTS_TABLE_SQL)
        _BOOTSTRAPPED = True


async def _create_session(mode: str) -> str:
    thread_id = new_thread_id()
    exec_sql("INSERT INTO sessions (thread_id, mode) VALUES (%s, %s)", [thread_id, mode])
    return thread_id

async def _run_foundry(
    prompt: str,
    require_human_approval: bool,
    auto_approve_on_halt: bool,
) -> dict:
    await _bootstrap_backend()

    mode = "human_required" if require_human_approval else "auto"
    thread_id = await _create_session(mode=mode)

    result = await run_with_ws(
        thread_id=thread_id,
        input_text=prompt,
        require_human_approval=require_human_approval,
    )
    run_id = result["run_id"]

    if result["status"] == "HALTED":
        if not auto_approve_on_halt:
            run_row = get_run(run_id) or {}
            interrupts = run_row.get("pending_interrupt")
            return {
                "thread_id": thread_id,
                "run_id": run_id,
                "status": "HALTED",
                "pending_interrupt": interrupts,
                "message": "Run halted awaiting approval. Re-run the MCP tool with auto_approve_on_halt=True to continue.",
            }

        resume = await resume_with_ws(
            thread_id=thread_id,
            run_id=run_id,
            approved=True,
            edited_text=None,
            feedback=None,
        )
        run_id = resume["run_id"]

    row = get_run(run_id) or {}
    final_payload = {
        "thread_id": row.get("thread_id"),
        "run_id": row.get("run_id", run_id),
        "status": row.get("status"),
        "final_markdown": row.get("final_markdown"),
        "final_data": row.get("final_data"),
        "reviews": row.get("reviews"),
        "supervisor": row.get("supervisor"),
        "human_edit": row.get("human_edit"),
        "error": row.get("error"),
    }
    return final_payload


@server.tool()
async def build_cbt_protocol(
    prompt: Annotated[str, "Describe the CBT exercise or protocol you want the foundry to create."],
    require_human_approval: Annotated[
        bool,
        "If true, keep the human-review gate. Set false (default) to fully automate the run."
    ] = False,
    auto_approve_on_halt: Annotated[
        bool,
        "If a run halts waiting for approval, automatically approve it so the workflow can finish."
    ] = True,
) -> dict:
    """
    Entry point exposed to MCP clients. Runs the LangGraph workflow and returns the final run record.
    """
    return await _run_foundry(prompt, require_human_approval, auto_approve_on_halt)


if __name__ == "__main__":
    server.run()

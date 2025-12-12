from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.core.config import get_settings

# These imports are provided by langgraph-checkpoint-* packages
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver


@dataclass
class CheckpointerHandle:
    """
    Holds:
      - checkpointer: the active saver instance used by LangGraph
      - _cm: the context-manager object returned by *.from_conn_string(...)
    """
    checkpointer: Any
    _cm: Any

    def close(self) -> None:
        # Close resources opened by the CM (connections/files)
        try:
            self._cm.__exit__(None, None, None)
        except Exception:
            # We don't want shutdown to crash the server
            pass


class CheckpointerManager:
    def __init__(self) -> None:
        self._handle: Optional[CheckpointerHandle] = None

    def start(self) -> Any:
        if self._handle is not None:
            return self._handle.checkpointer

        s = get_settings()
        backend = s.CHECKPOINT_BACKEND.strip().lower()

        if backend == "postgres":
            # Recommended usage: from_conn_string + setup() first time :contentReference[oaicite:4]{index=4}
            cm = PostgresSaver.from_conn_string(s.DATABASE_URL)
            checkpointer = cm.__enter__()
            # Call .setup() the first time you use Postgres checkpointer :contentReference[oaicite:5]{index=5}
            checkpointer.setup()
            self._handle = CheckpointerHandle(checkpointer=checkpointer, _cm=cm)
            return checkpointer

        if backend == "sqlite":
            Path(s.SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
            cm = SqliteSaver.from_conn_string(s.SQLITE_PATH)
            checkpointer = cm.__enter__()
            checkpointer.setup()
            self._handle = CheckpointerHandle(checkpointer=checkpointer, _cm=cm)
            return checkpointer

        raise ValueError(f"Unsupported CHECKPOINT_BACKEND={s.CHECKPOINT_BACKEND!r} (use 'postgres' or 'sqlite')")

    def get(self) -> Any:
        if self._handle is None:
            raise RuntimeError("CheckpointerManager not started yet")
        return self._handle.checkpointer

    def stop(self) -> None:
        if self._handle is None:
            return
        self._handle.close()
        self._handle = None


checkpointer_manager = CheckpointerManager()

import asyncio
from typing import Any, Dict, Set
from fastapi import WebSocket, WebSocketDisconnect


class WebSocketManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._rooms: Dict[str, Set[WebSocket]] = {}

    async def connect(self, thread_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms.setdefault(thread_id, set()).add(websocket)

    async def disconnect(self, thread_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._rooms.get(thread_id)
            if not conns:
                return
            conns.discard(websocket)
            if not conns:
                self._rooms.pop(thread_id, None)

    async def broadcast(self, thread_id: str, message: Dict[str, Any]) -> None:
        async with self._lock:
            conns = list(self._rooms.get(thread_id, set()))

        if not conns:
            return

        async def _send(ws: WebSocket):
            # Don't let a slow client block "real-time" updates
            await asyncio.wait_for(ws.send_json(message), timeout=1.5)

        results = await asyncio.gather(*(_send(ws) for ws in conns), return_exceptions=True)

        dead: list[WebSocket] = []
        for ws, res in zip(conns, results):
            if isinstance(res, (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError, Exception)):
                dead.append(ws)

        if dead:
            async with self._lock:
                conns2 = self._rooms.get(thread_id)
                if not conns2:
                    return
                for ws in dead:
                    conns2.discard(ws)
                if not conns2:
                    self._rooms.pop(thread_id, None)


ws_manager = WebSocketManager()

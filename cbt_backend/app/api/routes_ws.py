from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.websocket_manager import ws_manager

router = APIRouter(tags=["ws"])

@router.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    await ws_manager.connect(thread_id, websocket)
    try:
        while True:
            msg = await websocket.receive_text()

            # optional keepalive
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(thread_id, websocket)
    except Exception:
        await ws_manager.disconnect(thread_id, websocket)

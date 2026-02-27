from fastapi import APIRouter, WebSocket

from app.services.websocket_manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Simple websocket endpoint used by the frontend dashboard.

    The server currently treats all clients the same and only
    pushes broadcast messages; incoming messages are ignored.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; ignore any client messages for now
            await websocket.receive_text()
    except Exception:
        # Normal disconnects and errors are handled uniformly
        await manager.disconnect(websocket)

import logging
from typing import Any, List

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Simple in-memory websocket connection manager.

    All connected clients receive the same broadcast events.
    This is sufficient for a single-tenant dashboard and keeps
    state entirely in-process.
    """

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "WebSocket connected. Active connections=%d", len(self.active_connections)
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        try:
            self.active_connections.remove(websocket)
        except ValueError:
            # Already removed or unknown connection
            pass
        logger.info(
            "WebSocket disconnected. Active connections=%d",
            len(self.active_connections),
        )

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self.active_connections:
            return
        dead_connections: list[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except WebSocketDisconnect:
                dead_connections.append(connection)
            except Exception:
                # Do not break other listeners if one connection misbehaves
                logger.exception("Error broadcasting websocket message")
        for conn in dead_connections:
            await self.disconnect(conn)


manager = ConnectionManager()


async def broadcast_agent_status(status: dict[str, Any]) -> None:
    """
    Broadcast the current agent status to all connected dashboard clients.
    """
    await manager.broadcast({"type": "agent_status", "status": status})


async def broadcast_suppliers_snapshot(
    oem_id: str, suppliers: list[dict[str, Any]]
) -> None:
    """
    Broadcast a snapshot of suppliers and their latest scores/risks.
    """
    await manager.broadcast(
        {
            "type": "suppliers_snapshot",
            "oemId": oem_id,
            "suppliers": suppliers,
        }
    )


async def broadcast_oem_risk_score(oem_id: str, score: dict[str, Any]) -> None:
    """
    Broadcast the latest OEM-level supply chain risk score with summary.
    """
    await manager.broadcast(
        {
            "type": "oem_risk_score",
            "oemId": oem_id,
            "score": score,
        }
    )

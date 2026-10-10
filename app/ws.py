"""WebSocket endpoint: live message delivery and presence updates."""

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .auth import user_for_token
from .db import connect
from .presence import manager

router = APIRouter()


@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")) -> None:
    # Authenticate via the token query parameter; browsers cannot set custom
    # headers on WebSocket connections.
    conn = connect(websocket.app.state.database_path)
    try:
        user = user_for_token(conn, token)
    finally:
        conn.close()

    if user is None:
        # 4401 is an app-specific "unauthorized" close code. The client treats
        # it as fatal instead of retrying with the same credentials.
        await websocket.accept()
        await websocket.close(code=4401)
        return

    user_id = user["id"]
    await manager.connect(user_id, websocket)
    try:
        await manager.broadcast_all(
            {"type": "presence", "user_id": user_id, "online": True},
            exclude_user_id=user_id,
        )
        while True:
            # The client only listens. Receiving lets the server detect
            # disconnects and clean up presence state.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, websocket)
        if not manager.is_online(user_id):
            try:
                await manager.broadcast_all(
                    {"type": "presence", "user_id": user_id, "online": False},
                    exclude_user_id=user_id,
                )
            except Exception:
                # Presence is best-effort; never fail the disconnect path.
                pass

"""
HackRFComms - Comms Router
POST /api/comms/send  — send a message via OOK TX
WebSocket /ws/comms   — stream received messages to client
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from services import comms_service

router = APIRouter()


class SendRequest(BaseModel):
    message: str


@router.post("/comms/send")
async def send_message(body: SendRequest):
    """Send a message using protocol.send_reliable."""
    result = await comms_service.send_message(body.message)
    return result


@router.websocket("/ws/comms")
async def ws_comms(websocket: WebSocket):
    """
    WebSocket endpoint that continuously polls receive_message()
    and forwards results to the connected client.
    """
    await websocket.accept()
    try:
        while True:
            msg = await comms_service.receive_message()
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass

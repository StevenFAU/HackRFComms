from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import asyncio, sys, os

router = APIRouter()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Per-device async lock to prevent simultaneous operations
_device_locks: dict[str, asyncio.Lock] = {}

def _get_lock(serial: str) -> asyncio.Lock:
    if serial not in _device_locks:
        _device_locks[serial] = asyncio.Lock()
    return _device_locks[serial]


class SendRequest(BaseModel):
    message: str


@router.post("/api/comms/send")
async def send_message(body: SendRequest):
    import protocol, config
    lock = _get_lock(config.TX_SERIAL)
    if lock.locked():
        return {"success": False, "error": "Device busy"}
    async with lock:
        result = await asyncio.to_thread(
            protocol.send_reliable,
            body.message.encode(),
            config.TX_SERIAL,
        )
    return {"success": bool(result), "message": body.message}


@router.websocket("/ws/comms")
async def ws_comms(websocket: WebSocket):
    """Stream received messages — polls receive_and_ack in a loop."""
    await websocket.accept()
    import protocol, config

    try:
        while True:
            # Each iteration is one 3-second listen window
            lock = _get_lock(config.RX_SERIAL)
            if lock.locked():
                await asyncio.sleep(0.5)
                continue

            async with lock:
                data = await asyncio.to_thread(
                    protocol.receive_and_ack,
                    config.RX_SERIAL,
                    3.0,   # listen_duration
                )

            if data:
                await websocket.send_json({
                    "data": data.decode("utf-8", errors="replace"),
                    "timestamp": __import__("datetime").datetime.now().isoformat(),
                })
    except WebSocketDisconnect:
        pass
    except Exception:
        pass

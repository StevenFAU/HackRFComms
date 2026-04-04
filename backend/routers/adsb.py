"""
HackRFComms — ADS-B Router
WS  /ws/adsb              — stream aircraft updates during capture + decode
GET /api/adsb/aircraft    — snapshot of current aircraft state
"""
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.adsb_service import run_capture, aircraft_state

router = APIRouter()


@router.get("/adsb/aircraft")
def get_aircraft():
    """Return current aircraft tracking snapshot."""
    return {"aircraft": list(aircraft_state.values())}


@router.websocket("/ws/adsb")
async def adsb_ws(websocket: WebSocket):
    """
    Client sends one config message to start:
      {"duration": 30}

    Server streams:
      {"type": "status",   "phase": "capturing"|"computing_envelope"|"decoding", ...}
      {"type": "aircraft", "icao": "...", "callsign": "...", "alt": N, "lat": N, "lon": N, ...}
      {"type": "done",     "aircraft_count": N, "msg_count": N}
      {"type": "error",    "message": "..."}
    """
    await websocket.accept()

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
        cfg = json.loads(raw)
        duration = float(cfg.get("duration", 30.0))
        duration = max(5.0, min(duration, 120.0))
    except Exception:
        await websocket.close(code=1003)
        return

    async def send(event: dict):
        try:
            await websocket.send_text(json.dumps(event))
        except Exception:
            pass

    try:
        await run_capture(duration, on_event=send)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await send({"type": "error", "message": str(exc)})

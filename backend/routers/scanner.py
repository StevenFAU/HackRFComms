"""
HackRFComms — Scanner Router
POST /api/scan       — single sweep, returns JSON
WS   /ws/scan        — continuous sweeps, streams JSON per pass
"""
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from services.scanner_service import run_sweep

router = APIRouter()


class ScanRequest(BaseModel):
    start_mhz: int = 900
    end_mhz: int = 930
    fine: bool = False
    num_sweeps: int = 1


@router.post("/scan")
async def scan_once(req: ScanRequest):
    """Run one sweep and return all (freq, power) bins."""
    data = await run_sweep(req.start_mhz, req.end_mhz, req.fine, req.num_sweeps)
    return {"data": data, "start_mhz": req.start_mhz, "end_mhz": req.end_mhz}


@router.websocket("/ws/scan")
async def scan_live(websocket: WebSocket):
    """
    Continuous sweep mode. Client sends one JSON config message:
      {"start_mhz": 88, "end_mhz": 108, "fine": false}
    Server then streams sweep results as fast as hardware allows:
      {"type": "sweep", "data": [...], "sweep_n": N}
    Client sends {"type": "stop"} to end.
    """
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        cfg = json.loads(raw)
        start_mhz = int(cfg.get("start_mhz", 900))
        end_mhz   = int(cfg.get("end_mhz", 930))
        fine       = bool(cfg.get("fine", False))
    except Exception:
        await websocket.close(code=1003)
        return

    sweep_n = 0
    try:
        while True:
            # Check for stop message (non-blocking)
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
                if json.loads(msg).get("type") == "stop":
                    break
            except asyncio.TimeoutError:
                pass

            data = await run_sweep(start_mhz, end_mhz, fine, num_sweeps=1)
            sweep_n += 1
            await websocket.send_text(json.dumps({
                "type": "sweep",
                "sweep_n": sweep_n,
                "data": data,
            }))
    except WebSocketDisconnect:
        pass

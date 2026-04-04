"""
HackRFComms — FM Router
WS  /ws/fm               — streams capture + demod status, returns WAV URL
GET /api/fm/audio/{file} — serve WAV files from iq_dumps/
POST /api/fm/stop        — (no-op: cancel is handled via WS close)
"""
import asyncio
import json
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from services.fm_service import run_tune, IQ_DIR

router = APIRouter()


@router.get("/fm/audio/{filename}")
async def get_audio(filename: str):
    """Serve a WAV file from iq_dumps/."""
    # Sanitise: strip any path components to prevent directory traversal
    filename = os.path.basename(filename)
    path = os.path.join(IQ_DIR, filename)
    if not os.path.exists(path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path, media_type="audio/wav")


@router.websocket("/ws/fm")
async def fm_ws(websocket: WebSocket):
    """
    Client sends one config message:
      {"freq": 93.9, "duration": 10}

    Server streams:
      {"type": "status",   "phase": "capturing"|"demodulating"|"saving", ...}
      {"type": "progress", "phase": "capturing", "elapsed": N, "total": N}
      {"type": "done",     "wav_url": "/api/fm/audio/...", "waveform": [...], "duration_s": N}
      {"type": "cancelled"}
      {"type": "error",    "message": "..."}
    """
    await websocket.accept()

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
        cfg = json.loads(raw)
        freq = float(cfg.get("freq", 93.9))
        duration = float(cfg.get("duration", 10.0))
        duration = max(5.0, min(duration, 60.0))
    except Exception:
        await websocket.close(code=1003)
        return

    cancel_event = asyncio.Event()

    async def send(event: dict):
        try:
            await websocket.send_text(json.dumps(event))
        except Exception:
            cancel_event.set()

    # Listen for stop messages from client in background
    async def watch_client():
        try:
            while True:
                msg = await websocket.receive_text()
                if json.loads(msg).get("type") == "stop":
                    cancel_event.set()
                    break
        except Exception:
            cancel_event.set()

    watcher = asyncio.create_task(watch_client())

    try:
        await run_tune(freq, duration, on_event=send, cancel_event=cancel_event)
    except WebSocketDisconnect:
        cancel_event.set()
    except Exception as exc:
        await send({"type": "error", "message": str(exc)})
    finally:
        watcher.cancel()

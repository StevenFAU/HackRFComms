from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import asyncio, sys, os

router = APIRouter()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

IQ_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "iq_dumps")

_fm_lock = asyncio.Lock()


class TuneRequest(BaseModel):
    freq: float
    duration: float = 10.0


@router.post("/api/fm/tune")
async def tune_station(body: TuneRequest):
    if _fm_lock.locked():
        return JSONResponse({"success": False, "error": "FM capture already in progress"})

    async with _fm_lock:
        import config
        from protocols.fm import run as fm_run

        fm_config = config.PROTOCOLS["fm"].copy()
        await asyncio.to_thread(
            fm_run, fm_config,
            duration=body.duration,
            device=config.RX_SERIAL,
            freq=body.freq,
        )

    wav_name = f"fm_{body.freq}MHz.wav"
    wav_path = os.path.join(IQ_DIR, wav_name)
    if os.path.exists(wav_path):
        return {"success": True, "wav_url": f"/api/fm/audio/{wav_name}", "freq": body.freq, "duration": body.duration}
    return {"success": False, "error": "Demodulation failed — no WAV produced"}


@router.get("/api/fm/audio/{filename}")
async def get_audio(filename: str):
    # Sanitize: no path traversal
    filename = os.path.basename(filename)
    path = os.path.join(IQ_DIR, filename)
    if os.path.exists(path):
        return FileResponse(path, media_type="audio/wav")
    return JSONResponse({"error": "File not found"}, status_code=404)

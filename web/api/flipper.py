from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import asyncio, tempfile, sys, os

router = APIRouter()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

IQ_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "iq_dumps")


class EncodeRequest(BaseModel):
    message: str


@router.post("/api/flipper/encode")
async def encode_message(body: EncodeRequest):
    from tools.flipper_encode import frame_to_sub_data, write_sub_file
    from modulation import build_frame
    from config import CENTER_FREQ

    os.makedirs(IQ_DIR, exist_ok=True)

    def _encode():
        frame = build_frame(body.message.encode())
        durations = frame_to_sub_data(frame)
        repeated = []
        for i in range(5):
            repeated.extend(durations)
            if i < 4:
                repeated.append(-2000)
        path = os.path.join(IQ_DIR, "flipper_tx.sub")
        write_sub_file(repeated, path)
        return frame, durations, repeated

    frame, durations, repeated = await asyncio.to_thread(_encode)

    return {
        "success": True,
        "message": body.message,
        "frame_bytes": len(frame),
        "duration_ms": round(sum(abs(d) for d in repeated) / 1000, 1),
        "download_url": "/api/flipper/download/flipper_tx.sub",
    }


@router.get("/api/flipper/download/{filename}")
async def download_sub(filename: str):
    filename = os.path.basename(filename)
    path = os.path.join(IQ_DIR, filename)
    if os.path.exists(path):
        return FileResponse(path, filename=filename, media_type="application/octet-stream")
    return JSONResponse({"error": "File not found"}, status_code=404)


@router.post("/api/flipper/decode")
async def decode_sub(file: UploadFile = File(...)):
    from tools.flipper_decode import parse_sub_file, durations_to_bits, find_and_decode

    content = await file.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sub")
    tmp.write(content)
    tmp.close()

    try:
        def _decode():
            durations, freq = parse_sub_file(tmp.name)
            bits = durations_to_bits(durations)
            messages = find_and_decode(bits)
            return durations, freq, bits, messages

        durations, freq, bits, messages = await asyncio.to_thread(_decode)

        return {
            "success": len(messages) > 0,
            "messages": messages,
            "unique": list(dict.fromkeys(messages)),
            "duration_count": len(durations),
            "bit_count": len(bits),
            "frequency": freq,
        }
    finally:
        os.unlink(tmp.name)

from fastapi import APIRouter
from fastapi.responses import JSONResponse
import asyncio, os, sys

router = APIRouter()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

IQ_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "iq_dumps")


@router.get("/api/signals/list")
async def list_captures():
    if not os.path.exists(IQ_DIR):
        return {"files": []}
    files = []
    for f in sorted(os.listdir(IQ_DIR)):
        if f.endswith(".iq"):
            path = os.path.join(IQ_DIR, f)
            size_mb = os.path.getsize(path) / 1e6
            files.append({"name": f, "size_mb": round(size_mb, 2)})
    return {"files": files}


@router.get("/api/signals/{filename}")
async def get_signal_data(filename: str, downsample: int = 1000):
    filename = os.path.basename(filename)
    path = os.path.join(IQ_DIR, filename)
    if not os.path.exists(path):
        return JSONResponse({"error": "File not found"}, status_code=404)

    def process():
        import numpy as np
        raw = np.fromfile(path, dtype=np.int8)
        if len(raw) < 2:
            return {"error": "File too short"}
        i = raw[0::2].astype(np.float32)
        q = raw[1::2].astype(np.float32)
        env = np.sqrt(i ** 2 + q ** 2)

        # Downsample for browser
        step = max(1, len(env) // downsample)
        ds = env[::step].tolist()

        # Simple burst detection: threshold at 2× median
        import statistics
        median = statistics.median(ds[::max(1, len(ds)//200)])
        threshold = median * 2.0
        bursts = []
        in_burst = False
        start = 0
        for idx, v in enumerate(ds):
            if not in_burst and v > threshold:
                in_burst = True
                start = idx
            elif in_burst and v <= threshold:
                in_burst = False
                bursts.append({"start": start, "end": idx})
        if in_burst:
            bursts.append({"start": start, "end": len(ds) - 1})

        sample_rate = 2_000_000
        duration_s = len(env) / sample_rate

        return {
            "envelope":    ds,
            "samples":     len(env),
            "sample_rate": sample_rate,
            "duration_s":  round(duration_s, 3),
            "bursts":      bursts,
            "threshold":   threshold,
        }

    result = await asyncio.to_thread(process)
    return result

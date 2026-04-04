from fastapi import APIRouter
from pydantic import BaseModel
import asyncio, sys, os

router = APIRouter()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

_scan_lock = asyncio.Lock()


class ScanRequest(BaseModel):
    start_mhz: int = 900
    end_mhz: int = 930
    fine: bool = False


@router.post("/api/scan")
async def run_scan(body: ScanRequest):
    if _scan_lock.locked():
        return {"error": "Scan already in progress"}
    async with _scan_lock:
        import scanner
        bin_width = 100_000 if body.fine else 1_000_000
        results = await asyncio.to_thread(
            scanner.sweep,
            body.start_mhz,
            body.end_mhz,
            bin_width,
        )
    return {"data": [{"freq": f, "power": p} for f, p in results]}

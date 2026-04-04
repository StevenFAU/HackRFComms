"""
HackRFComms — Signals Router
GET  /api/signals/list      — list IQ files in iq_dumps/
POST /api/signals/analyze   — run full analysis on an IQ file
GET  /api/signals/timeline  — load protocol timeline JSONs
"""
import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from services.signals_service import list_iq_files, analyze_iq, get_timeline

router = APIRouter()


@router.get("/signals/list")
def signals_list():
    return {"files": list_iq_files()}


class AnalyzeRequest(BaseModel):
    filename: str


@router.post("/signals/analyze")
async def signals_analyze(req: AnalyzeRequest):
    result = await asyncio.to_thread(analyze_iq, req.filename)
    return result


@router.get("/signals/timeline")
async def signals_timeline():
    result = await asyncio.to_thread(get_timeline)
    if result is None:
        return {"available": False}
    return {"available": True, **result}

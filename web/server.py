#!/usr/bin/env python3
"""HackRFComms — Lightweight Web Server"""

import os
import sys
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse

# Add repo root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

app = FastAPI(title="HackRFComms")

# Import API routers (added as they're built in later phases)
from web.api import devices, comms, scan, adsb, fm, flipper, signals

app.include_router(devices.router)
app.include_router(comms.router)
app.include_router(scan.router)
app.include_router(adsb.router)
app.include_router(fm.router)
app.include_router(flipper.router)
app.include_router(signals.router)

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))

@app.get("/api/health")
async def health():
    return {"status": "ok", "project": "HackRFComms"}

if __name__ == "__main__":
    print("HackRFComms — http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

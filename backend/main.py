import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers import device as device_router
from routers import comms as comms_router
from routers import scanner as scanner_router

app = FastAPI(title="HackRFComms API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(device_router.router, prefix="/api")
app.include_router(comms_router.router, prefix="/api")
app.include_router(scanner_router.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "project": "HackRFComms"}


# Mount static files for production build (only if frontend/dist exists)
_dist_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(_dist_path):
    app.mount("/", StaticFiles(directory=_dist_path, html=True), name="static")

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="HackRFComms API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "project": "HackRFComms"}


# Mount static files for production build (only if frontend/dist exists)
_dist_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(_dist_path):
    app.mount("/", StaticFiles(directory=_dist_path, html=True), name="static")

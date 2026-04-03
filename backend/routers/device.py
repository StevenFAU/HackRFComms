"""
HackRFComms - Device Router
Endpoints: GET /api/devices, GET /api/protocols
"""
import os
import sys
from fastapi import APIRouter

# Import config from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config

from services.device_manager import get_devices

router = APIRouter()


@router.get("/devices")
def list_devices():
    """Return status of all known and detected HackRF devices."""
    devices = get_devices()
    return {"devices": devices}


@router.get("/protocols")
def list_protocols():
    """Return all protocol configurations from config.PROTOCOLS."""
    protocols = []
    for name, params in config.PROTOCOLS.items():
        protocols.append({
            "name": name,
            "center_freq": params.get("center_freq"),
            "sample_rate": params.get("sample_rate"),
            "lna_gain": params.get("lna_gain"),
            "vga_gain": params.get("vga_gain"),
            "bandwidth": params.get("bandwidth"),
            "description": params.get("description"),
        })
    return {"protocols": protocols}

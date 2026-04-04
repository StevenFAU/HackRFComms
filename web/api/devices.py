from fastapi import APIRouter
import subprocess, sys, os, re

router = APIRouter()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config

KNOWN_DEVICES = {
    config.TX_SERIAL: {"label": "Device 0", "role": "TX"},
    config.RX_SERIAL: {"label": "Device 1", "role": "RX"},
}


def _parse_hackrf_info() -> list[dict]:
    """Run hackrf_info and parse each device block."""
    try:
        result = subprocess.run(
            ["hackrf_info"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout + result.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    devices = []
    current = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Found HackRF"):
            if current:
                devices.append(current)
            current = {}
        elif "Serial number:" in line:
            current["serial"] = line.split("Serial number:")[-1].strip()
        elif "Firmware Version:" in line:
            current["firmware"] = line.split("Firmware Version:")[-1].strip()
        elif "Hardware Version:" in line:
            current["hardware"] = line.split("Hardware Version:")[-1].strip()
    if current:
        devices.append(current)
    return devices


@router.get("/api/devices")
async def get_devices():
    detected = _parse_hackrf_info()
    detected_serials = {d["serial"] for d in detected if "serial" in d}

    result = []
    for serial, meta in KNOWN_DEVICES.items():
        found = next((d for d in detected if d.get("serial") == serial), None)
        result.append({
            "serial": serial,
            "label": meta["label"],
            "role": meta["role"],
            "connected": found is not None,
            "firmware": found.get("firmware") if found else None,
            "hardware": found.get("hardware") if found else None,
        })

    # Flipper Zero — not USB-detected by hackrf_info, always manual
    result.append({
        "serial": "N/A",
        "label": "Flipper Zero",
        "role": "SUB-GHZ",
        "connected": None,  # manual / unknown
        "firmware": None,
        "hardware": None,
    })

    return {"devices": result}


@router.get("/api/protocols")
async def get_protocols():
    protocols = []
    for name, cfg in config.PROTOCOLS.items():
        freq = cfg.get("center_freq")
        protocols.append({
            "name": name,
            "description": cfg.get("description", ""),
            "freq_mhz": round(freq / 1e6, 3) if freq else None,
            "sample_rate_mhz": round(cfg.get("sample_rate", 0) / 1e6, 1),
        })
    return {"protocols": protocols}

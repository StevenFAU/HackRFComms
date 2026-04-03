"""
HackRFComms - Device Manager
Detects connected HackRF devices via hackrf_info and matches against config serials.
"""
import os
import re
import subprocess
import sys

# Import config from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config


def _parse_hackrf_info(output: str) -> list[dict]:
    """Parse hackrf_info output into a list of device attribute dicts."""
    devices = []
    current = {}
    for line in output.splitlines():
        line = line.strip()
        # New device block
        if line.startswith("Index:"):
            if current:
                devices.append(current)
            current = {}
        elif line.startswith("Serial number:"):
            current["serial"] = line.split(":", 1)[1].strip()
        elif line.startswith("Board ID Number:"):
            # e.g. "Board ID Number: 2 (HackRF One)"
            current["board_id"] = line.split(":", 1)[1].strip()
        elif line.startswith("Firmware Version:"):
            current["firmware_version"] = line.split(":", 1)[1].strip()
    if current:
        devices.append(current)
    return devices


def get_devices() -> list[dict]:
    """
    Run hackrf_info, parse output, and match serials against TX_SERIAL / RX_SERIAL.
    Returns a list of device dicts: {serial, role, connected, board_id, firmware_version}
    """
    tx_serial = config.TX_SERIAL.lower()
    rx_serial = config.RX_SERIAL.lower()

    # Build baseline "not connected" entries for known devices
    known = {
        tx_serial: {
            "serial": config.TX_SERIAL,
            "role": "TX",
            "connected": False,
            "board_id": None,
            "firmware_version": None,
        },
        rx_serial: {
            "serial": config.RX_SERIAL,
            "role": "RX",
            "connected": False,
            "board_id": None,
            "firmware_version": None,
        },
    }

    try:
        result = subprocess.run(
            ["hackrf_info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        combined = result.stdout + result.stderr
        parsed = _parse_hackrf_info(combined)
    except FileNotFoundError:
        # hackrf_info not installed
        return list(known.values())
    except subprocess.TimeoutExpired:
        return list(known.values())
    except Exception:
        return list(known.values())

    unknown_devices = []
    for dev in parsed:
        serial = dev.get("serial", "").lower()
        board_id = dev.get("board_id")
        firmware = dev.get("firmware_version")

        if serial in known:
            known[serial].update({
                "connected": True,
                "board_id": board_id,
                "firmware_version": firmware,
            })
        else:
            unknown_devices.append({
                "serial": dev.get("serial", "unknown"),
                "role": "unknown",
                "connected": True,
                "board_id": board_id,
                "firmware_version": firmware,
            })

    return list(known.values()) + unknown_devices

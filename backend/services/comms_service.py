"""
HackRFComms - Comms Service
Wraps protocol.send_reliable and protocol.receive_and_ack for async use.

protocol.py imports numpy/SciPy/HackRF libraries that may not be installed in the
API venv. Imports are deferred to function call time so the server can start even
when hardware dependencies are absent — errors surface as {"success": false} responses.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

# Ensure repo root is on sys.path for protocol and config
_REPO_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _load_protocol():
    """Lazy-import protocol and config at call time."""
    import importlib
    protocol = importlib.import_module('protocol')
    config = importlib.import_module('config')
    return protocol, config


async def send_message(message: str) -> dict:
    """
    Send a message using protocol.send_reliable via the TX device.
    Returns {"success": bool, "message": str}
    """
    try:
        protocol, config = _load_protocol()
        await asyncio.to_thread(protocol.send_reliable, message.encode(), config.TX_SERIAL)
        return {"success": True, "message": f"Sent: {message}"}
    except Exception as e:
        return {"success": False, "message": f"Send error: {str(e)}"}


async def receive_message() -> dict:
    """
    Receive a message using protocol.receive_and_ack via the RX device.
    Returns {"data": str, "timestamp": iso_timestamp}
    """
    try:
        protocol, config = _load_protocol()
        result = await asyncio.to_thread(protocol.receive_and_ack, config.RX_SERIAL)
        # result may be bytes or str
        if isinstance(result, (bytes, bytearray)):
            data = result.decode(errors='replace')
        else:
            data = str(result) if result is not None else ""
        return {
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {
            "data": "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }

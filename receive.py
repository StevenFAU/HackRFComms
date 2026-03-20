#!/usr/bin/env python3
"""
HackRFComs - Receiver
Listens on the configured frequency and decodes OOK-modulated messages
from HackRF device 1.
"""

import sys
import signal
import tempfile
import subprocess
import time
import numpy as np
from config import (
    RX_SERIAL, CENTER_FREQ, SAMPLE_RATE,
    LNA_GAIN, VGA_GAIN, BANDWIDTH
)
from modulation import iq_to_bits, find_sync_and_decode


def receive(duration: float = 10.0):
    print(f"[RX] Listening on {CENTER_FREQ / 1e6:.1f} MHz for {duration:.0f}s...")
    print(f"[RX] Using device: {RX_SERIAL}")

    with tempfile.NamedTemporaryFile(suffix=".iq", delete=False) as f:
        iq_path = f.name

    cmd = [
        "hackrf_transfer",
        "-d", RX_SERIAL,
        "-r", iq_path,
        "-f", str(CENTER_FREQ),
        "-s", str(SAMPLE_RATE),
        "-l", str(LNA_GAIN),
        "-g", str(VGA_GAIN),
        "-a", "1",           # Amp enable
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        time.sleep(duration)
        proc.terminate()
        proc.wait(timeout=5)
    except Exception as e:
        print(f"[RX] Error during capture: {e}")
        proc.kill()
        sys.exit(1)

    print(f"[RX] Capture complete. Processing...")

    # Load captured IQ data
    iq_data = np.fromfile(iq_path, dtype=np.int8)
    print(f"[RX] Captured {len(iq_data)} bytes ({len(iq_data) / (SAMPLE_RATE * 2):.2f}s of data)")

    if len(iq_data) < 1000:
        print("[RX] Not enough data captured.")
        return

    # Demodulate
    bits = iq_to_bits(iq_data)
    print(f"[RX] Demodulated {len(bits)} symbols")

    # Decode
    payload = find_sync_and_decode(bits)
    if payload is not None:
        message = payload.decode("utf-8", errors="replace")
        print(f"\n[RX] === MESSAGE RECEIVED ===")
        print(f"[RX] {message}")
        print(f"[RX] =========================\n")
    else:
        print("[RX] No valid message found in capture.")


if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    receive(duration=dur)

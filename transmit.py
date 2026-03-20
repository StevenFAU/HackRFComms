#!/usr/bin/env python3
"""
HackRFComs - Transmitter
Sends a text message over the air using OOK modulation on HackRF device 0.
"""

import sys
import time
import tempfile
import subprocess
from config import TX_SERIAL, CENTER_FREQ, SAMPLE_RATE, TX_VGA_GAIN
from modulation import build_frame, frame_to_iq


def transmit(message: str, repeat: int = 3):
    print(f"[TX] Preparing message: {message!r}")
    frame = build_frame(message.encode("utf-8"))
    print(f"[TX] Frame: {len(frame)} bytes ({len(frame) * 8} bits)")

    iq_samples = frame_to_iq(frame)
    print(f"[TX] IQ samples: {len(iq_samples)} bytes")

    # Repeat the frame for reliability
    iq_repeated = b""
    for _ in range(repeat):
        iq_repeated += iq_samples.tobytes()

    # Write to temp file for hackrf_transfer
    with tempfile.NamedTemporaryFile(suffix=".iq", delete=False) as f:
        f.write(iq_repeated)
        iq_path = f.name

    print(f"[TX] Transmitting {repeat}x on {CENTER_FREQ / 1e6:.1f} MHz...")
    print(f"[TX] Using device: {TX_SERIAL}")

    cmd = [
        "hackrf_transfer",
        "-d", TX_SERIAL,
        "-t", iq_path,
        "-f", str(CENTER_FREQ),
        "-s", str(SAMPLE_RATE),
        "-x", str(TX_VGA_GAIN),
        "-a", "1",           # Amp enable
        "-R",                # Repeat (loop the file until stopped)
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        # Let it transmit for enough time to send all repeats
        duration = (len(iq_repeated) / (SAMPLE_RATE * 2)) * 1.5  # 1.5x safety margin
        duration = max(duration, 2.0)
        print(f"[TX] Broadcasting for {duration:.1f}s...")
        time.sleep(duration)
        proc.terminate()
        proc.wait(timeout=5)
        print("[TX] Done.")
    except Exception as e:
        print(f"[TX] Error: {e}")
        proc.kill()
        sys.exit(1)


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Hello from HackRF!"
    transmit(msg)

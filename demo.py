#!/usr/bin/env python3
"""
HackRFComs - Hello World
TX sends a message, RX captures it, we decode and dump raw IQ for inspection.
Raw files are saved so you can open them in inspectrum / GNU Radio.
"""

import sys
import os
import time
import subprocess
import threading
import numpy as np
from config import (
    TX_SERIAL, RX_SERIAL, CENTER_FREQ, SAMPLE_RATE,
    LNA_GAIN, VGA_GAIN, TX_VGA_GAIN
)
from modulation import build_frame, frame_to_iq, demodulate

IQ_DIR = os.path.join(os.path.dirname(__file__), "iq_dumps")


def _run_hackrf(cmd, duration, label):
    """Run hackrf_transfer for a duration, then clean up reliably."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        print(f"[{label}] hackrf_transfer not found — is it installed?")
        return False

    time.sleep(duration)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print(f"[{label}] Process didn't stop, killing...")
        proc.kill()
        proc.wait()

    ret = proc.returncode
    if ret and ret != -15:  # -15 = SIGTERM, expected
        output = proc.stdout.read().decode(errors="replace").strip()
        print(f"[{label}] hackrf_transfer exited {ret}: {output}")
        return False
    return True


def capture_rx(path: str, duration: float):
    cmd = [
        "hackrf_transfer", "-d", RX_SERIAL, "-r", path,
        "-f", str(CENTER_FREQ), "-s", str(SAMPLE_RATE),
        "-l", str(LNA_GAIN), "-g", str(VGA_GAIN), "-a", "1",
    ]
    return _run_hackrf(cmd, duration, "RX")


def transmit(iq_path: str, duration: float):
    cmd = [
        "hackrf_transfer", "-d", TX_SERIAL, "-t", iq_path,
        "-f", str(CENTER_FREQ), "-s", str(SAMPLE_RATE),
        "-x", str(TX_VGA_GAIN), "-a", "1",
    ]
    return _run_hackrf(cmd, duration, "TX")


def main():
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Hello from HackRF!"
    os.makedirs(IQ_DIR, exist_ok=True)

    print(f"TX: {TX_SERIAL}  ->  RX: {RX_SERIAL}")
    print(f"Freq: {CENTER_FREQ/1e6:.1f} MHz  Rate: {SAMPLE_RATE/1e6:.1f} MS/s")
    print(f"Message: {msg!r}")
    print()

    # Build TX signal
    frame = build_frame(msg.encode())
    iq_samples = frame_to_iq(frame)
    tx_iq = iq_samples.tobytes() * 5  # repeat 5x

    tx_path = os.path.join(IQ_DIR, "tx.iq")
    rx_path = os.path.join(IQ_DIR, "rx.iq")
    with open(tx_path, "wb") as f:
        f.write(tx_iq)
    print(f"Saved TX IQ: {tx_path} ({len(tx_iq)} bytes)")

    # Start RX, wait a moment, then TX
    print("Starting RX capture...")
    rx_thread = threading.Thread(target=capture_rx, args=(rx_path, 10.0))
    rx_thread.start()
    time.sleep(2.0)

    tx_duration = (len(tx_iq) / (SAMPLE_RATE * 2)) * 1.5
    tx_duration = max(tx_duration, 3.0)
    print(f"Transmitting for {tx_duration:.1f}s...")
    transmit(tx_path, tx_duration)

    print("Waiting for RX to finish...")
    rx_thread.join()

    # Load and decode
    iq_data = np.fromfile(rx_path, dtype=np.int8)
    print(f"Saved RX IQ: {rx_path} ({len(iq_data)} bytes)")
    print()

    payload = demodulate(iq_data)
    if payload is not None:
        decoded = payload.decode("utf-8", errors="replace")
        print(f"RECEIVED: {decoded}")
        print("Match!" if decoded == msg else "Decoded but doesn't match.")
    else:
        print("No valid message decoded.")

    print(f"\nInspect with:  inspectrum {rx_path}")


if __name__ == "__main__":
    main()

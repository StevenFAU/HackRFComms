#!/usr/bin/env python3
"""
HackRFComs - Full Demo
Runs RX and TX concurrently: starts the receiver, then transmits a message,
then waits for the receiver to decode it.
"""

import sys
import time
import tempfile
import subprocess
import threading
import numpy as np
from config import (
    TX_SERIAL, RX_SERIAL, CENTER_FREQ, SAMPLE_RATE,
    LNA_GAIN, VGA_GAIN, TX_VGA_GAIN
)
from modulation import build_frame, frame_to_iq, iq_to_bits, find_sync_and_decode


def run_receiver(iq_path: str, duration: float):
    """Capture IQ data from the RX device."""
    cmd = [
        "hackrf_transfer",
        "-d", RX_SERIAL,
        "-r", iq_path,
        "-f", str(CENTER_FREQ),
        "-s", str(SAMPLE_RATE),
        "-l", str(LNA_GAIN),
        "-g", str(VGA_GAIN),
        "-a", "1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(duration)
    proc.terminate()
    proc.wait(timeout=5)


def run_transmitter(message: str, repeat: int = 5):
    """Build and transmit a message."""
    frame = build_frame(message.encode("utf-8"))
    iq_samples = frame_to_iq(frame)

    iq_repeated = iq_samples.tobytes() * repeat

    with tempfile.NamedTemporaryFile(suffix=".iq", delete=False) as f:
        f.write(iq_repeated)
        tx_path = f.name

    cmd = [
        "hackrf_transfer",
        "-d", TX_SERIAL,
        "-t", tx_path,
        "-f", str(CENTER_FREQ),
        "-s", str(SAMPLE_RATE),
        "-x", str(TX_VGA_GAIN),
        "-a", "1",
        "-R",
    ]

    duration = (len(iq_repeated) / (SAMPLE_RATE * 2)) * 1.5
    duration = max(duration, 3.0)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(duration)
    proc.terminate()
    proc.wait(timeout=5)


def demo(message: str):
    print("=" * 50)
    print("  HackRFComs - Device-to-Device Communication")
    print("=" * 50)
    print(f"  TX Device: {TX_SERIAL}")
    print(f"  RX Device: {RX_SERIAL}")
    print(f"  Frequency: {CENTER_FREQ / 1e6:.1f} MHz")
    print(f"  Sample Rate: {SAMPLE_RATE / 1e6:.1f} MS/s")
    print(f"  Message: {message!r}")
    print("=" * 50)

    rx_iq_path = tempfile.mktemp(suffix=".iq")
    rx_duration = 12.0

    # Start receiver first
    print("\n[1/3] Starting receiver...")
    rx_thread = threading.Thread(target=run_receiver, args=(rx_iq_path, rx_duration))
    rx_thread.start()

    # Give RX a moment to spin up
    time.sleep(2.0)

    # Start transmitter
    print("[2/3] Transmitting message...")
    run_transmitter(message, repeat=5)

    # Wait for receiver to finish
    print("[3/3] Waiting for receiver to finish capture...")
    rx_thread.join()

    # Decode
    print("\n[*] Decoding captured data...")
    iq_data = np.fromfile(rx_iq_path, dtype=np.int8)
    print(f"    Captured: {len(iq_data)} bytes ({len(iq_data) / (SAMPLE_RATE * 2):.2f}s)")

    bits = iq_to_bits(iq_data)
    print(f"    Demodulated: {len(bits)} symbols")

    payload = find_sync_and_decode(bits)
    if payload is not None:
        decoded = payload.decode("utf-8", errors="replace")
        print(f"\n{'=' * 50}")
        print(f"  RECEIVED: {decoded}")
        print(f"{'=' * 50}")
        if decoded == message:
            print("  Status: SUCCESS - Message matches!")
        else:
            print("  Status: PARTIAL - Message decoded but doesn't match")
    else:
        print("\n  Status: FAILED - No valid message decoded")
        print("  Tips: Try moving devices further apart (to reduce")
        print("  direct coupling), or adjust gains in config.py")

    print()


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Hello from HackRF!"
    demo(msg)

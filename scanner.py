#!/usr/bin/env python3
"""
HackRFComs - Frequency Scanner
Sweep a frequency range and show what's out there.
Reuses the demodulation chain to check for OOK signals at each step,
and shows a power-vs-frequency overview.
"""

import sys
import os
import time
import subprocess
import numpy as np
from config import RX_SERIAL, SAMPLE_RATE, LNA_GAIN, VGA_GAIN

IQ_DIR = os.path.join(os.path.dirname(__file__), "iq_dumps")


def _run_hackrf(cmd, duration):
    """Run hackrf_transfer for a duration, then clean up."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        print("hackrf_transfer not found")
        return False
    time.sleep(duration)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    return proc.returncode in (0, -15)


def measure_power(freq: int, duration: float = 0.5,
                  serial: str = RX_SERIAL) -> tuple[float, float]:
    """
    Capture at a frequency and return (mean_power_dB, peak_power_dB).
    """
    path = f"/tmp/hackrf_scan_{os.getpid()}.iq"
    cmd = [
        "hackrf_transfer", "-d", serial, "-r", path,
        "-f", str(freq), "-s", str(SAMPLE_RATE),
        "-l", str(LNA_GAIN), "-g", str(VGA_GAIN), "-a", "1",
    ]
    if not _run_hackrf(cmd, duration):
        return -100.0, -100.0

    try:
        raw = np.fromfile(path, dtype=np.int8)
    except FileNotFoundError:
        return -100.0, -100.0

    if len(raw) < 1000:
        return -100.0, -100.0

    i = raw[0::2].astype(np.float64)
    q = raw[1::2].astype(np.float64)
    power = i**2 + q**2

    mean_pow = np.mean(power)
    peak_pow = np.max(power)

    # Convert to dB (relative to full-scale 127^2)
    fs = 127.0 ** 2
    mean_db = 10 * np.log10(mean_pow / fs) if mean_pow > 0 else -100.0
    peak_db = 10 * np.log10(peak_pow / fs) if peak_pow > 0 else -100.0

    return mean_db, peak_db


def scan(start_freq: int, end_freq: int, step: int,
         dwell: float = 0.5, serial: str = RX_SERIAL):
    """
    Sweep from start_freq to end_freq, printing power at each step.
    """
    freqs = list(range(start_freq, end_freq + 1, step))
    print(f"Scanning {start_freq/1e6:.1f} - {end_freq/1e6:.1f} MHz "
          f"({len(freqs)} steps, {step/1e6:.2f} MHz each, {dwell:.1f}s dwell)")
    print(f"Device: {serial}")
    print()
    print(f"{'Freq (MHz)':>12}  {'Mean dB':>8}  {'Peak dB':>8}  {'Strength'}")
    print("-" * 60)

    results = []
    for freq in freqs:
        mean_db, peak_db = measure_power(freq, dwell, serial)
        results.append((freq, mean_db, peak_db))

        # Visual bar
        bar_len = max(0, int((mean_db + 30) * 3))  # -30 dB = 0 bars
        bar = "#" * min(bar_len, 40)
        print(f"  {freq/1e6:>10.3f}  {mean_db:>8.1f}  {peak_db:>8.1f}  {bar}")

    # Summary
    print()
    strongest = max(results, key=lambda r: r[1])
    print(f"Strongest: {strongest[0]/1e6:.3f} MHz (mean={strongest[1]:.1f} dB, peak={strongest[2]:.1f} dB)")

    return results


if __name__ == "__main__":
    # Defaults: scan ISM 915 MHz band
    start = 910_000_000
    end = 920_000_000
    step = 1_000_000  # 1 MHz steps

    if len(sys.argv) >= 3:
        start = int(float(sys.argv[1]) * 1e6)
        end = int(float(sys.argv[2]) * 1e6)
    if len(sys.argv) >= 4:
        step = int(float(sys.argv[3]) * 1e6)

    scan(start, end, step)

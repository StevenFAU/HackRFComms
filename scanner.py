#!/usr/bin/env python3
"""
HackRFComs - Frequency Scanner
Uses hackrf_sweep for fast wideband scanning. Can sweep the entire
HackRF range (1 MHz – 6 GHz) in seconds instead of minutes.

Output: live ASCII power bars + optional matplotlib waterfall plot.
"""

import sys
import os
import subprocess
import numpy as np
from config import RX_SERIAL, LNA_GAIN, VGA_GAIN

IQ_DIR = os.path.join(os.path.dirname(__file__), "iq_dumps")


def sweep(start_mhz: int = 1, end_mhz: int = 6000,
          bin_width: int = 1_000_000, num_sweeps: int = 1,
          serial: str = RX_SERIAL,
          lna_gain: int = LNA_GAIN, vga_gain: int = VGA_GAIN,
          amp: bool = True) -> list[tuple[float, float]]:
    """
    Run hackrf_sweep and return list of (freq_mhz, power_db) tuples.
    bin_width is in Hz (default 1 MHz). Smaller = finer resolution but slower.
    """
    cmd = [
        "hackrf_sweep",
        "-d", serial,
        "-f", f"{start_mhz}:{end_mhz}",
        "-w", str(bin_width),
        "-l", str(lna_gain),
        "-g", str(vga_gain),
        "-N", str(num_sweeps),
    ]
    if amp:
        cmd += ["-a", "1"]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        print("hackrf_sweep not found — install hackrf tools")
        return []
    except subprocess.TimeoutExpired:
        print("hackrf_sweep timed out")
        return []

    results = []
    for line in proc.stdout.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("call ") or line.startswith("Stop "):
            continue
        parts = line.split(", ")
        if len(parts) < 7:
            continue
        try:
            hz_low = int(parts[2])
            hz_high = int(parts[3])
            hz_bin_width = float(parts[4])
            db_values = [float(x) for x in parts[6:]]
        except (ValueError, IndexError):
            continue

        n_bins = len(db_values)
        for i, db in enumerate(db_values):
            freq_hz = hz_low + i * hz_bin_width
            results.append((freq_hz / 1e6, db))

    # Sort by frequency
    results.sort(key=lambda x: x[0])
    return results


def print_results(results: list[tuple[float, float]],
                  start_mhz: int, end_mhz: int):
    """Print ASCII bar chart of scan results."""
    if not results:
        print("No results.")
        return

    db_values = [db for _, db in results]
    db_min = min(db_values)
    db_max = max(db_values)

    print(f"\nScan: {start_mhz} – {end_mhz} MHz  ({len(results)} bins)")
    print(f"Range: {db_min:.1f} to {db_max:.1f} dB")
    print()
    print(f"{'Freq (MHz)':>12}  {'dB':>7}  Signal")
    print("-" * 70)

    for freq_mhz, db in results:
        # Normalize to 0–40 character bar
        bar_len = max(0, int((db - db_min) / max(db_max - db_min, 1) * 40))
        bar = "#" * bar_len
        print(f"  {freq_mhz:>10.2f}  {db:>7.1f}  {bar}")

    # Top 5 strongest
    print()
    top = sorted(results, key=lambda x: x[1], reverse=True)[:5]
    print("Strongest frequencies:")
    for freq, db in top:
        print(f"  {freq:.2f} MHz  ({db:.1f} dB)")


def plot_results(results: list[tuple[float, float]],
                 start_mhz: int, end_mhz: int, save: bool = False):
    """Plot scan results as a spectrum graph."""
    import matplotlib
    matplotlib.use('TkAgg')
    import matplotlib.pyplot as plt

    if not results:
        print("No results to plot.")
        return

    freqs = np.array([r[0] for r in results])
    powers = np.array([r[1] for r in results])

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(14, 5), facecolor='#111')

    ax.fill_between(freqs, powers, powers.min() - 3, alpha=0.3, color='#ff6600')
    ax.plot(freqs, powers, color='#ff6600', linewidth=0.6)

    # Mark strongest
    peak_idx = np.argmax(powers)
    ax.annotate(f'{freqs[peak_idx]:.1f} MHz\n{powers[peak_idx]:.1f} dB',
                xy=(freqs[peak_idx], powers[peak_idx]),
                xytext=(freqs[peak_idx], powers[peak_idx] + 5),
                ha='center', fontsize=8, color='white',
                arrowprops=dict(arrowstyle='->', color='cyan'),
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#333', alpha=0.8))

    # Mark known bands
    bands = [
        (88, 108, "FM Radio"),
        (462, 467, "FRS/GMRS"),
        (851, 869, "Cell 850"),
        (869, 894, "Cell 850 DL"),
        (902, 928, "ISM 915"),
        (1710, 1755, "AWS UL"),
        (1930, 1990, "PCS DL"),
        (2400, 2500, "WiFi 2.4G"),
    ]
    for bstart, bend, name in bands:
        if bstart >= freqs[0] and bend <= freqs[-1]:
            ax.axvspan(bstart, bend, alpha=0.08, color='cyan')
            mid = (bstart + bend) / 2
            ax.text(mid, ax.get_ylim()[1] - 2, name,
                    ha='center', fontsize=6, color='cyan', alpha=0.7)

    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Power (dB)")
    ax.set_title(f"HackRFComs — Spectrum Scan {start_mhz}–{end_mhz} MHz",
                 fontweight='bold', color='white')
    ax.grid(True, alpha=0.15)
    ax.set_xlim(freqs[0], freqs[-1])

    plt.tight_layout()

    if save:
        os.makedirs(IQ_DIR, exist_ok=True)
        out = os.path.join(IQ_DIR, "spectrum_scan.png")
        plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='#111')
        print(f"Saved: {out}")

    plt.show()


if __name__ == "__main__":
    usage = """Usage:
  python3 scanner.py                          # Quick ISM 915 band scan
  python3 scanner.py 88 108                   # FM radio band
  python3 scanner.py 400 1700                 # Wide sweep (400 MHz - 1.7 GHz)
  python3 scanner.py 2400 2500 --plot         # WiFi band with plot
  python3 scanner.py 1 6000 --plot --save     # Full range with saved plot

Options:
  --plot   Show matplotlib spectrum plot
  --save   Save plot to iq_dumps/spectrum_scan.png
  --fine   Use 100 kHz bins (slower, more detail)
  --sweeps N  Number of sweeps to average (default: 1)
"""

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if "--help" in flags or "-h" in flags:
        print(usage)
        sys.exit(0)

    # Defaults: ISM 915 band
    start = 900
    end = 930

    if len(args) >= 2:
        start = int(float(args[0]))
        end = int(float(args[1]))
    elif len(args) == 1:
        # Single arg: center frequency, scan +/- 10 MHz
        center = int(float(args[0]))
        start = center - 10
        end = center + 10

    bin_width = 100_000 if "--fine" in flags else 1_000_000

    num_sweeps = 1
    if "--sweeps" in sys.argv:
        idx = sys.argv.index("--sweeps")
        if idx + 1 < len(sys.argv):
            num_sweeps = int(sys.argv[idx + 1])

    do_plot = "--plot" in flags
    do_save = "--save" in flags

    print(f"Scanning {start} – {end} MHz ({'fine' if bin_width < 1_000_000 else 'coarse'} resolution)...")
    results = sweep(start, end, bin_width=bin_width, num_sweeps=num_sweeps)
    print_results(results, start, end)

    if do_plot:
        plot_results(results, start, end, save=do_save)

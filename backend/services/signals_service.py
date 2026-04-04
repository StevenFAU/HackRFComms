"""
HackRFComms — Signals Service
Provides IQ analysis data for the browser, replacing matplotlib outputs.

Wraps the same signal processing used by visualize.py and visualize_protocol.py
(mix-down to carrier, envelope, spectrogram, bit decode) but returns JSON
instead of matplotlib figures.
"""
import json
import os
import sys
import time

import numpy as np
from scipy import signal as dsp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from config import SAMPLE_RATE, SAMPLES_PER_SYMBOL
from modulation import CARRIER_OFFSET

IQ_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'iq_dumps')

# Downsampling targets for browser display
SPEC_TIME_BINS = 150    # spectrogram time steps
SPEC_FREQ_BINS = 128    # spectrogram frequency bins
ENVELOPE_POINTS = 2000  # points in full-capture envelope trace
OOK_POINTS = 600        # points in zoomed OOK burst view
MAX_BITS = 248          # one full frame


def list_iq_files() -> list[dict]:
    """Return metadata for all .iq files in iq_dumps/."""
    results = []
    try:
        for name in sorted(os.listdir(IQ_DIR)):
            if not name.endswith('.iq'):
                continue
            path = os.path.join(IQ_DIR, name)
            stat = os.stat(path)
            size_mb = round(stat.st_size / 1e6, 2)
            results.append({
                "name": name,
                "size_mb": size_mb,
                "modified": int(stat.st_mtime),
            })
    except FileNotFoundError:
        pass
    return results


def _load_iq(path: str) -> np.ndarray:
    return np.fromfile(path, dtype=np.int8)


def _mix_and_envelope(raw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mix down to carrier offset, lowpass filter, return (complex_signal, envelope)."""
    i = raw[0::2].astype(np.float64)
    q = raw[1::2].astype(np.float64)
    n = len(i)
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    csig = i + 1j * q
    mixed = csig * np.exp(-1j * 2 * np.pi * CARRIER_OFFSET * t)
    b, a = dsp.butter(4, 30_000 / (SAMPLE_RATE / 2), btype='low')
    filt = dsp.filtfilt(b, a, mixed)
    env = np.abs(filt)
    return filt, env


def _downsample(arr: np.ndarray, n: int) -> list[float]:
    """Downsample 1D array to at most n points using max-pooling."""
    step = max(1, len(arr) // n)
    trimmed = arr[:len(arr) // step * step]
    pooled = trimmed.reshape(-1, step).max(axis=1)
    return pooled.tolist()


def _compute_spectrogram(raw: np.ndarray) -> dict:
    """
    Compute STFT spectrogram on the first ~2M samples (1s) of IQ data.
    Returns a flat list of power values (row-major, time × freq) + axis info.
    """
    NFFT = 512
    # Limit to first 2M samples to keep JSON manageable
    chunk = raw[:min(len(raw), 4_000_000)]  # 4M int8 = 2M complex samples
    i = chunk[0::2].astype(np.float32)
    q = chunk[1::2].astype(np.float32)
    csig = i + 1j * q

    freqs, times, Zxx = dsp.stft(csig, fs=SAMPLE_RATE, nperseg=NFFT,
                                  noverlap=NFFT * 3 // 4)
    power_db = 20 * np.log10(np.abs(Zxx) + 1e-10)

    # Downsample to target grid
    n_t = power_db.shape[1]
    n_f = power_db.shape[0]
    t_step = max(1, n_t // SPEC_TIME_BINS)
    f_step = max(1, n_f // SPEC_FREQ_BINS)

    spec = power_db[::f_step, ::t_step]
    spec = spec[:SPEC_FREQ_BINS, :SPEC_TIME_BINS]

    # Normalise to [0, 1] for colormap
    vmin, vmax = np.percentile(spec, 5), np.percentile(spec, 99)
    norm = np.clip((spec - vmin) / (vmax - vmin + 1e-6), 0, 1)

    duration = len(csig) / SAMPLE_RATE
    return {
        "data":      norm.T.ravel().tolist(),  # [time_idx, freq_idx] row-major
        "time_bins": int(norm.shape[1]),
        "freq_bins": int(norm.shape[0]),
        "duration_s": round(duration, 2),
        "freq_min_khz": round(float(freqs[0]) / 1e3, 1),
        "freq_max_khz": round(float(freqs[-1]) / 1e3, 1),
        "carrier_khz":  round(CARRIER_OFFSET / 1e3, 1),
    }


def analyze_iq(filename: str) -> dict:
    """
    Full signal analysis of an IQ file. Returns JSON-ready dict with:
    - spectrogram (downsampled 2D power grid)
    - envelope (downsampled 1D, full capture)
    - ook_zoom (downsampled envelope around burst start)
    - bits (decoded 0/1 list, one frame)
    - stats (duration, sample_rate, burst timing, threshold)
    """
    filename = os.path.basename(filename)  # safety
    path = os.path.join(IQ_DIR, filename)
    if not os.path.exists(path):
        return {"error": f"{filename} not found"}

    raw = _load_iq(path)
    if len(raw) < 2000:
        return {"error": "File too short"}

    filt, env = _mix_and_envelope(raw)

    n_samples = len(env)
    duration_s = round(n_samples / SAMPLE_RATE, 2)

    # Threshold and burst region
    peak = float(env.max())
    threshold = peak * 0.3

    above = np.where(env > threshold)[0]
    burst_start = int(above[0]) if len(above) > 0 else 0
    burst_end   = int(above[-1]) if len(above) > 0 else n_samples

    # ── Envelope ──────────────────────────────────────────────────────────────
    envelope_ds = _downsample(env, ENVELOPE_POINTS)
    t_step_env = n_samples / SAMPLE_RATE / len(envelope_ds)
    envelope_t = [round(i * t_step_env, 4) for i in range(len(envelope_ds))]
    env_peak = max(envelope_ds) if envelope_ds else 1.0
    threshold_norm = threshold / peak if peak > 0 else 0.3

    # ── OOK zoom (one frame worth of samples around burst) ────────────────────
    frame_samples = MAX_BITS * SAMPLES_PER_SYMBOL
    ook_end = min(burst_start + frame_samples + SAMPLES_PER_SYMBOL * 10, n_samples)
    ook_env = env[burst_start:ook_end]
    ook_ds = _downsample(ook_env, OOK_POINTS)
    ook_t_total_ms = len(ook_env) / SAMPLE_RATE * 1000
    ook_t = [round(i * ook_t_total_ms / len(ook_ds), 3) for i in range(len(ook_ds))]

    # Annotate preamble / sync / data boundaries in ms
    preamble_end_ms = (64 * SAMPLES_PER_SYMBOL) / SAMPLE_RATE * 1000
    sync_end_ms     = preamble_end_ms + (16 * SAMPLES_PER_SYMBOL) / SAMPLE_RATE * 1000

    # ── Decoded bits ──────────────────────────────────────────────────────────
    burst_env_full = env[burst_start:burst_start + frame_samples + SAMPLES_PER_SYMBOL * 5]
    SPS = SAMPLES_PER_SYMBOL
    preamble_bits = np.unpackbits(np.frombuffer(b'\xaa' * 8, dtype=np.uint8))
    best_bits: list[int] = []
    best_score = 0

    for phase in range(0, SPS, max(1, SPS // 10)):
        indices = np.arange(phase + SPS // 2, len(burst_env_full), SPS)
        indices = indices[indices < len(burst_env_full)]
        sampled = burst_env_full[indices]
        bits = (sampled > threshold).astype(np.uint8)
        if len(bits) >= len(preamble_bits):
            score = int(np.sum(bits[:len(preamble_bits)] == preamble_bits))
            if score > best_score:
                best_score = score
                best_bits = bits[:MAX_BITS].tolist()

    # ── Spectrogram ───────────────────────────────────────────────────────────
    spec = _compute_spectrogram(raw)

    return {
        "filename": filename,
        "duration_s": duration_s,
        "sample_rate": SAMPLE_RATE,
        "n_samples": n_samples,
        "carrier_khz": round(CARRIER_OFFSET / 1e3, 1),
        "burst_start_s": round(burst_start / SAMPLE_RATE, 4),
        "burst_end_s":   round(burst_end   / SAMPLE_RATE, 4),
        "threshold_norm": round(threshold_norm, 4),

        "spectrogram": spec,

        "envelope": {
            "t": envelope_t,
            "v": [round(v / env_peak, 4) for v in envelope_ds],  # normalised 0–1
            "threshold_norm": round(threshold_norm, 4),
        },

        "ook_zoom": {
            "t_ms":           ook_t,
            "v":              [round(v / peak, 4) for v in ook_ds],
            "threshold_norm": round(threshold_norm, 4),
            "preamble_end_ms": round(preamble_end_ms, 2),
            "sync_end_ms":     round(sync_end_ms, 2),
            "total_ms":        round(ook_t_total_ms, 2),
        },

        "bits": {
            "data":      best_bits,
            "n_bits":    len(best_bits),
            "preamble_score": best_score,
            "frame_sections": {
                "preamble_end": 64,
                "sync_end":     80,
                "len_end":      88,
            },
        },
    }


def get_timeline() -> dict | None:
    """
    Load sender_timeline.json and receiver_timeline.json if they exist.
    Returns normalised dict with t=0 at the earliest timestamp, or None.
    """
    sender_path   = os.path.join(IQ_DIR, "sender_timeline.json")
    receiver_path = os.path.join(IQ_DIR, "receiver_timeline.json")

    sender_tl   = {}
    receiver_tl = {}

    if os.path.exists(sender_path):
        with open(sender_path) as f:
            sender_tl = {k: v for k, v in json.load(f)}
    if os.path.exists(receiver_path):
        with open(receiver_path) as f:
            receiver_tl = {k: v for k, v in json.load(f)}

    if not sender_tl and not receiver_tl:
        return None

    all_ts = list(sender_tl.values()) + list(receiver_tl.values())
    t0 = min(all_ts)

    def norm(tl):
        return {k: round(v - t0, 4) for k, v in tl.items()}

    sender_n   = norm(sender_tl)
    receiver_n = norm(receiver_tl)

    # Build phase list for each device
    def phases(tl, pairs, color):
        result = []
        for start_k, end_k, label in pairs:
            if start_k in tl and end_k in tl:
                result.append({
                    "label": label,
                    "start": tl[start_k],
                    "end":   tl[end_k],
                    "color": color,
                })
        return result

    sender_phases = phases(sender_n, [
        ("sender_tx_start", "sender_tx_end",   "TX DATA"),
        ("sender_rx_start", "sender_rx_end",   "RX (ACK wait)"),
    ], "#ff6600")

    receiver_phases = phases(receiver_n, [
        ("receiver_rx_start", "receiver_rx_end", "RX (listen)"),
        ("receiver_tx_start", "receiver_tx_end", "TX ACK"),
    ], "#00cc66")

    turnaround = None
    if "sender_tx_end" in sender_n and "receiver_tx_start" in receiver_n:
        turnaround = round(receiver_n["receiver_tx_start"] - sender_n["sender_tx_end"], 3)

    total = round(max(all_ts) - t0, 3)

    return {
        "sender":      {"phases": sender_phases},
        "receiver":    {"phases": receiver_phases},
        "turnaround_s": turnaround,
        "total_s":      total,
    }

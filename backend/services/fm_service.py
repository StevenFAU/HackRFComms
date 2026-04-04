"""
HackRFComms — FM Service
Wraps protocols/fm.py without modifying it.

Uses asyncio.create_subprocess_exec for capture so cancellation works
mid-flight (fm.py's capture_iq uses time.sleep internally — can't cancel it).
demodulate_fm and save_wav are called directly from fm.py.
"""
import asyncio
import os
import sys
import numpy as np
from typing import Callable, Awaitable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from config import PROTOCOLS, RX_SERIAL
from protocols.fm import demodulate_fm, save_wav, AUDIO_RATE, IQ_DIR

# Only one FM capture at a time (half-duplex hardware)
_lock = asyncio.Lock()

WAVEFORM_POINTS = 800  # downsample to this many points for browser display


async def run_tune(
    freq_mhz: float,
    duration: float,
    on_event: Callable[[dict], Awaitable[None]],
    cancel_event: asyncio.Event,
) -> None:
    """
    Full FM pipeline with cancellation support.
    Streams status events via on_event:
      {type: "status", phase: "capturing"|"demodulating"|"saving", ...}
      {type: "done",   wav_url: str, waveform: [float,...], duration_s: float}
      {type: "cancelled"}
      {type: "error",  message: str}
    """
    if _lock.locked():
        await on_event({"type": "error", "message": "FM capture already in progress"})
        return

    async with _lock:
        config = PROTOCOLS["fm"].copy()
        config["center_freq"] = int(freq_mhz * 1e6)
        device = RX_SERIAL

        os.makedirs(IQ_DIR, exist_ok=True)
        iq_path = os.path.join(IQ_DIR, f"fm_{freq_mhz:.1f}MHz.iq")

        # ── Phase 1: Capture ─────────────────────────────────────────────────
        await on_event({
            "type": "status", "phase": "capturing",
            "freq_mhz": freq_mhz, "duration": duration,
        })

        cmd = [
            "hackrf_transfer", "-d", device, "-r", iq_path,
            "-f", str(config["center_freq"]),
            "-s", str(config["sample_rate"]),
            "-l", str(config["lna_gain"]),
            "-g", str(config["vga_gain"]),
            "-a", "1",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            await on_event({"type": "error",
                            "message": "hackrf_transfer not found — install hackrf tools"})
            return

        # Poll until duration elapses or cancel fires
        elapsed = 0.0
        tick = 0.25
        while elapsed < duration:
            if cancel_event.is_set():
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                await on_event({"type": "cancelled"})
                return
            await asyncio.sleep(tick)
            elapsed += tick
            await on_event({
                "type": "progress",
                "phase": "capturing",
                "elapsed": round(elapsed, 1),
                "total": duration,
            })

        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()

        if not os.path.exists(iq_path):
            await on_event({"type": "error", "message": "No IQ file produced"})
            return

        try:
            iq_data = np.fromfile(iq_path, dtype=np.int8)
        except Exception as exc:
            await on_event({"type": "error", "message": f"Failed to read IQ: {exc}"})
            return

        if len(iq_data) < 1000:
            await on_event({"type": "error", "message": "Capture too short"})
            return

        # ── Phase 2: Demodulate ──────────────────────────────────────────────
        await on_event({"type": "status", "phase": "demodulating",
                        "samples": int(len(iq_data))})

        try:
            audio: np.ndarray = await asyncio.to_thread(
                demodulate_fm, iq_data, config["sample_rate"]
            )
        except Exception as exc:
            await on_event({"type": "error", "message": f"Demodulation failed: {exc}"})
            return

        # ── Phase 3: Save WAV ────────────────────────────────────────────────
        await on_event({"type": "status", "phase": "saving"})

        wav_filename = f"fm_{freq_mhz:.1f}MHz.wav"
        wav_path = os.path.join(IQ_DIR, wav_filename)

        try:
            await asyncio.to_thread(save_wav, audio, wav_path)
        except Exception as exc:
            await on_event({"type": "error", "message": f"Save failed: {exc}"})
            return

        # ── Downsample waveform for browser display ──────────────────────────
        n = len(audio)
        step = max(1, n // WAVEFORM_POINTS)
        waveform = audio[::step][:WAVEFORM_POINTS].tolist()
        duration_s = round(len(audio) / AUDIO_RATE, 1)

        await on_event({
            "type": "done",
            "wav_url": f"/api/fm/audio/{wav_filename}",
            "waveform": waveform,
            "duration_s": duration_s,
            "freq_mhz": freq_mhz,
        })

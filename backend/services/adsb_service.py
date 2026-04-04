"""
HackRFComms — ADS-B Service
Wraps protocols/adsb.py without modifying it.

Strategy: call adsb.capture_iq() + adsb.compute_envelope() via to_thread,
then run the preamble-detection decode loop ourselves (using adsb's low-level
functions) so we can broadcast each aircraft update over WebSocket live.
"""
import asyncio
import os
import sys
import time
import numpy as np
from typing import Callable, Awaitable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from config import PROTOCOLS, RX_SERIAL
import protocols.adsb as _adsb

# Global aircraft state — updated by the most recent decode run.
# Keyed by ICAO hex string. Values are the same dict adsb.decode_message uses.
aircraft_state: dict[str, dict] = {}


async def run_capture(
    duration: float,
    on_event: Callable[[dict], Awaitable[None]],
) -> None:
    """
    Full ADS-B pipeline:
      1. Capture IQ (blocking, runs in thread)
      2. Compute envelope (blocking, runs in thread)
      3. Decode — preamble detection loop calling adsb low-level functions,
         broadcasting each aircraft update via on_event as it's found.

    on_event: async callable that receives a dict and sends it to the client.
    """
    global aircraft_state

    config = PROTOCOLS["adsb"]
    device = RX_SERIAL

    # ── Phase 1: Capture ──────────────────────────────────────────────────────
    await on_event({"type": "status", "phase": "capturing",
                    "duration": duration, "device": device})

    iq_data: np.ndarray | None = await asyncio.to_thread(
        _adsb.capture_iq, config, duration, device
    )

    if iq_data is None or len(iq_data) < 1000:
        await on_event({"type": "error", "message": "Capture failed or too short"})
        return

    # ── Phase 2: Envelope ─────────────────────────────────────────────────────
    await on_event({"type": "status", "phase": "computing_envelope",
                    "samples": int(len(iq_data))})

    envelope: np.ndarray = await asyncio.to_thread(
        _adsb.compute_envelope, iq_data
    )

    # ── Phase 3: Decode (with per-message broadcast) ──────────────────────────
    await on_event({"type": "status", "phase": "decoding"})

    local_aircraft: dict = {}
    msg_count = 0
    crc_pass = 0

    # Run the heavy decode loop in a thread, but yield aircraft updates
    # by running it in chunks isn't practical with the existing loop structure.
    # Instead: run _downsample + full loop in executor, collect results, then
    # broadcast. We get structured data back by using decode_message with our
    # own aircraft dict.
    def _decode_all():
        nonlocal msg_count, crc_pass
        sample_rate = config["sample_rate"]
        spu = sample_rate / 1_000_000
        half_bit_samples = max(int(round(0.5 * spu)), 1)

        hb = _adsb._downsample_to_halfbits(envelope, half_bit_samples)

        preamble_hb = 16
        msg_hb = _adsb.LONG_MSG_BITS * 2

        sorted_hb = np.sort(hb[::10])
        noise_floor = sorted_hb[int(len(sorted_hb) * 0.7)]
        threshold = noise_floor * 1.5

        hp = np.array([0, 2, 7, 9])
        lp = np.array([1, 3, 4, 5, 6, 8, 10, 11, 12, 13, 14, 15])

        updates = []  # list of (icao, aircraft_snapshot) after each new message
        i = 0
        end = len(hb) - preamble_hb - msg_hb

        while i < end:
            if hb[i] < threshold:
                i += 1
                continue

            pvals = hb[i:i + preamble_hb]
            high_mean = pvals[hp].mean()
            low_mean = pvals[lp].mean()

            if high_mean < threshold or high_mean / max(low_mean, 0.1) < 2.0:
                i += 1
                continue

            mid = (high_mean + low_mean) / 2
            if np.any(pvals[hp] < mid):
                i += 1
                continue

            bit_start = i + preamble_hb
            bit_end = bit_start + msg_hb
            if bit_end > len(hb):
                i += 1
                continue

            msg_hb_vals = hb[bit_start:bit_end]
            bit_pairs = msg_hb_vals.reshape(_adsb.LONG_MSG_BITS, 2)
            bits = (bit_pairs[:, 0] > bit_pairs[:, 1]).astype(np.uint8)
            msg_bytes = _adsb.bits_to_bytes(bits.tolist())

            if _adsb.check_crc(msg_bytes):
                crc_pass += 1
                result = _adsb.decode_message(msg_bytes, local_aircraft)
                if result:
                    msg_count += 1
                    icao = f"{msg_bytes[1]:02X}{msg_bytes[2]:02X}{msg_bytes[3]:02X}"
                    ac = local_aircraft[icao]
                    updates.append((icao, {
                        "icao":     icao,
                        "callsign": ac.get("callsign"),
                        "alt":      ac.get("alt"),
                        "lat":      ac.get("lat"),
                        "lon":      ac.get("lon"),
                        "speed":    ac.get("speed"),
                        "heading":  ac.get("heading"),
                        "last_seen": time.time(),
                    }))
                i = bit_end
            else:
                i += 1

        return updates

    updates = await asyncio.to_thread(_decode_all)

    # ── Broadcast each aircraft update ────────────────────────────────────────
    # Deduplicate: keep only the last update per ICAO so the client gets
    # the most-complete record for each aircraft, then broadcast them.
    seen: dict[str, dict] = {}
    for icao, snap in updates:
        seen[icao] = snap

    aircraft_state.clear()
    aircraft_state.update(seen)

    for snap in seen.values():
        await on_event({"type": "aircraft", **snap})
        await asyncio.sleep(0)  # yield between sends

    await on_event({
        "type": "done",
        "aircraft_count": len(seen),
        "msg_count": msg_count,
        "crc_pass": crc_pass,
    })

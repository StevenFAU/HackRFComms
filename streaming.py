"""
HackRFComs - Streaming Demodulator
Uses pyhackrf2 for real-time sample access. Demodulates on a rolling buffer
and returns the moment a valid frame is found.

Note: pyhackrf2 currently only works on device 0 due to libusb indexing.
Device 1 falls back to hackrf_transfer file capture.
"""

import struct
import time
import os
import subprocess
import numpy as np
from scipy import signal as dsp
from config import (
    SAMPLE_RATE, SAMPLES_PER_SYMBOL,
    CENTER_FREQ, LNA_GAIN, VGA_GAIN, SYNC_WORD
)
from modulation import CARRIER_OFFSET, _crc16, demodulate

# Pre-compute filter coefficients
_B, _A = dsp.butter(4, 30_000 / (SAMPLE_RATE / 2), btype='low')
_SYNC_BITS = np.unpackbits(np.frombuffer(SYNC_WORD, dtype=np.uint8))
SPS = SAMPLES_PER_SYMBOL

# Device 0 serial — the one pyhackrf2 can open
_DEVICE_0_SERIAL = None
try:
    from pyhackrf2 import HackRF as _HackRF
    _serials = _HackRF.enumerate()
    _DEVICE_0_SERIAL = _serials[0] if _serials else None
except Exception:
    _DEVICE_0_SERIAL = None


def _try_decode_bits(bits: np.ndarray) -> bytes | None:
    """Search for sync word and decode frame from bit array."""
    sync_len = len(_SYNC_BITS)
    for i in range(len(bits) - sync_len - 8):
        if np.array_equal(bits[i:i + sync_len], _SYNC_BITS):
            pos = i + sync_len
            if pos + 8 > len(bits):
                return None
            length = int(np.packbits(bits[pos:pos + 8])[0])
            need = 8 + length * 8 + 16
            if pos + need > len(bits):
                return None
            raw = np.packbits(bits[pos:pos + need]).tobytes()
            payload = raw[1:1 + length]
            crc_got = struct.unpack("<H", raw[1 + length:1 + length + 2])[0]
            if crc_got == _crc16(payload):
                return payload
    return None


def _demod_and_decode(env: np.ndarray, noise_floor: float,
                      peak: float) -> bytes | None:
    """Try decoding from an envelope buffer with phase search."""
    threshold = noise_floor + (peak - noise_floor) * 0.3
    n_env = len(env)
    for phase in range(0, SPS, SPS // 5):
        indices = np.arange(phase + SPS // 2, n_env, SPS)
        indices = indices[indices < n_env]
        if len(indices) < 80:
            continue
        sampled = env[indices]
        bits = (sampled > threshold).astype(np.uint8)
        result = _try_decode_bits(bits)
        if result is not None:
            return result
    return None


def stream_receive_pyhackrf(timeout: float = 5.0) -> bytes | None:
    """
    Stream-receive using pyhackrf2 on device 0.
    Reads samples in chunks, demodulates in real-time,
    returns the first valid frame found.
    """
    from pyhackrf2 import HackRF

    hrf = HackRF(device_index=0)
    hrf.sample_rate = SAMPLE_RATE
    hrf.center_freq = CENTER_FREQ
    hrf.lna_gain = LNA_GAIN
    hrf.vga_gain = VGA_GAIN
    hrf.amplifier_on = True

    # Filter state
    zi = dsp.lfilter_zi(_B, _A).astype(np.complex128) * 0

    # Envelope accumulator
    env_buffer = np.array([], dtype=np.float64)
    noise_floor = None
    signal_seen = False

    chunk_size = 100_000  # ~50ms of data per read
    start_time = time.time()

    try:
        # Read initial chunk for noise floor
        samples = hrf.read_samples(chunk_size)
        # pyhackrf2 returns complex128 normalized to [-1, 1]
        # Mix down
        t = np.arange(len(samples), dtype=np.float64) / SAMPLE_RATE
        mixed = samples * np.exp(-1j * 2 * np.pi * CARRIER_OFFSET * t)
        filtered, zi = dsp.lfilter(_B, _A, mixed, zi=zi)
        env = np.abs(filtered)
        noise_floor = np.median(env)
        t_offset = len(samples)

        while time.time() - start_time < timeout:
            samples = hrf.read_samples(chunk_size)

            # Mix down
            t = (np.arange(len(samples)) + t_offset).astype(np.float64) / SAMPLE_RATE
            mixed = samples * np.exp(-1j * 2 * np.pi * CARRIER_OFFSET * t)
            t_offset += len(samples)

            # LPF
            filtered, zi = dsp.lfilter(_B, _A, mixed, zi=zi)
            env = np.abs(filtered)

            chunk_peak = np.max(env)
            threshold = noise_floor * 3

            if chunk_peak > threshold:
                if not signal_seen:
                    signal_seen = True
                    env_buffer = np.array([], dtype=np.float64)

                env_buffer = np.concatenate([env_buffer, env])

                if len(env_buffer) >= 112 * SPS:
                    full_peak = np.max(env_buffer)
                    result = _demod_and_decode(env_buffer, noise_floor, full_peak)
                    if result is not None:
                        return result

            elif signal_seen:
                # Signal ended — last try
                env_buffer = np.concatenate([env_buffer, env])
                full_peak = np.max(env_buffer)
                result = _demod_and_decode(env_buffer, noise_floor, full_peak)
                if result is not None:
                    return result

                if len(env_buffer) > SPS * 5000:
                    signal_seen = False
                    env_buffer = np.array([], dtype=np.float64)

            if len(env_buffer) > SPS * 10000:
                env_buffer = env_buffer[-SPS * 5000:]

    finally:
        try:
            hrf.stop_rx()
        except Exception:
            pass
        # Don't call hrf.close() — segfaults in pyhackrf2
        del hrf

    return None


def stream_receive_file(serial: str, duration: float = 3.0) -> bytes | None:
    """
    Fallback: capture to file and demodulate.
    Used for devices that can't use pyhackrf2.
    """
    path = f"/tmp/hackrf_stream_{os.getpid()}.iq"
    cmd = [
        "hackrf_transfer", "-d", serial, "-r", path,
        "-f", str(CENTER_FREQ), "-s", str(SAMPLE_RATE),
        "-l", str(LNA_GAIN), "-g", str(VGA_GAIN), "-a", "1",
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        return None
    time.sleep(duration)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    try:
        iq_data = np.fromfile(path, dtype=np.int8)
    except FileNotFoundError:
        return None
    if len(iq_data) < 1000:
        return None
    return demodulate(iq_data)


def stream_receive(serial: str, timeout: float = 5.0) -> bytes | None:
    """
    Smart dispatch: use pyhackrf2 streaming if this is device 0,
    otherwise fall back to file-based capture.
    """
    if _DEVICE_0_SERIAL and serial.endswith(_DEVICE_0_SERIAL[-16:]):
        return stream_receive_pyhackrf(timeout=timeout)
    else:
        return stream_receive_file(serial, duration=min(timeout, 3.0))


if __name__ == "__main__":
    import sys
    from config import RX_SERIAL
    serial = sys.argv[1] if len(sys.argv) > 1 else RX_SERIAL
    print(f"Streaming receive on {serial}, timeout 10s...")
    result = stream_receive(serial, timeout=10.0)
    if result:
        print(f"Decoded: {result}")
    else:
        print("No frame found.")

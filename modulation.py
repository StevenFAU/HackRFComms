"""
HackRFComs - OOK Modulation / Demodulation
On-Off Keying: carrier present = 1, carrier absent = 0.
"""

import struct
import numpy as np
from scipy import signal as dsp
from config import SAMPLES_PER_SYMBOL, SAMPLE_RATE, PREAMBLE, SYNC_WORD

# Offset carrier so the signal isn't sitting at DC in baseband
CARRIER_OFFSET = 100_000  # 100 kHz

# TX amplitude — must stay within int8 range [-128, 127]
TX_AMPLITUDE = 120
assert TX_AMPLITUDE <= 127, f"TX_AMPLITUDE {TX_AMPLITUDE} would overflow int8"


def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def build_frame(payload: bytes) -> bytes:
    """PREAMBLE + SYNC + LEN(1) + PAYLOAD + CRC16."""
    if len(payload) > 255:
        raise ValueError("Max 255 bytes")
    return PREAMBLE + SYNC_WORD + struct.pack("B", len(payload)) + payload + struct.pack("<H", _crc16(payload))


def frame_to_iq(frame: bytes) -> np.ndarray:
    """OOK-modulate a frame into interleaved int8 IQ samples."""
    bits = np.unpackbits(np.frombuffer(frame, dtype=np.uint8))
    envelope = np.repeat(bits, SAMPLES_PER_SYMBOL).astype(np.float64)

    t = np.arange(len(envelope), dtype=np.float64) / SAMPLE_RATE
    carrier_i = np.cos(2 * np.pi * CARRIER_OFFSET * t) * TX_AMPLITUDE
    carrier_q = np.sin(2 * np.pi * CARRIER_OFFSET * t) * TX_AMPLITUDE

    sig_i = carrier_i * envelope
    sig_q = carrier_q * envelope

    # Check for clipping before cast
    if np.any(np.abs(sig_i) > 127) or np.any(np.abs(sig_q) > 127):
        raise OverflowError(f"IQ samples exceed int8 range — lower TX_AMPLITUDE (currently {TX_AMPLITUDE})")

    iq = np.empty(len(envelope) * 2, dtype=np.int8)
    iq[0::2] = sig_i.astype(np.int8)
    iq[1::2] = sig_q.astype(np.int8)

    # Silent tail between repeats
    tail = np.zeros(SAMPLES_PER_SYMBOL * 32, dtype=np.int8)
    return np.concatenate([iq, tail])


def demodulate(iq_data: np.ndarray) -> bytes | None:
    """
    Mix down to carrier offset, LPF, envelope detect, recover symbol timing,
    find sync word, extract and verify payload.
    """
    i_raw = iq_data[0::2].astype(np.float64)
    q_raw = iq_data[1::2].astype(np.float64)

    # Mix down: shift carrier offset to DC
    t = np.arange(len(i_raw), dtype=np.float64) / SAMPLE_RATE
    csig = i_raw + 1j * q_raw
    mixed = csig * np.exp(-1j * 2 * np.pi * CARRIER_OFFSET * t)

    # Low-pass filter
    b, a = dsp.butter(4, 30_000 / (SAMPLE_RATE / 2), btype='low')
    filt = dsp.filtfilt(b, a, mixed)
    env = np.abs(filt)

    peak = np.max(env)
    if peak < 5.0:
        print(f"  [demod] No signal (peak={peak:.1f})")
        return None

    # Adaptive threshold: use noise floor + margin instead of peak-relative.
    # Estimate noise as the median (most of the capture is silence).
    noise_floor = np.median(env)
    threshold = noise_floor + (peak - noise_floor) * 0.3
    above = np.where(env > threshold)[0]
    if len(above) == 0:
        return None
    burst_start = above[0]

    # Try all possible symbol phase offsets within one symbol period
    # to find the best alignment
    SPS = SAMPLES_PER_SYMBOL

    for phase in range(0, SPS, SPS // 10):
        # Sample envelope at symbol centers
        offset = burst_start - SPS // 2 + phase
        offset = max(0, offset)
        indices = np.arange(offset + SPS // 2, len(env), SPS)
        if len(indices) < 100:
            continue
        sampled = env[indices]
        bits = (sampled > threshold).astype(np.uint8)

        result = _try_decode(bits)
        if result is not None:
            return result

    return None


def _try_decode(bits: np.ndarray) -> bytes | None:
    """Search for sync word in bit array and decode the frame."""
    sync_bits = np.unpackbits(np.frombuffer(SYNC_WORD, dtype=np.uint8))
    for i in range(len(bits) - len(sync_bits) - 8):
        if np.array_equal(bits[i:i + len(sync_bits)], sync_bits):
            pos = i + len(sync_bits)
            if pos + 8 > len(bits):
                continue
            length = int(np.packbits(bits[pos:pos + 8])[0])
            need = 8 + length * 8 + 16
            if pos + need > len(bits):
                continue
            raw = np.packbits(bits[pos:pos + need]).tobytes()
            payload = raw[1:1 + length]
            crc_got = struct.unpack("<H", raw[1 + length:1 + length + 2])[0]
            crc_want = _crc16(payload)
            if crc_got == crc_want:
                return payload
    return None

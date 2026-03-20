"""
HackRFComs - OOK Modulation / Demodulation
Simple On-Off Keying: carrier present = 1, carrier absent = 0.
"""

import struct
import numpy as np
from config import SAMPLES_PER_SYMBOL, PREAMBLE, SYNC_WORD


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


def build_frame(message: bytes) -> bytes:
    """Build a framed packet: PREAMBLE + SYNC + LEN + PAYLOAD + CRC16."""
    if len(message) > 255:
        raise ValueError("Message too long (max 255 bytes)")
    length = struct.pack("B", len(message))
    crc = struct.pack("<H", _crc16(message))
    return PREAMBLE + SYNC_WORD + length + message + crc


def frame_to_iq(frame: bytes) -> np.ndarray:
    """
    Convert a byte frame to IQ samples using OOK modulation.
    Bit=1 -> carrier tone (I=127, Q=0), Bit=0 -> silence (I=0, Q=0).
    Output is interleaved int8 IQ pairs ready for HackRF.
    """
    bits = np.unpackbits(np.frombuffer(frame, dtype=np.uint8))
    symbols = np.repeat(bits, SAMPLES_PER_SYMBOL)

    # IQ as interleaved int8: [I0, Q0, I1, Q1, ...]
    iq = np.zeros(len(symbols) * 2, dtype=np.int8)
    iq[0::2] = (symbols * 127).astype(np.int8)  # I channel
    # Q stays 0 for simple OOK

    # Add a small silent tail so the receiver can detect end-of-burst
    tail = np.zeros(SAMPLES_PER_SYMBOL * 16, dtype=np.int8)
    return np.concatenate([iq, tail])


def iq_to_bits(iq_data: np.ndarray, threshold: float = 0.3) -> np.ndarray:
    """
    Demodulate IQ samples back to bits via envelope detection.
    Returns array of 0s and 1s.
    """
    # iq_data is interleaved int8
    i = iq_data[0::2].astype(np.float32)
    q = iq_data[1::2].astype(np.float32)
    envelope = np.sqrt(i**2 + q**2)

    # Normalize
    peak = np.max(envelope)
    if peak < 1.0:
        return np.array([], dtype=np.uint8)
    envelope /= peak

    # Average over symbol periods to get one sample per symbol
    n_symbols = len(envelope) // SAMPLES_PER_SYMBOL
    if n_symbols == 0:
        return np.array([], dtype=np.uint8)
    trimmed = envelope[:n_symbols * SAMPLES_PER_SYMBOL]
    symbol_energies = trimmed.reshape(n_symbols, SAMPLES_PER_SYMBOL).mean(axis=1)

    bits = (symbol_energies > threshold).astype(np.uint8)
    return bits


def find_sync_and_decode(bits: np.ndarray) -> bytes | None:
    """
    Search for SYNC_WORD in bit stream, then extract and verify the frame.
    Returns the message payload or None if not found / CRC fails.
    """
    # Convert sync word to bit pattern
    sync_bits = np.unpackbits(np.frombuffer(SYNC_WORD, dtype=np.uint8))

    # Slide through looking for sync
    for i in range(len(bits) - len(sync_bits)):
        if np.array_equal(bits[i:i + len(sync_bits)], sync_bits):
            data_start = i + len(sync_bits)
            # Need at least 1 byte for length
            if data_start + 8 > len(bits):
                continue
            length = np.packbits(bits[data_start:data_start + 8])[0]
            total_bits = 8 + (length * 8) + 16  # len + payload + crc
            if data_start + total_bits > len(bits):
                continue

            frame_bits = bits[data_start:data_start + total_bits]
            frame_bytes = np.packbits(frame_bits).tobytes()

            payload = frame_bytes[1:1 + length]
            crc_received = struct.unpack("<H", frame_bytes[1 + length:1 + length + 2])[0]
            crc_computed = _crc16(payload)

            if crc_received == crc_computed:
                return payload
            else:
                print(f"  CRC mismatch: got 0x{crc_received:04X}, expected 0x{crc_computed:04X}")
    return None

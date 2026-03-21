#!/usr/bin/env python3
"""Parse Flipper Zero .sub captures to extract HackRFComs protocol messages."""

import sys
import os
import struct
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SYMBOL_RATE, SYNC_WORD
from modulation import _crc16

SYMBOL_DURATION_US = 1_000_000 // SYMBOL_RATE  # 100 µs


def parse_sub_file(path: str) -> tuple[list[int], int]:
    """Parse a .sub file and return (durations, frequency)."""
    durations = []
    freq = 0

    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("Frequency:"):
                freq = int(line.split(":")[1].strip())
            elif line.startswith("RAW_Data:"):
                values = line.split(":")[1].strip().split()
                durations.extend(int(v) for v in values)

    return durations, freq


def durations_to_bits(durations: list[int], tolerance: float = 0.3) -> list[int]:
    """Convert run-length encoded durations back to a bit array.
    Tolerance: ±30% on symbol duration for jitter handling."""
    bits = []

    for dur in durations:
        val = 1 if dur > 0 else 0
        abs_dur = abs(dur)

        # Round to nearest number of symbols
        num_bits = round(abs_dur / SYMBOL_DURATION_US)

        # Sanity checks
        if num_bits == 0:
            continue
        if num_bits > 500:
            # Long gap — treat as frame separator, insert some zeros
            bits.extend([0] * 20)
            continue

        # Tolerance check: verify the duration is within ±tolerance of expected
        expected = num_bits * SYMBOL_DURATION_US
        if abs(abs_dur - expected) / expected > tolerance:
            # Still use the rounded value, but it's noisy
            pass

        bits.extend([val] * num_bits)

    return bits


def find_and_decode(bits: list[int]) -> list[str]:
    """Search for sync words in the bitstream and decode messages."""
    sync_bits = np.unpackbits(np.frombuffer(SYNC_WORD, dtype=np.uint8)).tolist()
    sync_len = len(sync_bits)

    messages = []
    i = 0

    while i < len(bits) - sync_len - 8:
        # Look for sync word
        if bits[i:i + sync_len] == sync_bits:
            pos = i + sync_len

            # Extract length byte
            if pos + 8 > len(bits):
                i += 1
                continue
            length = 0
            for j in range(8):
                length = (length << 1) | bits[pos + j]
            pos += 8

            if length == 0 or length > 255:
                i += 1
                continue

            # Extract payload + CRC (2 bytes)
            need = length * 8 + 16
            if pos + need > len(bits):
                i += 1
                continue

            # Convert bits to bytes
            raw_bits = bits[pos:pos + need]
            raw_bytes = bytearray()
            for j in range(0, len(raw_bits), 8):
                byte_val = 0
                for k in range(8):
                    byte_val = (byte_val << 1) | raw_bits[j + k]
                raw_bytes.append(byte_val)

            payload = bytes(raw_bytes[:length])
            crc_got = struct.unpack("<H", bytes(raw_bytes[length:length + 2]))[0]
            crc_want = _crc16(payload)

            if crc_got == crc_want:
                decoded = payload.decode("utf-8", errors="replace")
                messages.append(decoded)
                print(f"[Flipper] Found sync word at bit {i}")
                print(f"[Flipper] Payload ({length} bytes): {decoded}")
                print(f"[Flipper] CRC: valid (0x{crc_got:04X})")
                # Skip past this message
                i = pos + need
                continue

            i += 1
        else:
            i += 1

    return messages


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/flipper_decode.py <file.sub>")
        print("Example: python3 tools/flipper_decode.py captured_signal.sub")
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)

    durations, freq = parse_sub_file(path)
    print(f"[Flipper] Loaded {len(durations)} raw durations")
    print(f"[Flipper] Frequency: {freq / 1e6:.3f} MHz")

    bits = durations_to_bits(durations)
    print(f"[Flipper] Converted to {len(bits)} bits")

    messages = find_and_decode(bits)

    if not messages:
        print("[Flipper] No valid messages found")
    else:
        unique = list(dict.fromkeys(messages))
        print(f"\n[Flipper] Decoded {len(messages)} message(s) ({len(unique)} unique)")
        for msg in unique:
            print(f"  → {msg}")


if __name__ == "__main__":
    main()

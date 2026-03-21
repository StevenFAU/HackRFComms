#!/usr/bin/env python3
"""Generate Flipper Zero .sub files containing HackRFComs protocol messages."""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CENTER_FREQ, SYMBOL_RATE
from modulation import build_frame

SYMBOL_DURATION_US = 1_000_000 // SYMBOL_RATE  # 100 µs at 10 ksym/s


def frame_to_sub_data(frame: bytes) -> list[int]:
    """Convert frame bytes to run-length encoded durations for .sub file."""
    bits = np.unpackbits(np.frombuffer(frame, dtype=np.uint8))

    durations = []
    current_val = int(bits[0])
    current_run = 1

    for bit in bits[1:]:
        bit = int(bit)
        if bit == current_val:
            current_run += 1
        else:
            duration = current_run * SYMBOL_DURATION_US
            durations.append(duration if current_val == 1 else -duration)
            current_val = bit
            current_run = 1

    # Final run
    duration = current_run * SYMBOL_DURATION_US
    durations.append(duration if current_val == 1 else -duration)

    # Add trailing silence (1ms)
    if durations[-1] > 0:
        durations.append(-1000)

    return durations


def write_sub_file(durations: list[int], path: str, freq: int = CENTER_FREQ):
    """Write a Flipper .sub file."""
    with open(path, "w") as f:
        f.write("Filetype: Flipper SubGhz RAW File\n")
        f.write("Version: 1\n")
        f.write(f"Frequency: {freq}\n")
        f.write("Preset: FuriHalSubGhzPresetOok650Async\n")
        f.write("Protocol: RAW\n")

        # Split into lines of max ~500 values (Flipper has line length limits)
        chunk_size = 500
        for i in range(0, len(durations), chunk_size):
            chunk = durations[i:i + chunk_size]
            f.write("RAW_Data: " + " ".join(str(d) for d in chunk) + "\n")

    print(f"Saved: {path}")
    print(f"Copy to Flipper SD card: /ext/subghz/ directory")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/flipper_encode.py <message> [output.sub]")
        print("Example: python3 tools/flipper_encode.py 'Hello from Flipper!'")
        sys.exit(1)

    message = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else "iq_dumps/flipper_tx.sub"

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

    frame = build_frame(message.encode())
    durations = frame_to_sub_data(frame)

    print(f"Message: {message!r}")
    print(f"Frame: {len(frame)} bytes ({len(frame) * 8} bits)")
    print(f"Duration: {sum(abs(d) for d in durations) / 1000:.1f} ms")

    # Repeat frame 5x (same as demo.py) with 2ms gap between repeats
    repeated = []
    for i in range(5):
        repeated.extend(durations)
        if i < 4:
            repeated.append(-2000)  # 2ms gap between repeats

    write_sub_file(repeated, output)


if __name__ == "__main__":
    main()

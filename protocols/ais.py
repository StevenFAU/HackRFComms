"""
HackRFComs — AIS Marine Vessel Tracker
Decodes AIS (Automatic Identification System) transmissions at 162 MHz.

Pipeline: IQ capture -> FM discriminator -> lowpass -> decimate (5 samp/bit)
          -> bit slice -> NRZI decode -> HDLC deframe -> destuff -> CRC -> parse

AIS channels:
  AIS1: 161.975 MHz (-25 kHz offset from 162.000 center)
  AIS2: 162.025 MHz (+25 kHz offset from 162.000 center)

ANTENNA REQUIREMENT: AIS at 162 MHz needs a quarter-wave antenna of ~46 cm.
The stock HackRF telescopic antenna (~20-25 cm) is too short — it's tuned for
~300-375 MHz. For reliable AIS reception, use a 46 cm dipole or take the
Portapack near a window/outside with the antenna fully extended.

Status: Decoder implemented but not yet validated (antenna too short for signal).
        Validate with Portapack AIS app first to confirm signal, then test decoder.
"""

import os
import sys
import time
import subprocess
import numpy as np

# AIS constants
AIS_BAUD = 9600
HDLC_FLAG = 0x7E  # 01111110

# CRC-16-CCITT (poly 0x1021, init 0xFFFF)
CRC_POLY = 0x1021
CRC_INIT = 0xFFFF

IQ_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "iq_dumps")


def capture_iq(config: dict, duration: float, device: str) -> np.ndarray | None:
    """Capture IQ data from HackRF at 162 MHz."""
    os.makedirs(IQ_DIR, exist_ok=True)
    path = os.path.join(IQ_DIR, "ais_capture.iq")

    cmd = [
        "hackrf_transfer", "-d", device, "-r", path,
        "-f", str(config["center_freq"]),
        "-s", str(config["sample_rate"]),
        "-l", str(config["lna_gain"]),
        "-g", str(config["vga_gain"]),
        "-a", "1",
    ]

    print(f"[AIS] Capturing {duration:.0f}s at {config['center_freq']/1e6:.3f} MHz "
          f"({config['sample_rate']/1e6:.0f} MS/s)...")

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        print("[AIS] hackrf_transfer not found — is it installed?")
        return None

    time.sleep(duration)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    ret = proc.returncode
    if ret and ret != -15:
        output = proc.stdout.read().decode(errors="replace").strip()
        print(f"[AIS] hackrf_transfer exited {ret}: {output}")
        return None

    try:
        data = np.fromfile(path, dtype=np.int8)
        print(f"[AIS] Captured {len(data)} bytes ({len(data)/config['sample_rate']/2:.1f}s)")
        return data
    except FileNotFoundError:
        print("[AIS] No capture file produced")
        return None


def crc16_ccitt(data: bytes) -> int:
    """CRC-16-CCITT (poly 0x1021, init 0xFFFF)."""
    crc = CRC_INIT
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ CRC_POLY
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def ais_char(val: int) -> str:
    """Convert 6-bit AIS value to ASCII character."""
    if val < 40:
        return chr(val + 48)
    else:
        return chr(val + 56)


def bits_to_bytes(bits: list[int]) -> bytes:
    """Convert a list of bits to bytes (MSB first)."""
    n_bytes = len(bits) // 8
    result = bytearray(n_bytes)
    for i in range(n_bytes):
        val = 0
        for j in range(8):
            val = (val << 1) | bits[i * 8 + j]
        result[i] = val
    return bytes(result)


def extract_bits(bits: list[int], start: int, length: int) -> int:
    """Extract an unsigned integer from a bit array."""
    val = 0
    for i in range(start, min(start + length, len(bits))):
        val = (val << 1) | bits[i]
    return val


def extract_signed(bits: list[int], start: int, length: int) -> int:
    """Extract a signed integer (two's complement) from a bit array."""
    val = extract_bits(bits, start, length)
    if val >= (1 << (length - 1)):
        val -= (1 << length)
    return val


def extract_string(bits: list[int], start: int, n_chars: int) -> str:
    """Extract a string of 6-bit AIS characters."""
    chars = []
    for i in range(n_chars):
        val = extract_bits(bits, start + i * 6, 6)
        chars.append(ais_char(val))
    return "".join(chars).rstrip("@").strip()


def nrzi_decode(bits: list[int]) -> list[int]:
    """Decode NRZI: 0 = transition, 1 = no transition.
    Output: same as previous = 1, different = 0."""
    decoded = []
    for i in range(1, len(bits)):
        decoded.append(1 if bits[i] == bits[i - 1] else 0)
    return decoded


def bit_destuff(bits: list[int]) -> list[int] | None:
    """Remove bit stuffing: after 5 consecutive 1s, remove the following 0.
    Returns None if stuffing violation found."""
    result = []
    ones_count = 0
    i = 0
    while i < len(bits):
        if ones_count == 5:
            if i < len(bits) and bits[i] == 0:
                ones_count = 0
                i += 1
                continue
            elif i < len(bits) and bits[i] == 1:
                return result
            else:
                return result
        result.append(bits[i])
        if bits[i] == 1:
            ones_count += 1
        else:
            ones_count = 0
        i += 1
    return result


def find_hdlc_frames(bits: list[int]) -> list[list[int]]:
    """Find HDLC frames delimited by 0x7E flags (01111110) in the bitstream."""
    flag = [0, 1, 1, 1, 1, 1, 1, 0]
    frames = []

    flag_positions = []
    for i in range(len(bits) - 7):
        if bits[i:i + 8] == flag:
            flag_positions.append(i)

    for idx in range(len(flag_positions) - 1):
        start = flag_positions[idx] + 8
        end = flag_positions[idx + 1]
        frame_bits = bits[start:end]
        if len(frame_bits) >= 40:
            frames.append(frame_bits)

    return frames


def decode_ais_message(payload_bits: list[int], vessels: dict) -> str | None:
    """Decode an AIS message from its payload bits. Returns formatted string."""
    if len(payload_bits) < 38:
        return None

    msg_type = extract_bits(payload_bits, 0, 6)
    mmsi = extract_bits(payload_bits, 8, 30)

    if mmsi == 0:
        return None

    mmsi_str = f"{mmsi:09d}"

    if mmsi_str not in vessels:
        vessels[mmsi_str] = {"name": None, "type": None, "lat": None, "lon": None,
                             "speed": None, "course": None, "heading": None, "dest": None}
    v = vessels[mmsi_str]
    v["type"] = msg_type

    parts = [f"[AIS] MMSI:{mmsi_str}  Type:{msg_type}"]

    if msg_type in (1, 2, 3):
        if len(payload_bits) < 168:
            return None
        sog = extract_bits(payload_bits, 46, 10)
        lon = extract_signed(payload_bits, 61, 28)
        lat = extract_signed(payload_bits, 89, 27)
        cog = extract_bits(payload_bits, 116, 12)
        hdg = extract_bits(payload_bits, 128, 9)

        speed = sog / 10.0
        lon_deg = lon / 600000.0
        lat_deg = lat / 600000.0
        course = cog / 10.0

        if abs(lat_deg) > 90 or abs(lon_deg) > 180:
            return None
        if sog == 1023:
            speed = None

        v["speed"] = speed
        v["course"] = course
        v["lat"] = lat_deg
        v["lon"] = lon_deg
        if hdg < 360:
            v["heading"] = hdg

        if lat_deg != 0 or lon_deg != 0:
            parts.append(f"Lat:{lat_deg:.4f}")
            parts.append(f"Lon:{lon_deg:.4f}")
        if speed is not None:
            parts.append(f"Speed:{speed:.1f}kt")
        if course < 360:
            parts.append(f"Course:{course:.0f}°")
        if hdg < 360:
            parts.append(f"Heading:{hdg}°")

    elif msg_type == 5:
        if len(payload_bits) < 424:
            return None
        name = extract_string(payload_bits, 112, 20)
        dest = extract_string(payload_bits, 302, 20)
        v["name"] = name if name else v["name"]
        v["dest"] = dest if dest else v["dest"]
        if name:
            parts.append(f"Name:{name}")
        if dest:
            parts.append(f"Dest:{dest}")

    elif msg_type == 18:
        if len(payload_bits) < 168:
            return None
        sog = extract_bits(payload_bits, 46, 10)
        lon = extract_signed(payload_bits, 57, 28)
        lat = extract_signed(payload_bits, 85, 27)
        cog = extract_bits(payload_bits, 112, 12)

        speed = sog / 10.0
        lon_deg = lon / 600000.0
        lat_deg = lat / 600000.0
        course = cog / 10.0

        if abs(lat_deg) > 90 or abs(lon_deg) > 180:
            return None

        v["speed"] = speed
        v["course"] = course
        v["lat"] = lat_deg
        v["lon"] = lon_deg

        if lat_deg != 0 or lon_deg != 0:
            parts.append(f"Lat:{lat_deg:.4f}")
            parts.append(f"Lon:{lon_deg:.4f}")
        if speed is not None:
            parts.append(f"Speed:{speed:.1f}kt")
        if course < 360:
            parts.append(f"Course:{course:.0f}°")

    elif msg_type == 24:
        part_num = extract_bits(payload_bits, 38, 2)
        if part_num == 0 and len(payload_bits) >= 160:
            name = extract_string(payload_bits, 40, 20)
            v["name"] = name if name else v["name"]
            if name:
                parts.append(f"Name:{name}")
        else:
            return None

    else:
        if len(parts) <= 1:
            return None

    if len(parts) <= 1:
        return None

    return "  ".join(parts)


def _decode_channel_bitstream(baseband: np.ndarray, samples_per_bit: int,
                              vessels: dict) -> tuple[list[str], int, int, int, int]:
    """Try all phase offsets and both polarities on a baseband signal.
    Returns (messages, best_phase, frame_count, crc_pass, crc_fail)."""
    best_messages = []
    best_phase = 0
    best_crc_pass = 0
    best_crc_fail = 0
    best_frame_count = 0

    for invert in [False, True]:
        for phase_offset in range(samples_per_bit):
            bit_samples = baseband[phase_offset::samples_per_bit]
            if invert:
                raw_bits = (bit_samples < 0).astype(int).tolist()
            else:
                raw_bits = (bit_samples > 0).astype(int).tolist()

            nrzi_bits = nrzi_decode(raw_bits)
            frames = find_hdlc_frames(nrzi_bits)

            messages = []
            crc_pass = 0
            crc_fail = 0

            for frame_bits in frames:
                destuffed = bit_destuff(frame_bits)
                if destuffed is None or len(destuffed) < 56:
                    continue

                payload_bits = destuffed[:-16]
                crc_bits = destuffed[-16:]

                if len(payload_bits) % 8 != 0 or len(crc_bits) != 16:
                    continue

                # AIS HDLC sends bits LSB first within each byte.
                # Reverse bit order within each byte before CRC and decode.
                payload_bits_msb = []
                for i in range(0, len(payload_bits), 8):
                    payload_bits_msb.extend(payload_bits[i:i+8][::-1])
                crc_bits_msb = []
                for i in range(0, 16, 8):
                    crc_bits_msb.extend(crc_bits[i:i+8][::-1])

                payload_bytes = bits_to_bytes(payload_bits_msb)
                crc_bytes = bits_to_bytes(crc_bits_msb)
                received_crc = (crc_bytes[0] << 8) | crc_bytes[1]

                computed = crc16_ccitt(payload_bytes)
                residual = crc16_ccitt(payload_bytes + crc_bytes)

                if (residual == 0 or residual == 0x1D0F or
                    computed == received_crc or
                    computed == (received_crc ^ 0xFFFF)):
                    crc_pass += 1
                    result = decode_ais_message(payload_bits_msb, vessels)
                    if result:
                        messages.append(result)
                else:
                    crc_fail += 1

            if len(messages) > len(best_messages):
                best_messages = messages
                best_phase = phase_offset + (samples_per_bit if invert else 0)
                best_crc_pass = crc_pass
                best_crc_fail = crc_fail
                best_frame_count = len(frames)

    return best_messages, best_phase, best_frame_count, best_crc_pass, best_crc_fail


def demodulate_and_decode(iq_data: np.ndarray, sample_rate: int) -> list[str]:
    """Full AIS demodulation and decoding pipeline.
    Processes both AIS channels (±25 kHz from center) independently."""
    from scipy.signal import butter, filtfilt, resample_poly
    from math import gcd

    i_sig = iq_data[0::2].astype(np.float32)
    q_sig = iq_data[1::2].astype(np.float32)
    signal = i_sig + 1j * q_sig

    print(f"[AIS] {len(signal)} IQ samples at {sample_rate/1e6:.0f} MS/s")

    target_rate = 48000
    samples_per_bit = target_rate // AIS_BAUD  # 5

    channels = [
        ("AIS1", -25000),
        ("AIS2", +25000),
    ]

    all_messages = []
    vessels = {}

    for ch_name, offset_hz in channels:
        print(f"\n[AIS] Processing {ch_name} (offset {offset_hz/1000:+.0f} kHz)...")

        # Frequency-shift channel to baseband
        t = np.arange(len(signal)) / sample_rate
        shifted = signal * np.exp(-1j * 2 * np.pi * offset_hz * t)

        # Lowpass to isolate channel (±8 kHz)
        nyq = sample_rate / 2
        b_lp, a_lp = butter(5, 8000 / nyq, btype='low')
        channel_i = filtfilt(b_lp, a_lp, shifted.real)
        channel_q = filtfilt(b_lp, a_lp, shifted.imag)
        channel = channel_i + 1j * channel_q

        # FM discriminator
        disc = np.angle(channel[1:] * np.conj(channel[:-1]))

        # Decimate to target rate
        g = gcd(sample_rate, target_rate)
        baseband = resample_poly(disc, target_rate // g, sample_rate // g)

        print(f"[AIS] {ch_name}: {len(baseband)} samples at {target_rate} Hz")

        messages, phase, frame_count, crc_pass, crc_fail = \
            _decode_channel_bitstream(baseband, samples_per_bit, vessels)

        print(f"[AIS] {ch_name}: {frame_count} HDLC frames, "
              f"{crc_pass} CRC pass, {crc_fail} CRC fail, "
              f"{len(messages)} decoded (phase={phase})")

        for msg in messages:
            print(msg)

        all_messages.extend(messages)

    # Summary
    print(f"\n[AIS] Total messages decoded: {len(all_messages)}")
    print(f"[AIS] Vessels tracked: {len(vessels)}")

    if vessels:
        print(f"\n[AIS] Vessel summary:")
        print(f"  {'MMSI':<12} {'Name':<20} {'Type':<5} {'Position':<22} {'Speed':<8} {'Course'}")
        for mmsi, v in sorted(vessels.items()):
            name = v['name'] or '—'
            typ = str(v['type']) if v['type'] else '—'
            if v['lat'] is not None and v['lon'] is not None:
                pos = f"{v['lat']:.4f}, {v['lon']:.4f}"
            else:
                pos = '—'
            spd = f"{v['speed']:.1f}kt" if v['speed'] is not None else '—'
            crs = f"{v['course']:.0f}°" if v['course'] is not None else '—'
            print(f"  {mmsi:<12} {name:<20} {typ:<5} {pos:<22} {spd:<8} {crs}")

    if not all_messages:
        print(f"\n[AIS] No messages decoded.")
        print(f"[AIS] NOTE: AIS at 162 MHz requires a ~46 cm quarter-wave antenna.")
        print(f"[AIS] The stock telescopic (~20-25 cm) is tuned for ~300+ MHz.")
        print(f"[AIS] Options: build a 46 cm dipole, or test near a window/outside.")
        print(f"[AIS] Verify signal first with Portapack AIS app at a window.")

    return all_messages


def run(config: dict, duration: float = 10.0, device: str = None):
    """Main entry point called by hackrf.py launcher."""
    if device is None:
        from config import RX_SERIAL
        device = RX_SERIAL

    print(f"[AIS] {config['description']}")
    print(f"[AIS] Device: {device}")
    print(f"[AIS] Duration: {duration}s")
    print(f"[AIS] Channels: AIS1 161.975 MHz / AIS2 162.025 MHz")
    print()

    iq_data = capture_iq(config, duration, device)
    if iq_data is None:
        return

    if len(iq_data) < 1000:
        print("[AIS] Capture too short, no data to decode")
        return

    print("[AIS] Demodulating and decoding...")
    demodulate_and_decode(iq_data, config["sample_rate"])


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import PROTOCOLS, RX_SERIAL

    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    run(PROTOCOLS["ais"], duration=duration, device=RX_SERIAL)

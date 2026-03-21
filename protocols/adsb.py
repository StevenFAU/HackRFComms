"""
HackRFComs — ADS-B Mode S Decoder
Receives and decodes ADS-B Extended Squitter (1090 MHz) from aircraft.

Pipeline: IQ capture -> envelope -> preamble detect -> PPM demod -> CRC -> decode
"""

import os
import sys
import time
import subprocess
import numpy as np

# ADS-B constants
ADSB_FREQ = 1_090_000_000
LONG_MSG_BITS = 112
SHORT_MSG_BITS = 56
CRC_BITS = 24

# Preamble pattern at 2 MS/s (16 samples for 8 µs preamble)
# 1010000101000000 -> high/low for each 0.5 µs at 2 MS/s = 1 sample per 0.5 µs
PREAMBLE_PATTERN = np.array([1, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0], dtype=np.float32)
PREAMBLE_LEN = len(PREAMBLE_PATTERN)

# CRC-24 generator polynomial for Mode S (0x1FFF409)
CRC_POLY = 0xFFF409

# ADS-B character set for callsign decoding
CALLSIGN_CHARS = "#ABCDEFGHIJKLMNOPQRSTUVWXYZ##### ###############0123456789######"

IQ_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "iq_dumps")


def capture_iq(config: dict, duration: float, device: str) -> np.ndarray | None:
    """Capture IQ data from HackRF at 1090 MHz."""
    os.makedirs(IQ_DIR, exist_ok=True)
    path = os.path.join(IQ_DIR, "adsb_capture.iq")

    cmd = [
        "hackrf_transfer", "-d", device, "-r", path,
        "-f", str(config["center_freq"]),
        "-s", str(config["sample_rate"]),
        "-l", str(config["lna_gain"]),
        "-g", str(config["vga_gain"]),
        "-a", "1",
    ]

    print(f"[ADS-B] Capturing {duration:.0f}s at {config['center_freq']/1e6:.0f} MHz "
          f"({config['sample_rate']/1e6:.0f} MS/s)...")

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        print("[ADS-B] hackrf_transfer not found — is it installed?")
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
        print(f"[ADS-B] hackrf_transfer exited {ret}: {output}")
        return None

    try:
        data = np.fromfile(path, dtype=np.int8)
        print(f"[ADS-B] Captured {len(data)} bytes ({len(data)/config['sample_rate']/2:.1f}s)")
        return data
    except FileNotFoundError:
        print("[ADS-B] No capture file produced")
        return None


def compute_envelope(iq_data: np.ndarray) -> np.ndarray:
    """Compute magnitude envelope from interleaved I/Q int8 samples."""
    i = iq_data[0::2].astype(np.float32)
    q = iq_data[1::2].astype(np.float32)
    return np.sqrt(i * i + q * q)


def crc24(msg_bytes: bytes, n_bytes: int) -> int:
    """Compute ADS-B CRC-24 over n_bytes of the message."""
    crc = 0
    for i in range(n_bytes):
        byte = msg_bytes[i]
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= CRC_POLY
    return crc & 0xFFFFFF


def check_crc(msg_bytes: bytes) -> bool:
    """Validate CRC-24 of a Mode S message (112-bit or 56-bit)."""
    n = len(msg_bytes)
    if n == 14:  # 112 bits
        crc = crc24(msg_bytes, 11)
        expected = (msg_bytes[11] << 16) | (msg_bytes[12] << 8) | msg_bytes[13]
        return crc == expected
    elif n == 7:  # 56 bits
        crc = crc24(msg_bytes, 4)
        expected = (msg_bytes[4] << 16) | (msg_bytes[5] << 8) | msg_bytes[6]
        return crc == expected
    return False


def bits_to_bytes(bits: list[int]) -> bytes:
    """Convert list of bits to bytes."""
    n_bytes = len(bits) // 8
    result = bytearray(n_bytes)
    for i in range(n_bytes):
        val = 0
        for j in range(8):
            val = (val << 1) | bits[i * 8 + j]
        result[i] = val
    return bytes(result)


def decode_callsign(msg_bytes: bytes) -> str:
    """Decode aircraft identification (Type 1-4) from DF17 message."""
    # Callsign is encoded in bytes 5-10, 6 bits per character, 8 characters
    chars = []
    # Bits 40-87 contain the callsign (48 bits = 8 chars x 6 bits)
    bits = []
    for b in msg_bytes[5:11]:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)

    for i in range(8):
        idx = 0
        for j in range(6):
            idx = (idx << 1) | bits[i * 6 + j]
        if idx < len(CALLSIGN_CHARS):
            chars.append(CALLSIGN_CHARS[idx])
        else:
            chars.append("?")
    return "".join(chars).rstrip(" #")


def decode_altitude(msg_bytes: bytes) -> int | None:
    """Decode altitude from airborne position message (Type 9-18)."""
    # Altitude is in bits 40-51 (bytes 5-6), with Q-bit at position 47
    alt_bits = ((msg_bytes[5] & 0xFF) << 4) | ((msg_bytes[6] >> 4) & 0x0F)

    # Q-bit is bit 47 (bit 4 of the 12-bit altitude code)
    q_bit = (alt_bits >> 4) & 1

    if q_bit:
        # Remove Q-bit and compute altitude in 25-ft increments
        n = ((alt_bits & 0x1F80) >> 1) | (alt_bits & 0x0F)
        altitude = n * 25 - 1000
        return altitude
    else:
        # Gillham code — less common, return None for now
        return None


def decode_cpr_lat_lon(even_msg: bytes, odd_msg: bytes,
                       most_recent_odd: bool = False) -> tuple[float, float] | None:
    """
    Decode CPR (Compact Position Reporting) latitude/longitude from
    an even/odd message pair. Uses the most recent message as reference
    for best accuracy. Returns (lat, lon) or None.
    """
    import math

    NZ = 15  # Number of latitude zones for airborne positions

    def cpr_nl(lat):
        """Number of longitude zones at a given latitude."""
        if abs(lat) >= 87.0:
            return 1
        return int(math.floor(
            2 * math.pi / math.acos(
                1 - (1 - math.cos(math.pi / (2 * NZ))) /
                math.cos(math.pi * lat / 180) ** 2
            )
        ))

    # Extract CPR encoded lat/lon (17 bits each) from bytes 6-10
    def extract_cpr(msg: bytes):
        # Bits 54-71: encoded latitude (17 bits)
        # Bits 72-89: encoded longitude (17 bits)
        lat_cpr = ((msg[6] & 0x03) << 15) | (msg[7] << 7) | (msg[8] >> 1)
        lon_cpr = ((msg[8] & 0x01) << 16) | (msg[9] << 8) | msg[10]
        return lat_cpr, lon_cpr

    lat_even, lon_even = extract_cpr(even_msg)
    lat_odd, lon_odd = extract_cpr(odd_msg)

    # Normalize to [0, 1)
    lat_even_f = lat_even / 131072.0  # 2^17
    lon_even_f = lon_even / 131072.0
    lat_odd_f = lat_odd / 131072.0
    lon_odd_f = lon_odd / 131072.0

    # Compute latitude zone index
    j = int(math.floor(59 * lat_even_f - 60 * lat_odd_f + 0.5))

    # Latitude
    dlat_even = 360.0 / 60
    dlat_odd = 360.0 / 59

    lat_even_decoded = dlat_even * ((j % 60) + lat_even_f)
    lat_odd_decoded = dlat_odd * ((j % 59) + lat_odd_f)

    if lat_even_decoded >= 270:
        lat_even_decoded -= 360
    if lat_odd_decoded >= 270:
        lat_odd_decoded -= 360

    # Check latitude zone consistency
    if cpr_nl(lat_even_decoded) != cpr_nl(lat_odd_decoded):
        return None

    # Use the most recent message as reference for best accuracy
    if most_recent_odd:
        lat = lat_odd_decoded
        nl = cpr_nl(lat)
        ni = max(nl - 1, 1)
        dlon = 360.0 / ni if ni > 0 else 360.0
        m = int(math.floor(lon_even_f * (nl - 1) - lon_odd_f * nl + 0.5))
        lon = dlon * ((m % ni) + lon_odd_f)
    else:
        lat = lat_even_decoded
        nl = cpr_nl(lat)
        ni = max(nl, 1)
        dlon = 360.0 / ni
        m = int(math.floor(lon_even_f * (nl - 1) - lon_odd_f * nl + 0.5))
        lon = dlon * ((m % ni) + lon_even_f)

    if lon >= 180:
        lon -= 360

    return lat, lon


def decode_velocity(msg_bytes: bytes) -> tuple[float, float] | None:
    """Decode airborne velocity (Type 19) from DF17 message.
    Returns (speed_kt, heading_deg) or None."""
    subtype = msg_bytes[4] & 0x07

    if subtype in (1, 2):
        # Ground speed, east/west and north/south components
        ew_dir = (msg_bytes[5] >> 2) & 1  # 0=east, 1=west
        ew_vel = ((msg_bytes[5] & 0x03) << 8) | msg_bytes[6]
        ns_dir = (msg_bytes[7] >> 7) & 1  # 0=north, 1=south
        ns_vel = ((msg_bytes[7] & 0x7F) << 3) | (msg_bytes[8] >> 5)

        if ew_vel == 0 or ns_vel == 0:
            return None

        ew_vel -= 1
        ns_vel -= 1

        if subtype == 2:  # Supersonic
            ew_vel *= 4
            ns_vel *= 4

        if ew_dir:
            ew_vel = -ew_vel
        if ns_dir:
            ns_vel = -ns_vel

        import math
        speed = math.sqrt(ew_vel ** 2 + ns_vel ** 2)
        heading = math.degrees(math.atan2(ew_vel, ns_vel))
        if heading < 0:
            heading += 360

        return speed, heading

    return None


def decode_message(msg_bytes: bytes, aircraft: dict) -> str | None:
    """Decode a Mode S message and return a formatted string."""
    df = (msg_bytes[0] >> 3) & 0x1F  # Downlink Format

    if df != 17:
        return None  # Only decode DF17 (Extended Squitter)

    icao = f"{msg_bytes[1]:02X}{msg_bytes[2]:02X}{msg_bytes[3]:02X}"
    type_code = (msg_bytes[4] >> 3) & 0x1F

    # Initialize aircraft tracking entry
    if icao not in aircraft:
        aircraft[icao] = {"callsign": None, "alt": None, "lat": None, "lon": None,
                          "speed": None, "heading": None, "even": None, "odd": None}
    ac = aircraft[icao]

    parts = [f"[ADS-B] ICAO:{icao}"]

    if 1 <= type_code <= 4:
        # Aircraft identification
        callsign = decode_callsign(msg_bytes)
        ac["callsign"] = callsign
        parts.append(f"Callsign:{callsign}")

    elif 9 <= type_code <= 18:
        # Airborne position
        alt = decode_altitude(msg_bytes)
        if alt is not None:
            ac["alt"] = alt
            parts.append(f"Alt:{alt}ft")

        # CPR even/odd flag is bit 53 (byte 6, bit 2)
        cpr_odd = (msg_bytes[6] >> 2) & 1
        if cpr_odd:
            ac["odd"] = msg_bytes
        else:
            ac["even"] = msg_bytes

        # Try to decode position if we have both even and odd
        if ac["even"] is not None and ac["odd"] is not None:
            pos = decode_cpr_lat_lon(ac["even"], ac["odd"],
                                     most_recent_odd=bool(cpr_odd))
            if pos:
                ac["lat"], ac["lon"] = pos
                parts.append(f"Lat:{pos[0]:.4f}")
                parts.append(f"Lon:{pos[1]:.4f}")

    elif type_code == 19:
        # Airborne velocity
        vel = decode_velocity(msg_bytes)
        if vel:
            ac["speed"], ac["heading"] = vel
            parts.append(f"Speed:{vel[0]:.0f}kt")
            parts.append(f"Heading:{vel[1]:.0f}")

    else:
        return None  # Skip other type codes

    # Append cached info
    if ac["callsign"] and type_code not in (1, 2, 3, 4):
        parts.insert(1, f"Callsign:{ac['callsign']}")

    if len(parts) <= 1:
        return None

    return "  ".join(parts)


def _downsample_to_halfbits(envelope: np.ndarray, half_bit_samples: int) -> np.ndarray:
    """Downsample envelope to one value per half-bit period (0.5 µs) using averaging.
    This is the key optimization — converts millions of samples to a manageable array."""
    n = len(envelope)
    # Trim to exact multiple of half_bit_samples
    trim = n - (n % half_bit_samples)
    reshaped = envelope[:trim].reshape(-1, half_bit_samples)
    return reshaped.mean(axis=1)


def decode_iq(envelope: np.ndarray, sample_rate: int) -> list[str]:
    """Process envelope to find and decode ADS-B messages."""
    spu = sample_rate / 1_000_000  # samples per µs
    half_bit_samples = max(int(round(0.5 * spu)), 1)  # samples per 0.5 µs

    print(f"[ADS-B] Sample rate: {sample_rate/1e6:.0f} MS/s  "
          f"({spu:.0f} samples/µs, {half_bit_samples} samples/half-bit)")

    # Downsample to half-bit resolution — one value per 0.5 µs
    print("[ADS-B] Downsampling to half-bit resolution...")
    hb = _downsample_to_halfbits(envelope, half_bit_samples)
    print(f"[ADS-B] {len(envelope)} samples -> {len(hb)} half-bit cells")

    # Now everything works in half-bit units:
    # Preamble = 16 half-bits, bit = 2 half-bits, message = 224 half-bits
    preamble_hb = 16
    msg_hb = LONG_MSG_BITS * 2  # 224 half-bits

    # Noise floor from 70th percentile of subsampled data
    sorted_hb = np.sort(hb[::10])
    noise_floor = sorted_hb[int(len(sorted_hb) * 0.7)]
    threshold = noise_floor * 1.5

    print(f"[ADS-B] Noise floor: {noise_floor:.1f}  Threshold: {threshold:.1f}")

    aircraft = {}
    messages = []
    crc_pass = 0
    crc_fail = 0
    preamble_hits = 0

    # Preamble pattern in half-bit units:
    # 1,0,1,0,0,0,0,1,0,1,0,0,0,0,0,0
    # High positions: 0, 2, 7, 9
    # Low positions: 1, 3, 4, 5, 6, 8, 10, 11, 12, 13, 14, 15
    hp = np.array([0, 2, 7, 9])
    lp = np.array([1, 3, 4, 5, 6, 8, 10, 11, 12, 13, 14, 15])

    i = 0
    end = len(hb) - preamble_hb - msg_hb

    while i < end:
        # Quick energy check
        if hb[i] < threshold:
            i += 1
            continue

        # Check preamble shape
        pvals = hb[i:i + preamble_hb]

        high_mean = pvals[hp].mean()
        low_mean = pvals[lp].mean()

        # High pulses must be well above lows
        if high_mean < threshold or high_mean / max(low_mean, 0.1) < 2.0:
            i += 1
            continue

        # Each high must be above midpoint
        mid = (high_mean + low_mean) / 2
        if np.any(pvals[hp] < mid):
            i += 1
            continue

        preamble_hits += 1

        # Extract 112 bits: for each bit, compare its two half-bit cells
        bit_start = i + preamble_hb
        bit_end = bit_start + msg_hb

        if bit_end > len(hb):
            i += 1
            continue

        msg_hb_vals = hb[bit_start:bit_end]
        # Reshape to (112, 2): first_half vs second_half for each bit
        bit_pairs = msg_hb_vals.reshape(LONG_MSG_BITS, 2)
        bits = (bit_pairs[:, 0] > bit_pairs[:, 1]).astype(np.uint8)

        # Convert to bytes and check CRC
        msg_bytes = bits_to_bytes(bits.tolist())

        if check_crc(msg_bytes):
            crc_pass += 1
            result = decode_message(msg_bytes, aircraft)
            if result:
                messages.append(result)
                print(result)
            # Skip past this message
            i = bit_end
        else:
            crc_fail += 1
            i += 1

    print(f"\n[ADS-B] Preamble hits: {preamble_hits}")
    print(f"[ADS-B] CRC pass: {crc_pass}  fail: {crc_fail}")
    print(f"[ADS-B] Unique aircraft: {len(aircraft)}")
    print(f"[ADS-B] Decoded messages: {len(messages)}")

    if aircraft:
        print("\n[ADS-B] Aircraft summary:")
        for icao, ac in sorted(aircraft.items()):
            info = f"  {icao}"
            if ac["callsign"]:
                info += f"  {ac['callsign']}"
            if ac["alt"] is not None:
                info += f"  {ac['alt']}ft"
            if ac["lat"] is not None:
                info += f"  ({ac['lat']:.4f}, {ac['lon']:.4f})"
            if ac["speed"] is not None:
                info += f"  {ac['speed']:.0f}kt hdg {ac['heading']:.0f}"
            print(info)

    return messages


def run(config: dict, duration: float = 10.0, device: str = None):
    """Main entry point called by hackrf.py launcher."""
    if device is None:
        from config import RX_SERIAL
        device = RX_SERIAL

    print(f"[ADS-B] {config['description']}")
    print(f"[ADS-B] Device: {device}")
    print(f"[ADS-B] Duration: {duration}s")
    print()

    # Capture IQ
    iq_data = capture_iq(config, duration, device)
    if iq_data is None:
        return

    if len(iq_data) < 1000:
        print("[ADS-B] Capture too short, no data to decode")
        return

    # Compute envelope
    print("[ADS-B] Computing envelope...")
    envelope = compute_envelope(iq_data)

    # Decode
    print("[ADS-B] Scanning for ADS-B messages...\n")
    decode_iq(envelope, config["sample_rate"])


if __name__ == "__main__":
    # Allow standalone testing: python3 protocols/adsb.py [duration]
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import PROTOCOLS, RX_SERIAL

    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    run(PROTOCOLS["adsb"], duration=duration, device=RX_SERIAL)

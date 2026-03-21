"""
HackRFComs - Configuration
Device serials and shared radio parameters.
"""

# Device serial numbers
TX_SERIAL = "625863dc2c8c318b"   # Device 0 - Transmitter
RX_SERIAL = "15b062dc2b3a96cf"   # Device 1 - Receiver

# Radio parameters
CENTER_FREQ = 915_000_000       # 915 MHz (ISM band)
SAMPLE_RATE = 2_000_000         # 2 MS/s
LNA_GAIN = 32                   # RX LNA gain (dB)
VGA_GAIN = 40                   # RX VGA gain (dB)
TX_VGA_GAIN = 30                # TX VGA gain (dB)
BANDWIDTH = 1_750_000           # Filter bandwidth (Hz)

# Modulation parameters
SYMBOL_RATE = 10_000            # Symbols per second
SAMPLES_PER_SYMBOL = SAMPLE_RATE // SYMBOL_RATE  # 200 samples/symbol

# Framing
PREAMBLE = bytes([0xAA] * 8)   # 8-byte preamble for clock sync
SYNC_WORD = bytes([0x2D, 0xD4])  # Sync word to mark frame start

# Per-protocol radio configurations (used by hackrf.py launcher)
PROTOCOLS = {
    "adsb": {
        "center_freq": 1_090_000_000,
        "sample_rate": 2_000_000,
        "lna_gain": 32,
        "vga_gain": 40,
        "bandwidth": 1_750_000,
        "description": "ADS-B aircraft tracking (1090 MHz)",
    },
    "ais": {
        "center_freq": 162_000_000,
        "sample_rate": 2_000_000,
        "lna_gain": 32,
        "vga_gain": 40,
        "bandwidth": 1_750_000,
        "description": "AIS marine vessel tracking (162 MHz)",
    },
    "fm": {
        "center_freq": None,  # Set per-station
        "sample_rate": 2_000_000,
        "lna_gain": 24,
        "vga_gain": 30,
        "bandwidth": 200_000,
        "description": "FM radio demodulation (88-108 MHz)",
    },
    "acars": {
        "center_freq": 131_550_000,
        "sample_rate": 2_000_000,
        "lna_gain": 32,
        "vga_gain": 40,
        "bandwidth": 1_750_000,
        "description": "ACARS aircraft messages (131.55 MHz)",
    },
    "noaa": {
        "center_freq": 137_100_000,
        "sample_rate": 2_000_000,
        "lna_gain": 32,
        "vga_gain": 40,
        "bandwidth": 1_750_000,
        "description": "NOAA weather satellite APT (137 MHz)",
    },
    "comms": {
        "center_freq": 915_000_000,
        "sample_rate": 2_000_000,
        "lna_gain": 32,
        "vga_gain": 40,
        "bandwidth": 1_750_000,
        "description": "HackRFComs OOK protocol (915 MHz)",
    },
}

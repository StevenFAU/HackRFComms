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

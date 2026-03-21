"""
HackRFComs — FM Radio Decoder
Wideband FM demodulation (88-108 MHz)
Status: Not yet implemented
"""


def run(config: dict, duration: float = 10.0, device: str = None, freq: float = None):
    """Main entry point called by hackrf.py launcher."""
    print("[FM] decoder not yet implemented")
    if freq:
        print(f"Frequency: {freq} MHz")
    else:
        print("Band: 88-108 MHz")
    print("To contribute, edit protocols/fm.py")

"""
HackRFComs — ACARS Decoder
Aircraft Communications Addressing and Reporting System (131.55 MHz)
Status: Not yet implemented
"""


def run(config: dict, duration: float = 10.0, device: str = None):
    """Main entry point called by hackrf.py launcher."""
    print("[ACARS] decoder not yet implemented")
    print(f"Frequency: {config['center_freq']/1e6:.2f} MHz")
    print("To contribute, edit protocols/acars.py")

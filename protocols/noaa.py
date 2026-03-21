"""
HackRFComs — NOAA Weather Satellite Decoder
NOAA APT weather satellite imagery (137 MHz)
Status: Not yet implemented
"""


def run(config: dict, duration: float = 10.0, device: str = None):
    """Main entry point called by hackrf.py launcher."""
    print("[NOAA] decoder not yet implemented")
    print(f"Frequency: {config['center_freq']/1e6:.1f} MHz")
    print("To contribute, edit protocols/noaa.py")

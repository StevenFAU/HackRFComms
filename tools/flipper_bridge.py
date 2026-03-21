#!/usr/bin/env python3
"""
HackRFComs — Flipper Zero Bridge
Convenience wrapper for Flipper encode/decode workflows.

Usage:
  python3 tools/flipper_bridge.py encode "Hello from Flipper!"
  python3 tools/flipper_bridge.py decode captured.sub
  python3 tools/flipper_bridge.py tx "Test message"
"""

import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TOOLS_DIR)


def cmd_encode(args):
    """Generate a .sub file from a message."""
    message = args[0] if args else "Hello from Flipper!"
    output = args[1] if len(args) > 1 else "iq_dumps/flipper_tx.sub"
    subprocess.run([sys.executable, os.path.join(TOOLS_DIR, "flipper_encode.py"),
                    message, output])


def cmd_decode(args):
    """Decode a .sub file captured on the Flipper."""
    if not args:
        print("Usage: flipper_bridge.py decode <file.sub>")
        sys.exit(1)
    subprocess.run([sys.executable, os.path.join(TOOLS_DIR, "flipper_decode.py"),
                    args[0]])


def cmd_tx(args):
    """Transmit via HackRF and remind user to capture on Flipper."""
    message = args[0] if args else "Hello from HackRF!"
    print(f"Transmitting: {message!r}")
    print("On your Flipper: Sub-GHz → Read RAW → Start capture NOW")
    print()
    subprocess.run([sys.executable, os.path.join(PROJECT_DIR, "demo.py"), message])
    print()
    print("Done! On Flipper: stop capture, save the .sub file.")
    print(f"Then decode with: python3 tools/flipper_decode.py <saved_file.sub>")


def main():
    usage = """Usage:
  python3 tools/flipper_bridge.py encode "message" [output.sub]
  python3 tools/flipper_bridge.py decode captured.sub
  python3 tools/flipper_bridge.py tx "message"
"""
    if len(sys.argv) < 2:
        print(usage)
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {"encode": cmd_encode, "decode": cmd_decode, "tx": cmd_tx}
    handler = commands.get(cmd)
    if handler:
        handler(args)
    else:
        print(f"Unknown command: {cmd}")
        print(usage)


if __name__ == "__main__":
    main()

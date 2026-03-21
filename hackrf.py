#!/usr/bin/env python3
"""
HackRFComs — Multi-Protocol RF Launcher
Single entry point for all protocol modes.

Usage:
  python3 hackrf.py adsb                      # ADS-B aircraft tracking
  python3 hackrf.py adsb --duration 60        # Capture for 60 seconds
  python3 hackrf.py scan 400 1700 --plot      # Spectrum scanner
  python3 hackrf.py comms "Hello"             # Send message
  python3 hackrf.py comms --rx                # Receive mode
  python3 hackrf.py demo "test message"       # Original hello world demo
  python3 hackrf.py fm 101.5                  # (future) FM demod
  python3 hackrf.py ais                       # (future) AIS marine tracking
  python3 hackrf.py acars                     # (future) ACARS aircraft messages
  python3 hackrf.py noaa                      # (future) NOAA satellite capture
"""

import argparse
import sys
import os

# Ensure project root is on the path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import PROTOCOLS, RX_SERIAL, TX_SERIAL


def cmd_adsb(args):
    from protocols import adsb
    config = PROTOCOLS["adsb"]
    device = args.device_serial or RX_SERIAL
    adsb.run(config, duration=args.duration, device=device)


def cmd_scan(args):
    from scanner import sweep, print_results, plot_results

    start = args.start or 900
    end = args.end or 930
    bin_width = 100_000 if args.fine else 1_000_000

    print(f"Scanning {start} - {end} MHz ({'fine' if args.fine else 'coarse'} resolution)...")
    results = sweep(start, end, bin_width=bin_width, num_sweeps=args.sweeps)
    print_results(results, start, end)

    if args.plot:
        plot_results(results, start, end, save=args.save)


def cmd_comms(args):
    if args.rx:
        from protocol import receive_and_ack, RX_SERIAL as default_rx
        device = args.device_serial or default_rx
        data = receive_and_ack(device=device, save=args.save)
        if data:
            print(f"\nReceived: {data.decode('utf-8', errors='replace')}")
    else:
        from protocol import send_reliable, TX_SERIAL as default_tx
        device = args.device_serial or default_tx
        msg = args.message or "Hello with ACK!"
        ok = send_reliable(msg.encode(), device=device, save=args.save)
        print(f"\nResult: {'delivered' if ok else 'failed'}")


def cmd_demo(args):
    # Run demo.py as a subprocess to avoid import side effects
    import subprocess
    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "demo.py")]
    if args.message:
        cmd.append(args.message)
    subprocess.run(cmd)


def cmd_fm(args):
    from protocols import fm
    config = PROTOCOLS["fm"].copy()
    freq = args.frequency
    if freq:
        config["center_freq"] = int(freq * 1e6)
    device = args.device_serial or RX_SERIAL
    fm.run(config, duration=args.duration, device=device, freq=freq)


def cmd_flipper(args):
    import subprocess
    tools_dir = os.path.join(os.path.dirname(__file__), "tools")
    if args.action == "encode":
        cmd = [sys.executable, os.path.join(tools_dir, "flipper_encode.py")]
        if args.message:
            cmd.append(args.message)
        if args.output:
            cmd.append(args.output)
        subprocess.run(cmd)
    elif args.action == "decode":
        if not args.message:
            print("Usage: hackrf.py flipper decode <file.sub>")
            return
        subprocess.run([sys.executable, os.path.join(tools_dir, "flipper_decode.py"),
                        args.message])
    else:
        print("Usage: hackrf.py flipper {encode|decode}")


def cmd_stub(protocol_name):
    """Return a handler for a stub protocol."""
    def handler(args):
        import importlib
        mod = importlib.import_module(f"protocols.{protocol_name}")
        config = PROTOCOLS[protocol_name]
        device = args.device_serial or RX_SERIAL
        mod.run(config, duration=args.duration, device=device)
    return handler


def resolve_device(device_index):
    """Convert device index (0 or 1) to serial string."""
    if device_index is None:
        return None
    serials = [TX_SERIAL, RX_SERIAL]
    if device_index < 0 or device_index >= len(serials):
        print(f"Invalid device index: {device_index}. Use 0 or 1.")
        sys.exit(1)
    return serials[device_index]


def main():
    parser = argparse.ArgumentParser(
        prog="hackrf.py",
        description="HackRFComs — Multi-Protocol RF Platform",
    )
    parser.add_argument("--device", type=int, default=None, metavar="N",
                        help="Device index (0=TX, 1=RX)")

    sub = parser.add_subparsers(dest="mode", help="Protocol mode")

    # adsb
    p_adsb = sub.add_parser("adsb", help="ADS-B aircraft tracking (1090 MHz)")
    p_adsb.add_argument("--duration", type=float, default=10.0,
                        help="Capture duration in seconds (default: 10)")

    # scan
    p_scan = sub.add_parser("scan", help="Spectrum scanner (hackrf_sweep)")
    p_scan.add_argument("start", type=int, nargs="?", default=None,
                        help="Start frequency in MHz")
    p_scan.add_argument("end", type=int, nargs="?", default=None,
                        help="End frequency in MHz")
    p_scan.add_argument("--plot", action="store_true", help="Show plot")
    p_scan.add_argument("--save", action="store_true", help="Save plot image")
    p_scan.add_argument("--fine", action="store_true", help="100 kHz bins")
    p_scan.add_argument("--sweeps", type=int, default=1, help="Number of sweeps")

    # comms
    p_comms = sub.add_parser("comms", help="OOK comms protocol (915 MHz)")
    p_comms.add_argument("message", nargs="?", default=None, help="Message to send")
    p_comms.add_argument("--rx", action="store_true", help="Receive mode")
    p_comms.add_argument("--save", action="store_true", help="Save IQ and timeline")

    # demo
    p_demo = sub.add_parser("demo", help="Original hello world demo")
    p_demo.add_argument("message", nargs="?", default=None, help="Message to send")

    # fm
    p_fm = sub.add_parser("fm", help="FM radio demodulation (88-108 MHz)")
    p_fm.add_argument("frequency", type=float, nargs="?", default=None,
                       help="Station frequency in MHz (e.g. 101.5)")
    p_fm.add_argument("--duration", type=float, default=10.0)

    # flipper
    p_flip = sub.add_parser("flipper", help="Flipper Zero .sub encode/decode")
    p_flip.add_argument("action", choices=["encode", "decode"],
                         help="encode message to .sub, or decode .sub file")
    p_flip.add_argument("message", nargs="?", default=None,
                         help="Message (encode) or .sub file path (decode)")
    p_flip.add_argument("--output", "-o", default=None, help="Output .sub path")

    # Stub protocols
    for proto in ("ais", "acars", "noaa"):
        p = sub.add_parser(proto, help=PROTOCOLS[proto]["description"])
        p.add_argument("--duration", type=float, default=10.0)

    args = parser.parse_args()

    if not args.mode:
        parser.print_help()
        print("\nAvailable protocols:")
        for name, cfg in PROTOCOLS.items():
            print(f"  {name:8s}  {cfg['description']}")
        sys.exit(0)

    # Resolve device serial
    args.device_serial = resolve_device(args.device)

    # Dispatch
    dispatch = {
        "adsb": cmd_adsb,
        "scan": cmd_scan,
        "comms": cmd_comms,
        "demo": cmd_demo,
        "fm": cmd_fm,
        "ais": cmd_stub("ais"),
        "acars": cmd_stub("acars"),
        "noaa": cmd_stub("noaa"),
        "flipper": cmd_flipper,
    }

    handler = dispatch.get(args.mode)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

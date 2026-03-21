"""
HackRFComs - Protocol Layer
Higher-level packet handling on top of the raw modulation layer.
Adds sequence numbers, ACK/NACK, and retransmission.

Packet types:
  DATA  (0x01): seq(1) + payload
  ACK   (0x02): seq(1)
  NACK  (0x03): seq(1)
"""

import os
import time
import struct
import subprocess
import threading
import numpy as np
from config import (
    TX_SERIAL, RX_SERIAL, CENTER_FREQ, SAMPLE_RATE,
    LNA_GAIN, VGA_GAIN, TX_VGA_GAIN, SAMPLES_PER_SYMBOL
)
from modulation import build_frame, frame_to_iq, demodulate

TYPE_DATA = 0x01
TYPE_ACK = 0x02
TYPE_NACK = 0x03

MAX_RETRIES = 3
ACK_TIMEOUT = 20.0  # seconds to wait for ACK (receiver needs time to capture, decode, and reply)


def _run_hackrf(cmd, duration, label):
    """Run hackrf_transfer for a duration, then clean up reliably."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        print(f"[{label}] hackrf_transfer not found")
        return False
    time.sleep(duration)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    return proc.returncode in (0, -15)


def build_data_packet(seq: int, payload: bytes) -> bytes:
    """Wrap payload in a DATA packet with sequence number."""
    return build_frame(struct.pack("BB", TYPE_DATA, seq) + payload)


def build_ack(seq: int) -> bytes:
    """Build an ACK packet for the given sequence number."""
    return build_frame(struct.pack("BB", TYPE_ACK, seq))


def build_nack(seq: int) -> bytes:
    """Build a NACK packet for the given sequence number."""
    return build_frame(struct.pack("BB", TYPE_NACK, seq))


def parse_packet(raw: bytes) -> tuple[int, int, bytes] | None:
    """
    Parse a decoded payload into (type, seq, data).
    Returns None if the payload is too short or unrecognized.
    """
    if len(raw) < 2:
        return None
    pkt_type = raw[0]
    seq = raw[1]
    data = raw[2:]
    if pkt_type not in (TYPE_DATA, TYPE_ACK, TYPE_NACK):
        return None
    return pkt_type, seq, data


def _tx_iq(frame: bytes, serial: str, repeats: int = 5):
    """Modulate a frame and transmit it."""
    iq = frame_to_iq(frame).tobytes() * repeats
    path = f"/tmp/hackrf_tx_{os.getpid()}.iq"
    with open(path, "wb") as f:
        f.write(iq)
    duration = max((len(iq) / (SAMPLE_RATE * 2)) * 1.5, 2.0)
    cmd = [
        "hackrf_transfer", "-d", serial, "-t", path,
        "-f", str(CENTER_FREQ), "-s", str(SAMPLE_RATE),
        "-x", str(TX_VGA_GAIN), "-a", "1",
    ]
    return _run_hackrf(cmd, duration, "TX")


def _rx_capture(serial: str, duration: float) -> np.ndarray | None:
    """Capture IQ data and return as array."""
    path = f"/tmp/hackrf_rx_{os.getpid()}.iq"
    cmd = [
        "hackrf_transfer", "-d", serial, "-r", path,
        "-f", str(CENTER_FREQ), "-s", str(SAMPLE_RATE),
        "-l", str(LNA_GAIN), "-g", str(VGA_GAIN), "-a", "1",
    ]
    if not _run_hackrf(cmd, duration, "RX"):
        return None
    try:
        return np.fromfile(path, dtype=np.int8)
    except FileNotFoundError:
        return None


def send_reliable(message: bytes, device: str = TX_SERIAL) -> bool:
    """
    Send a message with retransmission using a single HackRF.
    Half-duplex: transmit DATA, then switch to RX to listen for ACK.
    Returns True if ACK received, False after MAX_RETRIES.
    """
    seq = int(time.time()) % 256

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"[SENDER] Transmitting seq={seq} attempt {attempt}/{MAX_RETRIES}")
        frame = build_data_packet(seq, message)
        _tx_iq(frame, device)

        # Switch to RX on the same device and listen for ACK
        print(f"[SENDER] Listening for ACK ({ACK_TIMEOUT:.0f}s)...")
        iq_data = _rx_capture(device, ACK_TIMEOUT)
        if iq_data is None:
            continue

        payload = demodulate(iq_data)
        if payload is None:
            print(f"[SENDER] No valid response received")
            continue

        pkt = parse_packet(payload)
        if pkt is None:
            continue

        pkt_type, ack_seq, _ = pkt
        if pkt_type == TYPE_ACK and ack_seq == seq:
            print(f"[SENDER] ACK received for seq={seq}")
            return True
        elif pkt_type == TYPE_NACK and ack_seq == seq:
            print(f"[SENDER] NACK received, retrying...")
            continue

    print(f"[SENDER] Failed after {MAX_RETRIES} attempts")
    return False


def receive_and_ack(device: str = RX_SERIAL,
                    listen_duration: float = 15.0) -> bytes | None:
    """
    Listen for a DATA packet on a single HackRF, then switch to TX
    to send ACK back. Half-duplex on one device.
    Returns the message payload or None.
    """
    print(f"[RECEIVER] Listening for {listen_duration:.0f}s on {device}...")
    iq_data = _rx_capture(device, listen_duration)
    if iq_data is None:
        return None

    payload = demodulate(iq_data)
    if payload is None:
        print("[RECEIVER] No valid packet received")
        return None

    pkt = parse_packet(payload)
    if pkt is None:
        print("[RECEIVER] Unrecognized packet format")
        return None

    pkt_type, seq, data = pkt
    if pkt_type == TYPE_DATA:
        print(f"[RECEIVER] DATA received seq={seq}: {data}")
        # Delay so the sender has time to switch to RX mode
        print(f"[RECEIVER] Waiting 3s for sender to switch to RX...")
        time.sleep(3.0)
        # Switch to TX on the same device to send ACK
        ack = build_ack(seq)
        print(f"[RECEIVER] Sending ACK for seq={seq}")
        _tx_iq(ack, device)
        return data

    return None


if __name__ == "__main__":
    import sys

    usage = """Usage:
  python3 protocol.py rx                    # Receive on device 1 (default)
  python3 protocol.py send "message"        # Send on device 0 (default)

Each side uses ONE HackRF in half-duplex (TX then RX, or RX then TX).
  Device 0 (sender):   {tx}
  Device 1 (receiver): {rx}

For a full test, run in two terminals:
  Terminal 1:  python3 protocol.py rx
  Terminal 2:  python3 protocol.py send "Hello with ACK!"
""".format(tx=TX_SERIAL, rx=RX_SERIAL)

    if len(sys.argv) < 2:
        print(usage)
        sys.exit(0)

    if sys.argv[1] == "rx":
        data = receive_and_ack(device=RX_SERIAL)
        if data:
            print(f"\nReceived: {data.decode('utf-8', errors='replace')}")
    elif sys.argv[1] == "send":
        msg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Hello with ACK!"
        ok = send_reliable(msg.encode(), device=TX_SERIAL)
        print(f"\nResult: {'delivered' if ok else 'failed'}")
    else:
        print(usage)

#!/usr/bin/env python3
"""
HackRFComs - Protocol Timeline Visualizer
Shows the round-trip timing of a DATA + ACK exchange.

Reads IQ captures and timeline JSON from both sender and receiver,
then plots:
  1. Sender's view: its RX capture showing the ACK burst arriving
  2. Receiver's view: its RX capture showing the DATA burst arriving
  3. Combined timeline: wall-clock phases of the full exchange
"""

import os
import sys
import json
import numpy as np
from scipy import signal as dsp
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from config import SAMPLE_RATE, SAMPLES_PER_SYMBOL
from modulation import CARRIER_OFFSET

IQ_DIR = os.path.join(os.path.dirname(__file__), "iq_dumps")


def envelope_from_iq(path):
    """Load IQ file and return filtered envelope."""
    raw = np.fromfile(path, dtype=np.int8)
    i = raw[0::2].astype(np.float64)
    q = raw[1::2].astype(np.float64)

    t = np.arange(len(i), dtype=np.float64) / SAMPLE_RATE
    csig = i + 1j * q
    mixed = csig * np.exp(-1j * 2 * np.pi * CARRIER_OFFSET * t)

    b, a = dsp.butter(4, 30_000 / (SAMPLE_RATE / 2), btype='low')
    filt = dsp.filtfilt(b, a, mixed)
    return np.abs(filt)


def load_timeline(path):
    """Load timeline JSON and return as dict of event->timestamp."""
    with open(path) as f:
        events = json.load(f)
    return {name: ts for name, ts in events}


def main():
    plt.style.use('dark_background')

    sender_rx_path = os.path.join(IQ_DIR, "sender_rx.iq")
    receiver_rx_path = os.path.join(IQ_DIR, "receiver_rx.iq")
    sender_tl_path = os.path.join(IQ_DIR, "sender_timeline.json")
    receiver_tl_path = os.path.join(IQ_DIR, "receiver_timeline.json")

    have_sender = os.path.exists(sender_rx_path) and os.path.exists(sender_tl_path)
    have_receiver = os.path.exists(receiver_rx_path) and os.path.exists(receiver_tl_path)

    if not have_sender and not have_receiver:
        print("No protocol captures found. Run:")
        print("  Terminal 1:  python3 protocol.py rx --save")
        print("  Terminal 2:  python3 protocol.py send 'message' --save")
        sys.exit(1)

    sender_tl = load_timeline(sender_tl_path) if have_sender else {}
    receiver_tl = load_timeline(receiver_tl_path) if have_receiver else {}

    fig = plt.figure(figsize=(14, 10), facecolor='#111')
    fig.suptitle("HackRFComs — Protocol Round-Trip Timeline",
                 fontsize=14, fontweight='bold', color='white')
    gs = GridSpec(3, 1, figure=fig, hspace=0.4, height_ratios=[1, 1, 0.8])

    # --- Panel 1: Receiver's RX capture (shows DATA burst arriving) ---
    if have_receiver:
        ax1 = fig.add_subplot(gs[0])
        env = envelope_from_iq(receiver_rx_path)
        ds = max(1, len(env) // 20000)
        env_ds = env[:len(env) // ds * ds].reshape(-1, ds).max(axis=1)
        t_ds = np.arange(len(env_ds)) * ds / SAMPLE_RATE

        ax1.plot(t_ds, env_ds, color='#00cc66', linewidth=0.5)
        ax1.fill_between(t_ds, 0, env_ds, alpha=0.3, color='#00cc66')
        ax1.set_xlabel("Time (s)")
        ax1.set_ylabel("Signal strength")
        ax1.set_title("Receiver's view (Device 1 RX) — DATA burst from sender",
                      color='#00cc66')

        # Annotate the DATA burst
        peak = env_ds.max()
        threshold = np.median(env_ds) + (peak - np.median(env_ds)) * 0.3
        above = np.where(env_ds > threshold)[0]
        if len(above) > 0:
            burst_start = t_ds[above[0]]
            burst_end = t_ds[above[-1]]
            ax1.axvspan(burst_start, burst_end, alpha=0.15, color='#00cc66')
            ax1.annotate(f'DATA burst\n{(burst_end-burst_start)*1000:.0f} ms',
                         xy=((burst_start + burst_end) / 2, peak * 0.8),
                         ha='center', fontsize=9, color='white',
                         bbox=dict(boxstyle='round,pad=0.3', facecolor='#333', alpha=0.8))
    else:
        ax1 = fig.add_subplot(gs[0])
        ax1.text(0.5, 0.5, "No receiver capture (run with --save)",
                 ha='center', va='center', transform=ax1.transAxes, color='#666')

    # --- Panel 2: Sender's RX capture (shows ACK burst arriving) ---
    if have_sender:
        ax2 = fig.add_subplot(gs[1])
        env = envelope_from_iq(sender_rx_path)
        ds = max(1, len(env) // 20000)
        env_ds = env[:len(env) // ds * ds].reshape(-1, ds).max(axis=1)
        t_ds = np.arange(len(env_ds)) * ds / SAMPLE_RATE

        ax2.plot(t_ds, env_ds, color='#ff6600', linewidth=0.5)
        ax2.fill_between(t_ds, 0, env_ds, alpha=0.3, color='#ff6600')
        ax2.set_xlabel("Time (s)")
        ax2.set_ylabel("Signal strength")
        ax2.set_title("Sender's view (Device 0 RX) — waiting for ACK",
                      color='#ff6600')

        # Annotate the ACK burst
        peak = env_ds.max()
        threshold = np.median(env_ds) + (peak - np.median(env_ds)) * 0.3
        above = np.where(env_ds > threshold)[0]
        if len(above) > 0:
            burst_start = t_ds[above[0]]
            burst_end = t_ds[above[-1]]
            ax2.axvspan(burst_start, burst_end, alpha=0.15, color='#ff6600')
            ax2.annotate(f'ACK burst\n{(burst_end-burst_start)*1000:.0f} ms',
                         xy=((burst_start + burst_end) / 2, peak * 0.8),
                         ha='center', fontsize=9, color='white',
                         bbox=dict(boxstyle='round,pad=0.3', facecolor='#333', alpha=0.8))
    else:
        ax2 = fig.add_subplot(gs[1])
        ax2.text(0.5, 0.5, "No sender capture (run with --save)",
                 ha='center', va='center', transform=ax2.transAxes, color='#666')

    # --- Panel 3: Wall-clock timeline ---
    ax3 = fig.add_subplot(gs[2])
    ax3.set_yticks([])
    ax3.set_xlabel("Wall-clock time (s from start)")
    ax3.set_title("Protocol phases — full round-trip", color='white')

    # Find earliest timestamp as t=0
    all_ts = list(sender_tl.values()) + list(receiver_tl.values())
    if all_ts:
        t0 = min(all_ts)

        # Draw sender phases
        y_sender = 0.7
        y_receiver = 0.3
        bar_h = 0.15

        def draw_phase(ax, start_key, end_key, tl, y, color, label):
            if start_key in tl and end_key in tl:
                s = tl[start_key] - t0
                e = tl[end_key] - t0
                ax.barh(y, e - s, left=s, height=bar_h, color=color, alpha=0.8)
                ax.text(s + (e - s) / 2, y, f'{label}\n{e-s:.1f}s',
                        ha='center', va='center', fontsize=7, color='white')

        draw_phase(ax3, 'sender_tx_start', 'sender_tx_end',
                   sender_tl, y_sender, '#ff4444', 'TX DATA')
        draw_phase(ax3, 'sender_rx_start', 'sender_rx_end',
                   sender_tl, y_sender - bar_h - 0.02, '#ff6600', 'RX (wait for ACK)')

        draw_phase(ax3, 'receiver_rx_start', 'receiver_rx_end',
                   receiver_tl, y_receiver, '#00cc66', 'RX (listen)')
        draw_phase(ax3, 'receiver_tx_start', 'receiver_tx_end',
                   receiver_tl, y_receiver - bar_h - 0.02, '#44aa44', 'TX ACK')

        # Labels
        ax3.text(-0.5, y_sender - bar_h / 2, 'SENDER\n(Dev 0)', ha='right',
                 va='center', fontsize=9, color='#ff6600')
        ax3.text(-0.5, y_receiver - bar_h / 2, 'RECEIVER\n(Dev 1)', ha='right',
                 va='center', fontsize=9, color='#00cc66')

        # Turnaround time annotation
        if 'sender_tx_end' in sender_tl and 'receiver_tx_start' in receiver_tl:
            turnaround = receiver_tl['receiver_tx_start'] - sender_tl['sender_tx_end']
            ax3.annotate(f'Turnaround: {turnaround:.1f}s',
                         xy=(sender_tl['sender_tx_end'] - t0 + turnaround / 2, 0.5),
                         ha='center', fontsize=10, color='cyan',
                         bbox=dict(boxstyle='round,pad=0.3', facecolor='#222', alpha=0.9))

        ax3.set_ylim(0, 1)
        ax3.set_xlim(-1, max(t - t0 for t in all_ts) + 1)

    out_path = os.path.join(IQ_DIR, "protocol_timeline.png")
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='#111')
    print(f"Saved: {out_path}")
    plt.show()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
HackRFComs - Signal Visualizer
Shows what actually happened over the air in a way that makes sense.
"""

import sys
import numpy as np
from scipy import signal as dsp
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from config import SAMPLE_RATE, SAMPLES_PER_SYMBOL
from modulation import CARRIER_OFFSET

IQ_FILE = sys.argv[1] if len(sys.argv) > 1 else "iq_dumps/rx.iq"


def load_and_process(path):
    raw = np.fromfile(path, dtype=np.int8)
    i = raw[0::2].astype(np.float64)
    q = raw[1::2].astype(np.float64)
    return i, q


def main():
    print(f"Loading {IQ_FILE}...")
    i_raw, q_raw = load_and_process(IQ_FILE)
    duration = len(i_raw) / SAMPLE_RATE
    t = np.arange(len(i_raw)) / SAMPLE_RATE

    # Mix down to carrier offset
    csig = i_raw + 1j * q_raw
    mixed = csig * np.exp(-1j * 2 * np.pi * CARRIER_OFFSET * t)
    b, a = dsp.butter(4, 30_000 / (SAMPLE_RATE / 2), btype='low')
    filt = dsp.filtfilt(b, a, mixed)
    env = np.abs(filt)

    # Find burst region
    peak = env.max()
    threshold = peak * 0.3
    above = np.where(env > threshold)[0]
    burst_start_s = above[0] / SAMPLE_RATE if len(above) > 0 else 0
    burst_end_s = above[-1] / SAMPLE_RATE if len(above) > 0 else duration

    # Zoom window: one frame copy (~25ms of data around burst start)
    frame_samples = 248 * SAMPLES_PER_SYMBOL  # one frame in samples
    zoom_start = above[0] if len(above) > 0 else 0
    zoom_end = zoom_start + frame_samples + SAMPLES_PER_SYMBOL * 10  # +padding
    zoom_end = min(zoom_end, len(env))

    plt.style.use('dark_background')
    fig = plt.figure(figsize=(14, 10), facecolor='#111')
    fig.suptitle("HackRFComs — What Happened Over the Air",
                 fontsize=14, fontweight='bold', color='white')
    gs = GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.3)

    # --- Panel 1: Spectrogram (full capture) ---
    ax1 = fig.add_subplot(gs[0, :])
    # Downsample for spectrogram
    nfft = 2048
    spec, freqs, t_spec, im = ax1.specgram(
        i_raw + 1j * q_raw, NFFT=nfft, Fs=SAMPLE_RATE,
        Fc=0, noverlap=nfft * 3 // 4, cmap='inferno',
        scale='dB', vmin=-65, vmax=5)
    fig.colorbar(im, ax=ax1, label='Power (dB)', shrink=0.8, pad=0.01)
    # Relabel axes to human-friendly units
    ax1.set_ylabel("Freq offset (kHz)")
    ax1.set_xlabel("Time (s)")
    # Convert y-axis ticks from Hz to kHz
    yticks = ax1.get_yticks()
    ax1.set_yticklabels([f'{y/1e3:.0f}' for y in yticks])
    ax1.set_title("Spectrogram — full capture  (bright = energy at that frequency)")
    ax1.axhline(y=CARRIER_OFFSET, color='cyan', linewidth=0.8, linestyle='--',
                label=f'Our carrier @ +{CARRIER_OFFSET/1e3:.0f} kHz')
    ax1.legend(loc='upper right', fontsize=8)

    # Mark burst region
    ax1.axvline(x=burst_start_s, color='lime', linewidth=1, linestyle='--', alpha=0.7)
    ax1.axvline(x=burst_end_s, color='lime', linewidth=1, linestyle='--', alpha=0.7)
    ax1.text(burst_start_s, SAMPLE_RATE / 2 / 1e6 * 0.9, ' signal here',
             color='lime', fontsize=8, va='top')

    # --- Panel 2: Envelope over full capture ---
    ax2 = fig.add_subplot(gs[1, 0])
    # Downsample envelope for plotting
    ds = max(1, len(env) // 10000)
    env_ds = env[:len(env) // ds * ds].reshape(-1, ds).max(axis=1)
    t_ds = np.arange(len(env_ds)) * ds / SAMPLE_RATE
    ax2.plot(t_ds, env_ds, color='#ff6600', linewidth=0.5)
    ax2.axhline(y=threshold, color='cyan', linewidth=1, linestyle='--',
                label=f'Threshold ({threshold:.0f})')
    ax2.fill_between(t_ds, 0, env_ds, alpha=0.3, color='#ff6600')
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Signal strength")
    ax2.set_title("Demodulated envelope — where is the signal?")
    ax2.legend(fontsize=8)

    # Annotate
    ax2.annotate('TX burst', xy=(burst_start_s, peak * 0.8),
                 fontsize=9, color='white',
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='#333', alpha=0.8))

    # --- Panel 3: Zoomed OOK bits (one frame) ---
    ax3 = fig.add_subplot(gs[1, 1])
    z_t = np.arange(zoom_start, zoom_end) / SAMPLE_RATE * 1000  # ms
    z_env = env[zoom_start:zoom_end]
    ax3.plot(z_t, z_env, color='#ff6600', linewidth=0.8)
    ax3.axhline(y=threshold, color='cyan', linewidth=1, linestyle='--')
    ax3.fill_between(z_t, 0, z_env, where=z_env > threshold,
                     alpha=0.4, color='lime', label='Bit = 1 (carrier ON)')
    ax3.fill_between(z_t, 0, z_env, where=z_env <= threshold,
                     alpha=0.2, color='red', label='Bit = 0 (carrier OFF)')
    ax3.set_xlabel("Time (ms)")
    ax3.set_ylabel("Signal strength")
    ax3.set_title("Zoomed in — one frame of OOK data")
    ax3.legend(fontsize=7, loc='upper right')

    # Mark preamble / sync / data regions
    preamble_end_ms = z_t[0] + (64 * SAMPLES_PER_SYMBOL) / SAMPLE_RATE * 1000
    sync_end_ms = preamble_end_ms + (16 * SAMPLES_PER_SYMBOL) / SAMPLE_RATE * 1000
    ymax = z_env.max() * 1.1
    ax3.axvspan(z_t[0], preamble_end_ms, alpha=0.08, color='yellow')
    ax3.axvspan(preamble_end_ms, sync_end_ms, alpha=0.08, color='cyan')
    ax3.text(z_t[0] + 0.1, ymax * 0.95, 'PREAMBLE\n10101010...',
             fontsize=7, color='#888', va='top')
    ax3.text(preamble_end_ms + 0.05, ymax * 0.95, 'SYNC',
             fontsize=7, color='#888', va='top')
    ax3.text(sync_end_ms + 0.1, ymax * 0.95, 'DATA + CRC',
             fontsize=7, color='#888', va='top')

    # --- Panel 4: Decoded bit pattern ---
    ax4 = fig.add_subplot(gs[2, :])
    # Get bits at symbol rate for the burst region
    SPS = SAMPLES_PER_SYMBOL
    burst_env = env[above[0]:above[0] + frame_samples + SPS * 5]
    n_sym = len(burst_env) // SPS

    # Find best phase
    best_bits = None
    best_preamble_score = 0
    preamble_bits = np.unpackbits(np.frombuffer(b'\xaa' * 8, dtype=np.uint8))
    for phase in range(0, SPS, SPS // 10):
        indices = np.arange(phase + SPS // 2, len(burst_env), SPS)
        indices = indices[indices < len(burst_env)]
        sampled = burst_env[indices]
        bits = (sampled > threshold).astype(np.uint8)
        # Score against preamble
        if len(bits) >= len(preamble_bits):
            score = np.sum(bits[:len(preamble_bits)] == preamble_bits)
            if score > best_preamble_score:
                best_preamble_score = score
                best_bits = bits

    if best_bits is not None and len(best_bits) > 80:
        n_show = min(len(best_bits), 248)  # one frame
        colors = ['#00cc00' if b == 1 else '#333333' for b in best_bits[:n_show]]

        ax4.bar(range(n_show), [1] * n_show, color=colors, width=1.0, edgecolor='none')
        ax4.set_xlim(-1, n_show + 1)
        ax4.set_ylim(0, 1.8)
        ax4.set_xlabel("Bit number")
        ax4.set_title("Decoded bits — green = 1 (carrier ON), dark = 0 (carrier OFF)")
        ax4.set_yticks([])

        # Annotate sections
        ax4.axvspan(0, 64, alpha=0.1, color='yellow')
        ax4.axvspan(64, 80, alpha=0.1, color='cyan')
        ax4.axvspan(80, 88, alpha=0.1, color='magenta')
        ax4.text(32, 1.5, 'PREAMBLE (64 bits)', ha='center', fontsize=8, color='#888')
        ax4.text(72, 1.5, 'SYNC', ha='center', fontsize=7, color='#888')
        ax4.text(84, 1.5, 'LEN', ha='center', fontsize=7, color='#888')
        ax4.text(84 + (n_show - 84) // 2, 1.5, 'PAYLOAD + CRC',
                 ha='center', fontsize=8, color='#888')

    plt.savefig("iq_dumps/signal_analysis.png", dpi=150, bbox_inches='tight',
                facecolor='#111')
    print("Saved: iq_dumps/signal_analysis.png")
    plt.show()


if __name__ == "__main__":
    main()

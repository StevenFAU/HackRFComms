"""
HackRFComs — FM Radio Demodulator
Wideband FM demodulation (88-108 MHz)

Pipeline: IQ capture -> FM discriminator -> lowpass -> decimate -> WAV
"""

import os
import sys
import time
import subprocess
import numpy as np

IQ_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "iq_dumps")

# Audio output parameters
AUDIO_RATE = 44100  # WAV sample rate


def capture_iq(config: dict, duration: float, device: str) -> np.ndarray | None:
    """Capture IQ data from HackRF at the tuned FM frequency."""
    os.makedirs(IQ_DIR, exist_ok=True)
    path = os.path.join(IQ_DIR, "fm_capture.iq")

    cmd = [
        "hackrf_transfer", "-d", device, "-r", path,
        "-f", str(config["center_freq"]),
        "-s", str(config["sample_rate"]),
        "-l", str(config["lna_gain"]),
        "-g", str(config["vga_gain"]),
        "-a", "1",
    ]

    freq_mhz = config["center_freq"] / 1e6
    print(f"[FM] Capturing {duration:.1f}s at {freq_mhz:.1f} MHz "
          f"({config['sample_rate']/1e6:.0f} MS/s)...")

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        print("[FM] hackrf_transfer not found — is it installed?")
        return None

    time.sleep(duration)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    ret = proc.returncode
    if ret and ret != -15:
        output = proc.stdout.read().decode(errors="replace").strip()
        print(f"[FM] hackrf_transfer exited {ret}: {output}")
        return None

    try:
        data = np.fromfile(path, dtype=np.int8)
        print(f"[FM] Captured {len(data)} bytes ({len(data)/config['sample_rate']/2:.1f}s)")
        return data
    except FileNotFoundError:
        print("[FM] No capture file produced")
        return None


def demodulate_fm(iq_data: np.ndarray, sample_rate: int) -> np.ndarray:
    """FM demodulation: IQ -> baseband audio at AUDIO_RATE Hz."""
    from scipy.signal import butter, filtfilt, resample_poly
    from math import gcd

    # Build complex signal from interleaved I/Q int8
    i = iq_data[0::2].astype(np.float32)
    q = iq_data[1::2].astype(np.float32)
    signal = i + 1j * q

    print(f"[FM] {len(signal)} IQ samples at {sample_rate/1e6:.0f} MS/s")

    # FM discriminator: instantaneous frequency via conjugate multiply
    # freq[n] = angle(x[n] * conj(x[n-1]))
    discriminated = np.angle(signal[1:] * np.conj(signal[:-1]))

    print(f"[FM] Discriminator output: {len(discriminated)} samples")

    # Lowpass filter at 15 kHz (mono FM audio bandwidth)
    nyq = sample_rate / 2
    cutoff = 15000 / nyq
    b, a = butter(5, cutoff, btype='low')
    filtered = filtfilt(b, a, discriminated)

    # De-emphasis filter (75 µs time constant, US standard)
    # Implemented as a single-pole IIR via scipy.signal.lfilter
    from scipy.signal import lfilter
    tau = 75e-6
    dt = 1.0 / sample_rate
    alpha = dt / (tau + dt)
    deemph = lfilter([alpha], [1, -(1 - alpha)], filtered)

    # Resample from sample_rate to AUDIO_RATE
    # Use resample_poly with up/down factors derived from gcd
    g = gcd(sample_rate, AUDIO_RATE)
    up = AUDIO_RATE // g
    down = sample_rate // g

    print(f"[FM] Resampling: {sample_rate} Hz -> {AUDIO_RATE} Hz (up={up}, down={down})")
    audio = resample_poly(deemph, up, down)

    print(f"[FM] Audio: {len(audio)} samples ({len(audio)/AUDIO_RATE:.1f}s at {AUDIO_RATE} Hz)")

    # Normalize to [-1, 1]
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak

    return audio


def save_wav(audio: np.ndarray, path: str, sample_rate: int = AUDIO_RATE):
    """Save audio as 16-bit mono WAV."""
    from scipy.io import wavfile

    # Scale to int16 range
    audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    wavfile.write(path, sample_rate, audio_int16)
    size_mb = os.path.getsize(path) / 1e6
    print(f"[FM] Saved: {path} ({size_mb:.1f} MB)")


def run(config: dict, duration: float = 10.0, device: str = None, freq: float = None):
    """Main entry point called by hackrf.py launcher."""
    if device is None:
        from config import RX_SERIAL
        device = RX_SERIAL

    if freq is None:
        print("[FM] No frequency specified. Usage: python3 hackrf.py fm <freq_mhz>")
        print("[FM] Example: python3 hackrf.py fm 93.9")
        print("[FM] Tip: run 'python3 hackrf.py scan 88 108' to find strong stations")
        return

    if freq < 88 or freq > 108:
        print(f"[FM] Warning: {freq} MHz is outside the FM broadcast band (88-108 MHz)")

    # Set center frequency from the station frequency
    config = config.copy()
    config["center_freq"] = int(freq * 1e6)

    print(f"[FM] Tuned to {freq} MHz")
    print(f"[FM] Device: {device}")

    # Capture IQ
    iq_data = capture_iq(config, duration, device)
    if iq_data is None:
        return

    if len(iq_data) < 1000:
        print("[FM] Capture too short, no data to demodulate")
        return

    # Demodulate
    print("[FM] Demodulating...")
    audio = demodulate_fm(iq_data, config["sample_rate"])

    # Save WAV
    wav_path = os.path.join(IQ_DIR, f"fm_{freq}MHz.wav")
    save_wav(audio, wav_path)
    print(f"[FM] Play with: aplay {wav_path}")


if __name__ == "__main__":
    # Standalone: python3 protocols/fm.py <freq_mhz> [duration]
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import PROTOCOLS, RX_SERIAL

    if len(sys.argv) < 2:
        print("Usage: python3 protocols/fm.py <freq_mhz> [duration]")
        print("Example: python3 protocols/fm.py 93.9 10")
        sys.exit(1)

    freq = float(sys.argv[1])
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    run(PROTOCOLS["fm"], duration=duration, device=RX_SERIAL, freq=freq)

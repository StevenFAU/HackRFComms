# HackRFComs

RF communication link between two HackRF One devices using OOK modulation at 915 MHz.

Built from scratch — no GNURadio, no SDR frameworks. Raw IQ samples, numpy, and scipy.

## What it does

Two HackRF Ones (in PortaPacks) talk to each other over the air:
- **OOK modulation** with 100 kHz carrier offset to dodge the DC spike
- **Framed packets** with preamble, sync word, CRC-16 error checking
- **Reliable protocol** with sequence numbers, ACK/NACK, and retransmission
- **Wideband spectrum scanner** using `hackrf_sweep` (1 MHz to 6 GHz)
- **Signal visualization** — spectrogram, envelope, decoded bits, protocol timeline

## Signal Analysis

What a transmitted "Hello HackRF!" looks like through the demodulation chain:

![Signal Analysis](docs/signal_analysis.png)

Top to bottom: spectrogram showing the 100 kHz carrier burst, demodulated envelope with adaptive threshold, zoomed OOK symbols, and decoded bit stream (preamble → sync → length → payload → CRC).

## Protocol Round-Trip

Half-duplex DATA + ACK exchange between two devices:

![Protocol Timeline](docs/protocol_timeline.png)

Each device owns one HackRF. The sender transmits DATA, switches to RX, and waits for ACK. The receiver listens, decodes the DATA, waits for the sender's TX→RX switch (~65 ms), then sends ACK back.

**Optimization story:** Initial round-trip was 25 seconds. Tuned capture windows, TX duration floor, and switch delays down to **6.5 seconds**.

## Spectrum Scanner

400 MHz – 1.7 GHz swept in a single pass using `hackrf_sweep`:

![Spectrum Scan](docs/spectrum_scan.png)

TV broadcast around 491/600 MHz, cellular at 750–850 MHz, ISM at 915 MHz. The old per-step scanner took ~10 subprocess launches for 10 MHz — `hackrf_sweep` covers 1300 MHz in under a second.

## Quick Start

```bash
# Prerequisites
pip install numpy scipy matplotlib
# hackrf tools must be installed (hackrf_transfer, hackrf_sweep)

# Edit config.py with your device serials
# (find them with: hackrf_info)

# Send a message between two HackRFs
python3 demo.py "Hello from HackRF!"

# Reliable send with ACK (two terminals)
python3 protocol.py rx                    # Terminal 1: receiver
python3 protocol.py send "Hello with ACK" # Terminal 2: sender

# Scan the spectrum
python3 scanner.py 88 108                 # FM radio band
python3 scanner.py 400 1700 --plot        # Wide sweep with plot
python3 scanner.py 900 930 --fine         # ISM band, 100 kHz resolution

# Visualize captured signals
python3 visualize.py                      # Spectrogram + demod analysis
python3 visualize_protocol.py             # Protocol timeline
```

## Project Structure

| File | Purpose |
|------|---------|
| `config.py` | Device serials, frequency, sample rate, gain, framing constants |
| `modulation.py` | OOK modulation/demodulation, frame building, CRC-16 |
| `demo.py` | Simple TX→RX hello world (two devices, threaded) |
| `protocol.py` | Reliable transport — DATA/ACK/NACK with retransmission |
| `scanner.py` | Wideband spectrum scanner using `hackrf_sweep` |
| `visualize.py` | 4-panel signal analysis (spectrogram, envelope, OOK, bits) |
| `visualize_protocol.py` | Protocol round-trip timeline visualization |
| `streaming.py` | Experimental streaming demodulator (WIP) |

## How the Modulation Works

```
Transmitter                              Receiver
──────────                               ────────
payload                                  IQ samples (int8)
  ↓ CRC-16                                ↓ complex signal
  ↓ frame (preamble+sync+len+data+crc)    ↓ mix down by 100 kHz
  ↓ OOK: bit=1 → carrier, bit=0 → silence ↓ lowpass filter (30 kHz, 4th order Butterworth)
  ↓ carrier at +100 kHz offset             ↓ envelope = |filtered|
  ↓ IQ samples (int8, amplitude 120)       ↓ adaptive threshold
  ↓ hackrf_transfer -t                     ↓ symbol sampling (phase search)
  ~~~~~~~~~~~~ 915 MHz ~~~~~~~~~~~~~→      ↓ sync word detection
                                           ↓ CRC verify
                                           payload
```

## Hardware

- 2x HackRF One (r9) in PortaPack enclosures
- Firmware: 2026.01.3 (Device 0), v1.9.1 (Device 1)
- Stock telescopic antennas, ~1 meter apart on desk

## Notes

- `hackrf_transfer -r -` (stdout pipe) does not stream — only outputs headers. File-based capture is required.
- `pyhackrf2` only reliably opens device index 0. Device 1 gets `HACKRF_ERROR_LIBUSB`. The library also segfaults on `close()`.
- Device 0's RX was dead out of the box — fixed by reflashing CPLD with firmware v2026.01.3.
- TX→RX hardware switch time is ~65 ms. The protocol accounts for this.

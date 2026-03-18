"""
ECG Receipt Printer — SD Festival of Science & Engineering Edition
==================================================================

Streams ECG data from an Arduino (USB or Bluetooth serial), displays a live plot,
and prints a receipt with ECG waveform and HR metrics on demand.

Workflow:
  1. Read ECG samples from serial (format: index,value or value)
  2. Maintain a rolling buffer for visualization and processing
  3. Press 'P' to process data → compute BPM/HRV → render receipt → print
  4. Press 'Q' to quit

Configuration:
  - Set PORT and BAUD below to match your device
  - Arduino USB typically uses 115200 baud
  - JDY-31 Bluetooth typically uses 9600 baud

Dependencies:
  pip install pyusb numpy pillow pyserial matplotlib scipy neurokit2

Windows USB printing setup:
  - Install WinUSB driver using Zadig: https://zadig.akeo.ie
  - Select your thermal printer (e.g., Vretti) and install driver

Notes:
  - Requires ~10s of data for stable HRV (RMSSD)
  - Plot updates in real time; printing runs in a background thread
  - ESC/POS printing is handled via libusb (no OS print driver)

"""
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ONLY CHANGE THESE:
PORT = 'COM4'       # COM# for Windows devices # ls /dev/cu.*
BAUD = 115200       # 115200 (USB) | 115200 (JDY-31 Bluetooth)
# Change lines 53-54 from printer.py with valid fonts paths.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Imports
import sys
import time
import threading
from collections import deque

import numpy as np
import matplotlib.pyplot as plt
import serial

from ecg import process_raw_ecg
from printer import render_full_receipt, image_to_escpos, send_to_printer, INIT, FEED, CUT

# ── ECG streaming config ──────────────────────────────────────────────────────

FS             = 200   # Hz — must match Arduino SAMPLE_RATE
WINDOW_S       = 10    # seconds of data to buffer and capture (10s min for reliable HRV)
PRINT_WINDOW_S = 6   # seconds of ECG trace shown on the printed receipt
N              = int(FS * WINDOW_S)


# ── Live streaming + plot ─────────────────────────────────────────────────────
def print_ecg_raw(raw_samples, sample_rate=FS, debug=False):
    """Process raw ADC samples and print. Called by the key handler."""
    data    = process_raw_ecg(raw_samples, sample_rate, print_window_s=PRINT_WINDOW_S)
    print("  Rendering receipt...")
    img     = render_full_receipt(data)
    if debug:
        np.save('raw.npy', raw_samples)
        np.save('processed.npy', data)
        img.save("test.png")
    escpos  = image_to_escpos(img)
    payload = INIT + escpos + FEED + CUT
    print(f"  Sending {len(payload):,} bytes to printer...")
    send_to_printer(payload)
    print("  Done!")


def run_live(ser):
    """Read serial stream, show live plot. Press P to print, Q to quit."""
    buf         = deque(maxlen=N)   # stores (t_sec, adc_value)
    printing    = False
    should_quit = False

    # ── Serial reader runs in its own thread so GUI never blocks it ───────────
    _debug_lines = [0]   # count lines received for early diagnosis

    def _read_serial():
        while not should_quit:
            try:
                raw = ser.readline().decode(errors="ignore").strip()
            except Exception:
                break
            if not raw:
                continue
            _debug_lines[0] += 1
            if _debug_lines[0] <= 5:
                print(f"  [serial debug] line {_debug_lines[0]}: {raw!r}")
            parts   = raw.split(",")
            val_str = parts[-1].strip()
            if not val_str.lstrip("-").isdigit():
                continue
            v = int(val_str)
            if len(parts) == 2 and parts[0].strip().isdigit():
                t = int(parts[0].strip()) / FS
            elif buf:
                t = buf[-1][0] + 1.0 / FS
            else:
                t = 0.0
            buf.append((t, v))

    reader = threading.Thread(target=_read_serial, daemon=True)

    # ── Plot setup ────────────────────────────────────────────────────────────
    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 4))
    fig.canvas.manager.set_window_title("ECG Live — Press P to print, Q to quit")
    line_plot, = ax.plot([], [], color='#e53935', linewidth=0.8)
    ax.set_title("ECG stream  |  P = print  |  Q = quit", fontsize=11)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("ADC")
    ax.set_xlim(-WINDOW_S, 0)
    ax.set_facecolor('#1a1a2e')
    fig.patch.set_facecolor('#1a1a2e')
    ax.tick_params(colors='white')
    ax.xaxis.label.set_color('white')
    ax.yaxis.label.set_color('white')
    ax.title.set_color('white')
    plt.tight_layout()
    plt.show(block=False)

    def on_key(event):
        nonlocal printing, should_quit

        if event.key == 'q':
            should_quit = True

        elif event.key == 'p':
            if printing:
                print("Already printing — wait for it to finish.")
                return
            if len(buf) < FS * 2:
                print(f"Buffer only {len(buf)/FS:.1f}s full — wait for more data.")
                return

            _, raw_vals = zip(*buf)
            samples = list(raw_vals)

            def do_print():
                nonlocal printing
                printing = True
                print(f"\nCapturing {len(samples)} samples ({len(samples)/FS:.1f}s)...")
                try:
                    print_ecg_raw(samples)
                except Exception as e:
                    print(f"  Print failed: {e}")
                finally:
                    printing = False

            threading.Thread(target=do_print, daemon=True).start()

    fig.canvas.mpl_connect("key_press_event", on_key)

    print(f"Streaming from {PORT} at {BAUD} baud...")
    print("Watch the plot — press P to print, Q to quit.\n")

    reader.start()

    PLOT_INTERVAL = 0.05   # redraw every 50 ms (~20 fps)
    try:
        while not should_quit:
            if buf:
                t_last = buf[-1][0]
                xs = [tt - t_last for tt, _ in buf]
                ys = [vv for _, vv in buf]
                line_plot.set_data(xs, ys)
                ax.relim()
                ax.autoscale_view(scalex=False, scaley=True)
            plt.pause(PLOT_INTERVAL)   # processes GUI events + sleeps
    finally:
        plt.ioff()
        plt.close(fig)

if __name__ == '__main__':
    print(f"Opening {PORT} at {BAUD} baud...")
    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
    except serial.SerialException as e:
        print(f"Could not open {PORT}: {e}")
        print("Check Device Manager for the correct COM port number.")
        sys.exit(1)

    time.sleep(2)          # wait for Arduino auto-reset
    ser.reset_input_buffer()

    try:
        run_live(ser)
    finally:
        ser.close()

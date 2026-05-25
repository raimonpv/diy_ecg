# DIY ECG

A homemade ECG device that streams live heart signals, displays them in real time, and prints a receipt with your heart rate and ECG waveform on a thermal printer.

Built for the **San Diego Festival of Science & Engineering** by the **Bioengineering Graduate Society at UCSD**.

## Safety

> **This is NOT a medical device.** It is an educational demo only. Do not use it to diagnose or monitor any medical condition.
>
> - **Do not use on people with pacemakers or other implanted devices.**
> - It is **strongly recommended** to power the Arduino with a **9V battery** and use the **Bluetooth module** for data transmission. This electrically isolates the device from mains power, eliminating any risk of current leakage through the electrodes.
> - Never connect the Arduino to a wall-powered computer while electrodes are attached to a person.

## What it does

1. Arduino reads your heart signal at 200 Hz
2. Python shows a live ECG plot on screen
3. Press **P** to print a receipt with your ECG waveform, BPM, and HRV
4. Press **Q** to quit

## Hardware

### Components

- Arduino (Uno, Nano, etc.)
- AD8232 ECG sensor module (or similar)
- JDY-31 Bluetooth module (optional, for wireless)
- Vretti thermal receipt printer (58mm, USB)
- ECG electrode pads + cables

### Wiring

```
                     ┌───────────────┐
  ┌────────┐         │  ARDUINO UNO  │         ┌───────────┐
  │ AD8232 │         │               │         │ JDY-31    │
  │ ECG    │         │               │         │ Bluetooth │
  │ Module │         │               │         │           │
  │        │         │            D2 ├─────────┤ TX        │
  │ OUTPUT ├─────────┤ A0         D4 ├───[*]───┤ RX        │
  │    VCC ├─────────┤ 5V       3.3V ├─────────┤ VCC       │
  │    GND ├─────────┤ GND       GND ├─────────┤ GND       │
  └───┬────┘         └───────────────┘         └───────────┘
      │                                                  
      │                       
      │
 ┌────┴────┐
Electrode Pads
```

**[*] Voltage Divider on pin D4 → BT RX** (5V → 3.3V):

```
  Arduino D4 ───┤ R ├───┬───→ JDY-31 RX
                        │
                       ┤2R├
                        │
                       GND
```

Use **any resistor R and another resistor of 2R** — for example **1 kΩ and 2 kΩ**, or **10 kΩ and 20 kΩ**. The 1:2 ratio is what matters, not the absolute value.

**Notes:**
- The JDY-31 RX pin is 3.3V logic — the voltage divider steps down the Arduino's 5V output
- The AD8232 has 3 electrode leads: RA, LA, and a reference lead (RL)
- For battery-powered operation, connect a 9V battery to the Arduino barrel jack instead of USB

## Software Setup

### 1. Arduino

Open `arduino/main.ino` in the Arduino IDE and upload it to your board. This samples the ECG signal at 200 Hz and streams it over USB Serial (and Bluetooth if connected).

No external libraries are needed — only the built-in `SoftwareSerial.h`. Before uploading, set the correct board and port under **Tools → Board** and **Tools → Port**.

### 2. Python

```bash
# Create the conda environment
conda env create -f environment.yml
conda activate ecg

# Run
python python/main.py
```

The serial port is auto-detected. If it fails, specify it manually:

```bash
python python/main.py --port <PORT>
```

Common port names: `/dev/ttyUSB0` (Linux), `/dev/cu.usbserial-*` (macOS), `COM4` (Windows).

### 3. Thermal Printer (optional)

The receipt printer communicates via USB using ESC/POS commands.

**Linux/macOS:** Should work out of the box with libusb.

**Windows:** Install the WinUSB driver using [Zadig](https://zadig.akeo.ie):
1. Plug in the printer
2. Open Zadig, select your printer (e.g., "Vretti")
3. Install the WinUSB driver

### 4. Bluetooth (optional)

If using a JDY-31 Bluetooth module, you may need to configure its baud rate to 115200. Upload `arduino/buad.ino`, open the Serial Monitor, and send `AT+BAUD8` to set 115200 baud.

## Usage

```bash
python python/main.py
```

- A live plot window opens showing your ECG signal
- Wait ~10 seconds for the buffer to fill (needed for accurate HRV)
- Press **P** to print a receipt — the print job runs on a background thread, so the live plot keeps updating during printing
- Press **Q** to quit

## Verifying it works

A quick sanity check so you know things are running correctly before letting anyone try the demo:

- The terminal shows a continuous stream of `i,v` lines (index and ADC value) once `main.py` starts.
- The live plot window opens within ~2 seconds.
- With electrodes properly placed on a person, you should see clear QRS spikes about once per second — a sharp peak rising well above the baseline.
- HRV needs ~10 seconds of clean signal before it stabilizes. The first reading after pressing **P** can be noisy; wait a bit longer if it looks off.
- Typical resting BPM: **55–95**. Numbers wildly outside that range usually mean a noisy electrode contact, not a heart condition.

## Receipt Output

Each printed receipt includes:

- Date and time
- Heart rate (BPM)
- Heart rate variability (HRV, RMSSD in ms)
- 6-second ECG waveform trace
- Event branding

## Troubleshooting

**Python can't find the Arduino**
- List available ports: `python -m serial.tools.list_ports`
- Pass it explicitly: `python python/main.py --port /dev/ttyUSB0` (or `COM4`, etc.)
- On Linux, add yourself to the `dialout` group so you can access serial devices without `sudo`:
  ```bash
  sudo usermod -aG dialout $USER
  ```
  Then log out and back in.

**Printer not responding**
- Confirm the printer is detected: `lsusb` (Linux) or `system_profiler SPUSBDataType` (macOS). Look for VID:PID `1fc9:2016`.
- If your printer has a different VID:PID, edit the `VENDOR_ID` and `PRODUCT_ID` constants near the top of [`python/printer.py`](python/printer.py).
- On Linux, accessing USB devices without root requires a udev rule. Create `/etc/udev/rules.d/99-vretti-printer.rules` with:
  ```
  SUBSYSTEM=="usb", ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="2016", MODE="0666"
  ```
  Then run `sudo udevadm control --reload-rules && sudo udevadm trigger` and replug the printer.
- If no system fonts are found, the printer falls back to Pillow's tiny default font — the receipt still prints, it just looks uglier. Install a system font like Liberation Serif if you care about how it looks.

**Plot is flat or looks like pure noise**
- Check the **LO+** and **LO−** LEDs on the AD8232 — if either is lit, an electrode has poor skin contact. Reseat the pads.
- Make sure the reference lead (RL) is connected.
- Pads dry out fast — use fresh ones.
- If the device is plugged into a wall-powered laptop via USB, switch to a 9V battery + Bluetooth. Mains-coupled noise (~50/60 Hz hum) is the most common culprit.

**Bluetooth garbled or no data**
- The JDY-31 ships at 9600 baud, but the firmware in `arduino/main.ino` speaks 115200. Upload `arduino/buad.ino` once, open the Serial Monitor, and send `AT+BAUD8` to reconfigure the module to 115200. After that the module remembers the setting, so you only need to do this once per JDY-31.

## Project Structure

```
diy_ecg/
├── arduino/
│   ├── main.ino          # ECG sampling firmware (200 Hz)
│   └── buad.ino          # Bluetooth module configuration utility
├── python/
│   ├── main.py           # Live streaming, plotting, and print trigger
│   ├── ecg.py            # Signal processing (R-peak detection, BPM, HRV)
│   └── printer.py        # Receipt rendering and USB thermal printing
├── environment.yml       # Conda environment
└── README.md
```

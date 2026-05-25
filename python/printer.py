"""
Thermal printer module for ECG receipt generation (ESC/POS over USB).

This module:
  - Renders ECG data and summary metrics (BPM, HRV) into a receipt-style image
  - Converts images into ESC/POS raster format
  - Sends print jobs directly to a USB thermal printer using libusb

Key features:
  - ECG waveform rendering with grid
  - Timestamped stats (BPM, HRV)
  - Custom branding footer
  - Automatic USB bulk endpoint detection

Intended for real-time demos or experiments (e.g., ECG streaming + printing).
"""

# Imports
import datetime
import numpy as np
import usb.core
import usb.util
import usb.backend.libusb1 as _libusb1
from PIL import Image, ImageDraw, ImageFont
import libusb_package 

_USB_BACKEND = _libusb1.get_backend(find_library=libusb_package.find_library)

# ── USB / ESC-POS ─────────────────────────────────────────────────────────────
VENDOR_ID  = 0x1fc9
PRODUCT_ID = 0x2016
EP_OUT     = 0x01

ESC        = b'\x1b'
GS         = b'\x1d'
INIT       = ESC + b'@'
FEED       = ESC + b'd\x03'
CUT        = GS  + b'V\x41\x00'

# ── Layout ────────────────────────────────────────────────────────────────────
PAPER_WIDTH   = 576
STRIP_H       = 52
BOT_STRIP_H   = 110
GRAPH_PAD     = 14
GRID_STEP     = 20
GRID_COLOR    = 180
LINE_COLOR    = 0
BG_COLOR      = 255
PX_PER_SAMPLE = 1.2
MIN_CANVAS_W  = 800

# Font detection — tries common paths per OS, falls back to Pillow default
import os

def _find_font(candidates):
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None

_BODY_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/Times.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    # Linux
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/LiberationSerif-Regular.ttf",
    # Windows
    "C:\\Windows\\Fonts\\times.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
]

_BOLD_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    # Linux
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/LiberationSerif-Bold.ttf",
    # Windows
    "C:\\Windows\\Fonts\\timesbd.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]

FONT_BODY = _find_font(_BODY_CANDIDATES)
FONT_BOLD = _find_font(_BOLD_CANDIDATES)

# ── Rendering ─────────────────────────────────────────────────────────────────
def _text_size(font, text):
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def _draw_ecg_zone(draw, ecg_points, x0, y0, w, h):
    for gx in range(x0, x0 + w, GRID_STEP):
        draw.line([(gx, y0), (gx, y0 + h)], fill=GRID_COLOR, width=1)
    for gy in range(y0, y0 + h, GRID_STEP):
        draw.line([(x0, gy), (x0 + w, gy)], fill=GRID_COLOR, width=1)
    draw.rectangle([x0, y0, x0 + w - 1, y0 + h - 1], outline=60, width=2)

    arr    = np.array(ecg_points)
    lo, hi = arr.min(), arr.max()
    span   = hi - lo if hi != lo else 1.0
    inner  = h - GRAPH_PAD * 2
    xs     = np.linspace(x0, x0 + w, len(arr))
    ys     = y0 + GRAPH_PAD + inner * (1.0 - (arr - lo) / span)
    pts    = [(float(x), float(y)) for x, y in zip(xs, ys)]
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=LINE_COLOR, width=2)


def render_full_receipt(data):
    bpm     = data['bpm']
    hrv     = data['hrv']
    ecg_pts = data['ecg_points']
    now     = datetime.datetime.now()

    def _load_font(path, size):
        if path:
            return ImageFont.truetype(path, size)
        return ImageFont.load_default()

    font_stats = _load_font(FONT_BODY, 20)
    font_bpm   = _load_font(FONT_BOLD, 28)
    font_org1  = _load_font(FONT_BOLD, 36)
    font_org2  = _load_font(FONT_BOLD, 28)

    canvas_w = max(MIN_CANVAS_W, int(len(ecg_pts) * PX_PER_SAMPLE))
    canvas_h = PAPER_WIDTH
    graph_y  = STRIP_H
    graph_h  = canvas_h - STRIP_H - BOT_STRIP_H

    img  = Image.new('L', (canvas_w, canvas_h), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Top strip
    draw.line([(0, STRIP_H), (canvas_w, STRIP_H)], fill=0, width=1)
    stats = [
        (now.strftime('%b %d, %Y'), font_stats, 0),
        (now.strftime('%I:%M %p'),  font_stats, 100),
        (f'{bpm} bpm',              font_bpm,   0),
        (f'HRV  {hrv} ms',         font_stats, 0),
    ]
    col_w = canvas_w // len(stats)
    for i, (text, font, fill) in enumerate(stats):
        tw, th = _text_size(font, text)
        draw.text((i * col_w + (col_w - tw) // 2, (STRIP_H - th) // 2),
                  text, font=font, fill=fill)

    # ECG graph
    _draw_ecg_zone(draw, ecg_pts, 0, graph_y, canvas_w, graph_h)

    # Bottom branding
    bot_y     = canvas_h - BOT_STRIP_H
    line_slot = BOT_STRIP_H // 2
    draw.line([(0, bot_y), (canvas_w, bot_y)], fill=0, width=1)

    org1     = 'San Diego Festival of Science and Engineering'
    o1w, o1h = _text_size(font_org1, org1)
    draw.text(((canvas_w - o1w) // 2, bot_y + (line_slot - o1h) // 2),
              org1, font=font_org1, fill=0)

    org2     = 'Bioengineering Graduate Society UCSD'
    o2w, o2h = _text_size(font_org2, org2)
    draw.text(((canvas_w - o2w) // 2, bot_y + line_slot + (line_slot - o2h) // 2),
              org2, font=font_org2, fill=0)

    img = img.rotate(-90, expand=True)
    return img


# ── USB printing ──────────────────────────────────────────────────────────────
def image_to_escpos(img):
    img_1bit    = img.convert('1')
    width_px    = img_1bit.width
    height_px   = img_1bit.height
    width_bytes = (width_px + 7) // 8

    xL = width_bytes & 0xFF
    xH = (width_bytes >> 8) & 0xFF
    yL = height_px & 0xFF
    yH = (height_px >> 8) & 0xFF
    header   = GS + b'v0' + bytes([0, xL, xH, yL, yH])
    pixels   = img_1bit.load()
    row_data = bytearray()
    for y in range(height_px):
        for byte_x in range(width_bytes):
            byte = 0
            for bit in range(8):
                x = byte_x * 8 + bit
                if x < width_px and pixels[x, y] == 0:
                    byte |= (0x80 >> bit)
            row_data.append(byte)
    return header + bytes(row_data)


def _find_bulk_out(dev):
    """Return the first bulk-OUT endpoint on the device, or fall back to EP_OUT."""
    try:
        cfg  = dev.get_active_configuration()
        intf = cfg[(0, 0)]
        ep   = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress)
                    == usb.util.ENDPOINT_OUT
                and usb.util.endpoint_type(e.bmAttributes)
                    == usb.util.ENDPOINT_TYPE_BULK
            ),
        )
        if ep is not None:
            addr = ep.bEndpointAddress
            if addr != EP_OUT:
                print(f"  [USB] auto-detected bulk-OUT endpoint: 0x{addr:02x} "
                      f"(hardcoded was 0x{EP_OUT:02x})")
            return addr
    except Exception as e:
        print(f"  [USB] endpoint auto-detect failed ({e}), using hardcoded 0x{EP_OUT:02x}")
    return EP_OUT


def send_to_printer(data):
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID, backend=_USB_BACKEND)
    if dev is None:
        raise RuntimeError(
            "Printer not found.\n"
            "  • Make sure the printer is plugged in and powered on.\n"
            "  • Run Zadig → select the Vretti printer → install WinUSB driver.\n"
            f"  • Expected VID=0x{VENDOR_ID:04x}  PID=0x{PRODUCT_ID:04x}\n"
            "  • To list all USB devices: python -c \"import libusb_package, usb.core, usb.backend.libusb1; "
            "b=usb.backend.libusb1.get_backend(find_library=libusb_package.find_library); "
            "[print(d) for d in usb.core.find(find_all=True, backend=b)]\""
        )

    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except (NotImplementedError, usb.core.USBError):
        pass

    dev.set_configuration()
    usb.util.claim_interface(dev, 0)
    ep_addr = _find_bulk_out(dev)

    try:
        for i in range(0, len(data), 64):
            dev.write(ep_addr, data[i:i + 64], timeout=5000)
    finally:
        try:
            usb.util.release_interface(dev, 0)
        except usb.core.USBError:
            pass
        try:
            usb.util.dispose_resources(dev)
        except Exception:
            pass
        
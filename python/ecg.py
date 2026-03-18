"""
ECG processing utilities for heart rate and HRV estimation.

This module provides a lightweight pipeline to:
  - Clean raw ECG signals using neurokit2
  - Detect R-peaks
  - Compute heart rate (BPM) and HRV (RMSSD)
  - Normalize a short ECG window for visualization

Intended for real-time or near real-time processing of ECG data streams
(e.g., from microcontrollers or wearable devices).
"""

# Imports
import numpy as np
import neurokit2 as nk

def _metrics_from_peaks(peaks, sample_rate):
    """
    Compute heart-rate metrics from R-peak indices.

    Returns:
        bpm (int): Median heart rate (beats per minute)
        hrv (int): RMSSD (ms)
        min_bpm (int): Minimum instantaneous BPM
        max_bpm (int): Maximum instantaneous BPM
    """
    bpm = hrv = min_bpm = max_bpm = 0
    if len(peaks) >= 2:
        rr_s  = np.diff(peaks) / sample_rate
        # Keep physiologically plausible RR intervals (30–180 BPM)
        rr_ok = rr_s[(rr_s >= 0.33) & (rr_s <= 2.00)] 
        if len(rr_ok) >= 1:
            # Reject outliers: keep intervals within 20% of the median
            median_rr = float(np.median(rr_ok))
            rr_clean  = rr_ok[np.abs(rr_ok - median_rr) / median_rr < 0.20]
            if len(rr_clean) >= 1:
                bpm_arr = 60.0 / rr_clean
                bpm     = int(round(float(np.median(bpm_arr))))   # median > mean for robustness
                min_bpm = int(round(float(np.min(bpm_arr))))
                max_bpm = int(round(float(np.max(bpm_arr))))
                # RMSSD: needs at least 2 RR intervals (3 peaks)
                if len(rr_clean) >= 2:
                    hrv = int(round(float(
                        np.sqrt(np.mean(np.diff(rr_clean) ** 2)) * 1000
                    )))
    return bpm, hrv, min_bpm, max_bpm


def process_raw_ecg(raw_samples, sample_rate, print_window_s = 6):
    """
    Process raw ECG samples into HR metrics and a normalized waveform.

    Steps:
      1. Clean ECG + detect R-peaks via neurokit2.ecg_process
      2. Compute BPM, HRV (RMSSD), and range
      3. Normalize last `print_window_s` seconds to [-1, 1]

    Args:
        raw_samples (array-like): Raw ECG signal (ADC values)
        sample_rate (int): Sampling frequency in Hz
        print_window_s (int, optional): Seconds to keep for visualization

    Returns:
        dict: {
            "bpm", "hrv", "min_bpm", "max_bpm", "ecg_points"
        }
    """
    ecg_array = np.array(raw_samples, dtype=float)

    # Clean ECG and detect R-peaks using nk
    signals, info = nk.ecg_process(ecg_array, sampling_rate=sample_rate)
    cleaned = signals["ECG_Clean"]
    peaks = info["ECG_R_Peaks"]

    bpm, hrv, min_bpm, max_bpm = _metrics_from_peaks(peaks, sample_rate)

    # Normalise the last PRINT_WINDOW_S seconds to [-1, 1] for rendering
    render_n      = int(sample_rate * print_window_s)
    render_signal = cleaned[-render_n:]
    lo, hi = render_signal.min(), render_signal.max()
    span   = hi - lo if hi != lo else 1.0
    norm   = ((render_signal - lo) / span * 2.0 - 1.0).tolist()

    print(
        f"Processed (neurokit2): BPM={bpm} HRV={hrv}ms "
        f"range={min_bpm}-{max_bpm} peaks={len(peaks)}"
    )
    return {
        "bpm": bpm,
        "hrv": hrv,
        "min_bpm": min_bpm,
        "max_bpm": max_bpm,
        "ecg_points": norm,
    }
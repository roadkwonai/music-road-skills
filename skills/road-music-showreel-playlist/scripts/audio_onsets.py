"""Measure adaptive source-audio attacks; never changes audio or installs tools."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np

RATE, WINDOW, HOP = 16000, 1024, 160


def detect(audio, minimum_spacing=0.27):
    if not math.isfinite(minimum_spacing) or minimum_spacing <= 0:
        raise ValueError('minimum spacing must be finite and positive')
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim != 1 or not np.all(np.isfinite(audio)):
        raise ValueError('audio must be finite mono samples')
    if len(audio) < WINDOW + HOP or not np.any(audio):
        return []
    frames = np.lib.stride_tricks.sliding_window_view(audio, WINDOW)[::HOP]
    frequency = np.fft.rfftfreq(WINDOW, 1 / RATE)
    band = (frequency >= 60) & (frequency <= 6500)
    window = np.hanning(WINDOW)
    flux = np.empty(len(frames) - 1)
    previous = None
    # Bound FFT memory for long tracks; retain the cross-block difference.
    for start in range(0, len(frames), 2048):
        spectrum = np.log1p(np.abs(np.fft.rfft(frames[start:start+2048] * window, axis=1))[:, band])
        if previous is not None:
            flux[start-1] = np.maximum(spectrum[0] - previous, 0).mean()
        delta = np.maximum(np.diff(spectrum, axis=0), 0).mean(axis=1)
        flux[start:start+len(delta)] = delta
        previous = spectrum[-1]
    if len(flux) < 5:
        return []
    flux = np.convolve(flux, [0.25, 0.5, 0.25], mode='same')
    floor = float(flux.max()) * 0.015
    candidates = []
    for i in range(2, len(flux)-2):
        if flux[i] < floor or flux[i] <= flux[i-1] or flux[i] < flux[i+1]:
            continue
        if flux[i] < np.quantile(flux[max(0,i-250):min(len(flux),i+251)], 0.70):
            continue
        time = (i * HOP + WINDOW * 0.75) / RATE
        candidates.append((time, float(flux[i])))
    selected = []
    for time, strength in sorted(candidates, key=lambda item: -item[1]):
        if all(abs(time-other[0]) >= minimum_spacing for other in selected):
            selected.append((time, strength))
    return sorted(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--min-spacing', type=float, default=0.27)
    args = parser.parse_args()
    source, output = args.audio.resolve(), args.out.resolve()
    if output == source or output.exists():
        parser.error('output must be a new file, separate from the source')
    if not math.isfinite(args.min_spacing) or args.min_spacing <= 0:
        parser.error('minimum spacing must be finite and positive')
    with source.open('rb') as handle:
        source_hash = hashlib.file_digest(handle, 'sha256').hexdigest()
    decoded = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(source), '-ar', str(RATE), '-ac', '1', '-f', 'f32le', '-'])
    samples = np.frombuffer(decoded, dtype='<f4')
    events = detect(samples, args.min_spacing)
    result = {
        'sourceAudio': str(source), 'sourceAudioSha256': source_hash,
        'durationSeconds': len(samples)/RATE, 'sampleRate': RATE,
        'windowSamples': WINDOW, 'hopSamples': HOP,
        'minimumSpacingSeconds': args.min_spacing,
        'method': 'positive log-spectral-flux peaks; local 5s 70% threshold; not a BPM grid or isolated drum labels',
        'analysisOnly': True, 'sourceAudioModified': False,
        'events': [{'timeSeconds': round(t,5), 'strength': round(s,7)} for t,s in events],
    }
    with output.open('x') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({'output': str(output), 'events': len(events), 'sourceAudioSha256': source_hash}))


if __name__ == '__main__':
    main()

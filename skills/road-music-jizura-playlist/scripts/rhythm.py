#!/usr/bin/env python3
"""Fit a fixed beat grid to local audio attacks without claiming downbeats or vocal alignment."""
import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np


SAMPLE_RATE = 22050
HOP = 220
NFFT = 2048
BANDS = ((30, 180), (180, 2000), (2000, 9000))


def finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name}: 유한한 숫자가 필요합니다')
    return float(value)


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    with Path(path).open(encoding='utf-8') as stream:
        return json.load(stream)


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def decode(audio):
    raw = subprocess.check_output([
        'ffmpeg', '-v', 'error', '-i', str(audio), '-f', 'f32le', '-ac', '1', '-ar', str(SAMPLE_RATE), '-'
    ])
    return np.frombuffer(raw, dtype='<f4').copy()


def require_samples(samples):
    if samples.size < NFFT:
        raise ValueError('빈 음원이거나 분석하기에 너무 짧습니다')
    if not np.isfinite(samples).all():
        raise ValueError('음원 표본에 NaN 또는 Infinity가 있습니다')
    if float(np.max(np.abs(samples))) < 1e-7:
        raise ValueError('무음 음원은 박자 그리드를 맞출 수 없습니다')


def onset_features(samples, sample_rate=SAMPLE_RATE):
    """Return audio attacks and RMS blocks; reusable by tests without decoding a file."""
    require_samples(samples)
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f'분석 샘플레이트는 {SAMPLE_RATE}Hz여야 합니다')
    frames = np.lib.stride_tricks.sliding_window_view(samples, NFFT)[::HOP]
    if not len(frames):
        raise ValueError('분석 프레임이 없습니다')
    freq = np.fft.rfftfreq(NFFT, 1 / sample_rate)
    masks = [(freq >= left) & (freq < right) for left, right in BANDS]
    window = np.hanning(NFFT).astype(np.float32)
    chunks, previous = [], None
    for start in range(0, len(frames), 1000):
        magnitude = np.abs(np.fft.rfft(frames[start:start + 1000] * window, axis=1))
        logs = np.log1p(magnitude * 5)
        prior = np.vstack([previous if previous is not None else logs[0], logs[:-1]])
        positive = np.maximum(logs - prior, 0)
        chunks.append(np.stack([positive[:, mask].mean(axis=1) for mask in masks], axis=1))
        previous = logs[-1]
    flux = np.vstack(chunks)
    scale = np.maximum(np.percentile(flux, 95, axis=0), 1e-6)
    strengths = flux / scale
    combined = strengths[:, 0] * .5 + strengths[:, 1] * .25 + strengths[:, 2] * .25
    times = (np.arange(len(frames)) * HOP + NFFT / 2) / sample_rate
    onsets = []
    for index in range(5, len(combined) - 5):
        if combined[index] >= np.max(combined[index - 5:index + 6]) and combined[index] > .65:
            onsets.append({
                'time': round(float(times[index]), 4), 'strength': round(float(combined[index]), 4),
                'low': round(float(strengths[index, 0]), 4), 'mid': round(float(strengths[index, 1]), 4),
                'high': round(float(strengths[index, 2]), 4),
            })
    block_seconds = 5
    blocks = []
    duration = len(samples) / sample_rate
    for start in np.arange(0, duration, block_seconds):
        stop = min(start + block_seconds, duration)
        segment = samples[round(start * sample_rate):round(stop * sample_rate)]
        blocks.append({'start': round(float(start), 3), 'end': round(float(stop), 3),
                       'rms': float(np.sqrt(np.mean(segment * segment)))})
    return onsets, blocks


def circular_distance(times, bpm, phase):
    period = 60 / bpm
    return np.abs(((times - phase + period / 2) % period) - period / 2)


def score_grid(times, weights, bpm, phase):
    distance = circular_distance(times, bpm, phase)
    return float(np.sum(np.exp(-(distance / .022) ** 2 / 2) * weights) / np.sum(weights))


def fitting_window(duration, blocks):
    left, right = duration * .2, duration * .9
    candidates = [b for b in blocks if b['start'] >= left and b['end'] <= right]
    if not candidates:
        raise ValueError('리듬 적합용 중간 구간이 없습니다')
    rms = np.array([b['rms'] for b in candidates])
    threshold = float(np.median(rms))
    active = [b for b in candidates if b['rms'] >= threshold]
    return left, right, threshold, active


def grid_ticks(bpm, phase, start, stop):
    period = 60 / bpm
    first = math.ceil((start - phase) / period)
    return phase + np.arange(first, math.floor((stop - phase) / period) + 1) * period


def fit_grid(onsets, blocks, duration, native_bpm, native_phase):
    left, right, rms_threshold, active_blocks = fitting_window(duration, blocks)
    times = np.array([point['time'] for point in onsets], dtype=float)
    weights = np.array([point['low'] * .7 + point['high'] * .3 for point in onsets], dtype=float)
    active = np.zeros(len(times), dtype=bool)
    for block in active_blocks:
        active |= (times >= block['start']) & (times < block['end'])
    mask = active & (weights > 1)
    times, weights = times[mask], weights[mask]
    if len(times) < 16:
        raise ValueError('강한 중간 구간의 온셋이 부족합니다')
    lo, hi = native_bpm * .9, native_bpm * 1.1
    coarse = []
    for bpm in np.arange(lo, hi + .0001, .05):
        period = 60 / bpm
        phases = np.arange(0, period, .005)
        delta = np.abs(((times[:, None] - phases[None, :] + period / 2) % period) - period / 2)
        scores = (np.exp(-(delta / .022) ** 2 / 2) * weights[:, None]).sum(axis=0) / weights.sum()
        index = int(scores.argmax())
        coarse.append((float(scores[index]), float(bpm), float(phases[index])))
    _, seed, _ = max(coarse)
    best = []
    for bpm in np.arange(max(lo, seed - .1), min(hi, seed + .1) + .0001, .01):
        period = 60 / bpm
        phases = np.arange(0, period, .005)
        delta = np.abs(((times[:, None] - phases[None, :] + period / 2) % period) - period / 2)
        scores = (np.exp(-(delta / .022) ** 2 / 2) * weights[:, None]).sum(axis=0) / weights.sum()
        index = int(scores.argmax())
        best.append((float(scores[index]), float(bpm), float(phases[index])))
    fit_score, bpm, phase = max(best)
    native_score = score_grid(times, weights, native_bpm, native_phase)

    def distance_stats(candidate_bpm, candidate_phase):
        distance = circular_distance(times, candidate_bpm, candidate_phase)
        strong = weights >= np.percentile(weights, 75)
        ticks = grid_ticks(candidate_bpm, candidate_phase, left, right)
        strong_times = times[strong]
        matched_strong = np.any(np.abs(strong_times[:, None] - ticks[None, :]) <= .04, axis=1)
        matched_ticks = np.any(np.abs(ticks[:, None] - strong_times[None, :]) <= .04, axis=1)
        return {
            'weightedScore': round(score_grid(times, weights, candidate_bpm, candidate_phase), 6),
            'strongOnsetsWithin40msRatio': round(float(np.mean(distance[strong] <= .04)), 4),
            'medianMs': round(float(np.median(distance) * 1000), 2),
            'p95Ms': round(float(np.percentile(distance, 95) * 1000), 2),
            'toleranceMs': 40, 'selectedOnsets': int(len(times)), 'strongOnsets': int(len(strong_times)),
            'strongOnsetsMatched': int(matched_strong.sum()),
            'strongOnsetsUnmatched': int((~matched_strong).sum()),
            'strongOnsetRecall': round(float(matched_strong.mean()), 4),
            'gridTicks': int(len(ticks)), 'gridTicksWithStrongOnset': int(matched_ticks.sum()),
            'gridTickPrecision': round(float(matched_ticks.mean()), 4),
        }
    alternatives = []
    for label, candidate in (('half', native_bpm / 2), ('double', native_bpm * 2)):
        if 20 <= candidate <= 400:
            period = 60 / candidate
            phases = np.arange(0, period, .005)
            scores = [score_grid(times, weights, candidate, value) for value in phases]
            alternatives.append({'relation': label, 'bpm': round(candidate, 4),
                                 'bestScore': round(max(scores), 6)})
    return {
        'fitWindow': {'start': round(left, 3), 'end': round(right, 3), 'rmsActiveThreshold': round(rms_threshold, 6),
                      'activeFiveSecondBlocks': len(active_blocks), 'onsets': int(len(times))},
        'best': {'bpm': round(bpm, 4), 'phase': round(phase, 4), 'score': round(fit_score, 6)},
        'native': {'bpm': round(native_bpm, 4), 'phase': round(native_phase, 4), 'score': round(native_score, 6)},
        'gridDistance': {'native': distance_stats(native_bpm, native_phase), 'fitted': distance_stats(bpm, phase)},
        'halfDoubleAmbiguity': alternatives,
    }


def beat_times(bpm, phase, duration):
    period = 60 / bpm
    return [round(phase + index * period, 4) for index in range(math.ceil((duration - phase) / period))
            if 0 <= phase + index * period < duration]


def native_values(analysis, actual_sha):
    audio = analysis.get('audio')
    if not isinstance(audio, dict):
        raise ValueError('native-analysis.audio가 없습니다')
    if audio.get('sha256') != actual_sha:
        raise ValueError('native-analysis의 오디오 SHA256이 입력과 다릅니다')
    bpm = finite_number(audio.get('bpm'), 'native-analysis.audio.bpm')
    beats = audio.get('beats')
    if not isinstance(beats, list) or not beats:
        raise ValueError('native-analysis.audio.beats가 없습니다')
    phase = finite_number(beats[0], 'native-analysis.audio.beats[0]')
    if not 20 <= bpm <= 400:
        raise ValueError('native-analysis BPM 범위가 올바르지 않습니다')
    return bpm, phase


def analyze(samples, source, digest, native_analysis):
    onsets, blocks = onset_features(samples)
    duration = len(samples) / SAMPLE_RATE
    native_bpm, native_phase = native_values(native_analysis, digest)
    fit = fit_grid(onsets, blocks, duration, native_bpm, native_phase)
    improvement = fit['best']['score'] - fit['native']['score']
    confidence = 'low' if fit['best']['score'] < .3 or improvement < .015 else 'medium'
    return {
        'audioSource': str(source), 'sha256': digest, 'duration': round(duration, 6),
        'analysis': {'sampleRate': SAMPLE_RATE, 'hopSamples': HOP, 'hopMs': round(HOP / SAMPLE_RATE * 1000, 3)},
        'source': {'nativeBpm': fit['native']['bpm'], 'nativePhase': fit['native']['phase']},
        'bestCandidate': fit['best'], 'confidence': confidence,
        'onset': onsets, 'beatTimesNative': beat_times(native_bpm, native_phase, duration),
        'beatTimesFitted': beat_times(fit['best']['bpm'], fit['best']['phase'], duration),
        'nativeVsFit': {'fitWindow': fit['fitWindow'], 'nativeScore': fit['native']['score'],
                        'fittedScore': fit['best']['score'], 'improvement': round(improvement, 6)},
        'gridDistance': fit['gridDistance'], 'halfDoubleAmbiguity': fit['halfDoubleAmbiguity'],
        'limits': '고정 템포 온셋 그리드의 권고일 뿐 다운비트, 실제 마디, 가창 정렬 또는 청취 품질의 증거가 아닙니다.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', required=True)
    parser.add_argument('--native-analysis', required=True)
    parser.add_argument('--out', required=True)
    options = parser.parse_args()
    audio, analysis_path, out = map(Path, (options.audio, options.native_analysis, options.out))
    if not audio.is_absolute() or not analysis_path.is_absolute() or not out.is_absolute():
        raise ValueError('--audio, --native-analysis, --out은 절대 경로여야 합니다')
    if not audio.is_file() or not analysis_path.is_file():
        raise ValueError('입력 음원 또는 native-analysis 파일이 없습니다')
    if out.exists():
        raise ValueError('--out은 아직 없는 새 디렉터리여야 합니다')
    digest = sha256(audio)
    result = analyze(decode(audio), audio, digest, read_json(analysis_path))
    out.mkdir(parents=True)
    write_json(out / 'rhythm.json', result)
    print(json.dumps({'ok': True, 'output': str((out / 'rhythm.json').resolve()), 'bpm': result['bestCandidate']['bpm'],
                      'phase': result['bestCandidate']['phase'], 'confidence': result['confidence']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Playlist-display settings, PCM playlist joins, and deterministic spectrum data."""

from __future__ import annotations

import math
from pathlib import Path
import subprocess
import unicodedata
import wave


SAMPLE_RATE = 48_000
CHANNELS = 2
SAMPLE_WIDTH = 2
ANALYSIS_RATE = 24_000
WINDOW_SAMPLES = 4_096
MIN_HZ = 40
MAX_HZ = 12_000
DISPLAY_KEYS = {"showSpectrum", "showQueue", "showNowPlaying", "channelName"}


def _is_skip(value):
    return value is None or (isinstance(value, str) and value.strip().casefold() == "skip")


def _display_flag(value, name):
    if _is_skip(value):
        return False
    if isinstance(value, bool):
        return value
    raise ValueError(f"{name}: bool, SKIP 또는 None만 사용할 수 있습니다")


def _channel_name(value):
    if _is_skip(value):
        return ""
    if not isinstance(value, str):
        raise ValueError("channelName: 문자열, SKIP 또는 None만 사용할 수 있습니다")
    value = value.strip()
    if len(value) > 120:
        raise ValueError("channelName: 최대 120자입니다")
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError("channelName: 개행, NUL 및 제어문자는 사용할 수 없습니다")
    return value


def normalize_display(value=None):
    """Normalize optional playlist display settings without guessing unanswered values."""
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("display: 객체 또는 None이어야 합니다")
    unknown = set(value) - DISPLAY_KEYS
    if unknown:
        raise ValueError(f"display: 지원하지 않는 키: {', '.join(sorted(unknown))}")
    return {
        "showSpectrum": _display_flag(value.get("showSpectrum"), "showSpectrum"),
        "showQueue": _display_flag(value.get("showQueue"), "showQueue"),
        "showNowPlaying": _display_flag(value.get("showNowPlaying"), "showNowPlaying"),
        "channelName": _channel_name(value.get("channelName")),
    }


def _validated_wav(path):
    path = Path(path)
    with wave.open(str(path), "rb") as source:
        if source.getcomptype() != "NONE":
            raise ValueError(f"{path}: PCM WAV가 아닙니다")
        if (source.getsampwidth(), source.getframerate(), source.getnchannels()) != (SAMPLE_WIDTH, SAMPLE_RATE, CHANNELS):
            raise ValueError(f"{path}: PCM16/48kHz/stereo WAV만 지원합니다")
        return source.getnframes()


def concat_wavs(paths, target):
    """Concatenate PCM16/48k/stereo WAVs by streaming frames in input order."""
    sources = [Path(path) for path in paths]
    if not sources:
        raise ValueError("연결할 WAV가 없습니다")
    target = Path(target)
    if target.exists():
        raise FileExistsError(f"기존 출력 파일을 덮어쓸 수 없습니다: {target}")

    # Validate every input before creating any output so a bad later file leaves no partial mix.
    total_frames = sum(_validated_wav(path) for path in sources)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as raw_target:
        with wave.open(raw_target, "wb") as destination:
            destination.setnchannels(CHANNELS)
            destination.setsampwidth(SAMPLE_WIDTH)
            destination.setframerate(SAMPLE_RATE)
            for path in sources:
                with wave.open(str(path), "rb") as source:
                    while frames := source.readframes(32_768):
                        destination.writeframesraw(frames)
    return total_frames


def _analysis_bands(bands):
    import numpy as np
    if isinstance(bands, bool) or not isinstance(bands, int) or not 1 <= bands <= 256:
        raise ValueError("bands: 1..256 정수가 필요합니다")
    frequencies = np.fft.rfftfreq(WINDOW_SAMPLES, d=1 / ANALYSIS_RATE)
    edges = np.geomspace(MIN_HZ, MAX_HZ, bands + 1)
    indices = []
    for index, (low, high) in enumerate(zip(edges[:-1], edges[1:])):
        if index == bands - 1:
            selected = np.flatnonzero((frequencies >= low) & (frequencies <= high))
        else:
            selected = np.flatnonzero((frequencies >= low) & (frequencies < high))
        if not len(selected):
            selected = np.array([np.abs(frequencies - math.sqrt(low * high)).argmin()])
        indices.append(selected)
    return indices


def _spectrum_frame(pcm, hann, band_indices):
    import numpy as np
    signal = np.zeros(WINDOW_SAMPLES, dtype=np.float64)
    if len(pcm):
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64) / 32768.0
        signal[: len(samples)] = samples
    if not signal.any():
        return [0] * len(band_indices)
    magnitudes = np.abs(np.fft.rfft(signal * hann)) / (hann.sum() / 2)
    values = []
    for indices in band_indices:
        magnitude = float(magnitudes[indices].max())
        decibels = 20 * math.log10(max(magnitude, 1e-12))
        values.append(int(round(max(0.0, min(255.0, (decibels + 72.0) * 255.0 / 72.0)))))
    return values


def _centered_window(buffer, buffer_start, center, total_samples):
    """Return a zero-padded 4096-sample window centred on one display instant."""
    half = WINDOW_SAMPLES // 2
    start = center - half
    end = start + WINDOW_SAMPLES
    copy_start = max(start, 0, buffer_start)
    copy_end = min(end, total_samples)
    result = bytearray(WINDOW_SAMPLES * SAMPLE_WIDTH)
    if copy_end > copy_start:
        source_start = (copy_start - buffer_start) * SAMPLE_WIDTH
        source_end = (copy_end - buffer_start) * SAMPLE_WIDTH
        destination_start = (copy_start - start) * SAMPLE_WIDTH
        result[destination_start: destination_start + source_end - source_start] = buffer[source_start:source_end]
    return result


def _pcm24k_mono(path):
    command = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0",
        "-vn", "-ac", "1", "-ar", str(ANALYSIS_RATE), "-f", "s16le", "-",
    ]
    return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def spectrum_data(wav_path, bands=48, dt=.05):
    """Analyze audio with a fixed t=0 STFT clock and return JSON-ready 0..255 bands."""
    import numpy as np
    if isinstance(dt, bool) or not isinstance(dt, (int, float)) or not math.isfinite(dt) or not .005 <= dt <= 2:
        raise ValueError("dt: 0.005..2초의 유한한 숫자가 필요합니다")
    requested_dt = float(dt)
    hop_samples = round(requested_dt * ANALYSIS_RATE)
    if hop_samples < 1:
        raise ValueError("dt가 너무 작습니다")
    dt = hop_samples / ANALYSIS_RATE
    band_indices = _analysis_bands(bands)
    hann = np.hanning(WINDOW_SAMPLES)
    process = _pcm24k_mono(Path(wav_path))
    buffer = bytearray()
    frames = []
    input_samples = 0
    buffer_start = 0
    frame_index = 0

    def emit_ready(eof=False):
        nonlocal buffer_start, frame_index
        half = WINDOW_SAMPLES // 2
        while True:
            center = frame_index * hop_samples
            end = center + half
            if not eof and end > input_samples:
                return
            if eof and frame_index >= math.ceil(input_samples / hop_samples):
                return
            frames.append(_spectrum_frame(_centered_window(buffer, buffer_start, center, input_samples), hann, band_indices))
            frame_index += 1
            next_start = frame_index * hop_samples - half
            discard_until = min(input_samples, max(buffer_start, next_start))
            if discard_until > buffer_start:
                del buffer[: (discard_until - buffer_start) * SAMPLE_WIDTH]
                buffer_start = discard_until

    try:
        assert process.stdout is not None
        while chunk := process.stdout.read(65_536):
            if len(chunk) % SAMPLE_WIDTH:
                raise ValueError("ffmpeg가 손상된 PCM 프레임을 반환했습니다")
            input_samples += len(chunk) // SAMPLE_WIDTH
            buffer.extend(chunk)
            emit_ready()
        emit_ready(eof=True)
        assert process.stderr is not None
        stderr = process.stderr.read().decode("utf-8", "replace").strip()
        if process.wait() != 0:
            raise ValueError(f"ffmpeg 오디오 분석 실패: {stderr or wav_path}")
    except BaseException:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise
    finally:
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
    if not frames:
        raise ValueError("비어 있는 오디오는 스펙트럼을 만들 수 없습니다")
    return {
        "schemaVersion": 1,
        "dt": dt,
        "requestedDt": requested_dt,
        "bands": bands,
        "minHz": MIN_HZ,
        "maxHz": MAX_HZ,
        "sampleRate": ANALYSIS_RATE,
        "windowSamples": WINDOW_SAMPLES,
        "hopSamples": hop_samples,
        "windowAlignment": "center",
        "durationSeconds": input_samples / ANALYSIS_RATE,
        "frames": frames,
    }

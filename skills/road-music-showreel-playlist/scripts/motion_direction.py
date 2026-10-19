#!/usr/bin/env python3
"""Validate and apply source-clock motion direction to a new rhythm-canvas project."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile


STYLES = {"orbit", "ribbons", "grid", "tiles"}
MOTIFS = {"stars", "rain", "petals", "none"}
ACCENT_KINDS = {"ring", "rays", "sweep", "punch"}
HEX = "0123456789abcdefABCDEF"
FRAME_SECONDS = 1 / 30
ASSET_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _number(value, name, low=0, high=float("inf")):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: 유한한 숫자 필요")
    value = float(value)
    if not low <= value <= high:
        raise ValueError(f"{name}: {low}..{high} 범위 필요")
    return value


def _string(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: 비어 있지 않은 문자열 필요")
    return value.strip()


def _asset_id(value, name):
    value = _string(value, name)
    if not ASSET_ID.fullmatch(value):
        raise ValueError(f"{name}: 영문·숫자·_-만 사용 가능")
    return value


def _object(value, name, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        missing = sorted(set(keys) - set(value) if isinstance(value, dict) else keys)
        unknown = sorted(set(value) - set(keys)) if isinstance(value, dict) else []
        detail = ", ".join([*(f"누락: {', '.join(missing)}" for _ in [0] if missing), *(f"지원하지 않는 키: {', '.join(unknown)}" for _ in [0] if unknown)])
        raise ValueError(f"{name}: 정확한 필드 필요" + (f" ({detail})" if detail else ""))
    return value


def _sha(value, name):
    value = _string(value, name)
    if len(value) != 64 or any(char not in HEX for char in value):
        raise ValueError(f"{name}: SHA-256 64자리 필요")
    return value.lower()


def _hex(value, name):
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#" or any(char not in HEX for char in value[1:]):
        raise ValueError(f"{name}: #RRGGBB 필요")
    return value.upper()


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: JSON 형식 오류: {error.msg}") from error


def _digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _initial_direction_script(value):
    """Allow only comments and the unconfigured direction sentinel."""
    value = re.sub(r"/\*.*?\*/|//[^\n]*", "", value, flags=re.S)
    return re.sub(r"\s+", "", value) == "window.PLAYLIST_DIRECTION=null;"


def _atomic_many(values):
    """Write all validated data to sibling temp files before exposing any output."""
    temporary = []
    try:
        for path, content in values:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix="." + path.name + ".", delete=False) as stream:
                stream.write(content)
                temp = Path(stream.name)
            os.chmod(temp, 0o600)
            temporary.append((path, temp))
        for path, temp in temporary:
            os.replace(temp, path)
    finally:
        for _, temp in temporary:
            if temp.exists():
                temp.unlink()


def _source_tracks(playlist):
    if not isinstance(playlist, dict) or not isinstance(playlist.get("tracks"), list) or not playlist["tracks"]:
        raise ValueError("playlist.tracks: 비어 있지 않은 목록 필요")
    tracks = []
    previous_end = 0.0
    for index, track in enumerate(playlist["tracks"]):
        if not isinstance(track, dict):
            raise ValueError(f"playlist.tracks[{index}]: 객체 필요")
        identifier = _string(track.get("id"), f"playlist.tracks[{index}].id")
        start = _number(track.get("startSeconds"), f"playlist.tracks[{index}].startSeconds", 0)
        end = _number(track.get("endSeconds"), f"playlist.tracks[{index}].endSeconds", 0)
        if end <= start or abs(start - previous_end) > 1e-6:
            raise ValueError("playlist.tracks: 전역 재생 구간은 간격 없이 순서대로 이어져야 합니다")
        source = track.get("source")
        if not isinstance(source, dict):
            raise ValueError(f"playlist.tracks[{index}].source: 객체 필요")
        cut_start = _number(source.get("cutStartSeconds"), f"playlist.tracks[{index}].source.cutStartSeconds", 0)
        cut_end = _number(source.get("cutEndSeconds"), f"playlist.tracks[{index}].source.cutEndSeconds", 0)
        if cut_end <= cut_start or abs((cut_end - cut_start) - (end - start)) > 1e-4:
            raise ValueError(f"playlist.tracks[{index}]: 원곡 절단 길이와 재생 길이가 일치해야 합니다")
        tracks.append({"id": identifier, "startSeconds": start, "endSeconds": end, "sourceSha256": _sha(source.get("sha256"), f"playlist.tracks[{index}].source.sha256"), "cutStartSeconds": cut_start, "cutEndSeconds": cut_end})
        previous_end = end
    duration = _number(playlist.get("durationSeconds", previous_end), "playlist.durationSeconds", 0)
    if abs(duration - previous_end) > 1e-6:
        raise ValueError("playlist.durationSeconds: 마지막 트랙 끝과 일치해야 합니다")
    return tracks, duration


def _interpolate_energy(points, time):
    if not points:
        return None
    if time <= points[0][0]:
        return points[0][1]
    if time >= points[-1][0]:
        return points[-1][1]
    for left, right in zip(points, points[1:]):
        if left[0] <= time <= right[0]:
            span = right[0] - left[0]
            return left[1] if span == 0 else left[1] + (right[1] - left[1]) * (time - left[0]) / span
    return None


def _analysis(value, duration):
    if not isinstance(value, dict):
        raise ValueError("native_analysis: 객체 필요")
    hits = value.get("hits", [])
    energy = value.get("energy", [])
    if not isinstance(hits, list) or not isinstance(energy, list):
        raise ValueError("native_analysis.hits/energy: 목록 필요")
    ordered_hits = []
    for index, hit in enumerate(hits):
        hit = _number(hit, f"native_analysis.hits[{index}]", 0, duration)
        if ordered_hits and hit <= ordered_hits[-1]:
            raise ValueError("native_analysis.hits: 오름차순 고유 시각 필요")
        ordered_hits.append(hit)
    points = []
    for index, item in enumerate(energy):
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"native_analysis.energy[{index}]: [timeSeconds, dB] 필요")
        point = (_number(item[0], f"native_analysis.energy[{index}][0]", 0, duration), _number(item[1], f"native_analysis.energy[{index}][1]", -240, 120))
        if points and point[0] <= points[-1][0]:
            raise ValueError("native_analysis.energy: 오름차순 시각 필요")
        points.append(point)
    return ordered_hits, points


def _direction_tracks(direction, source_tracks):
    _object(direction, "direction", {"schemaVersion", "type", "tracks"} | ({"media"} if isinstance(direction, dict) and "media" in direction else set()))
    if direction["schemaVersion"] != 1 or direction["type"] != "showreel-music-direction":
        raise ValueError("direction: schemaVersion=1, type=showreel-music-direction 필요")
    if not isinstance(direction["tracks"], list) or len(direction["tracks"]) != len(source_tracks):
        raise ValueError("direction.tracks: playlist와 정확히 같은 트랙 수 필요")
    by_id = {track["id"]: track for track in source_tracks}
    media = _direction_media(direction.get("media")) if "media" in direction else None
    image_ids = {image["id"] for image in media["images"]} if media else set()
    result = []
    seen = set()
    for index, item in enumerate(direction["tracks"]):
        _object(item, f"direction.tracks[{index}]", {"id", "sourceSha256", "interpretation", "sections"} | ({"accents"} if "accents" in item else set()))
        identifier = _string(item["id"], f"direction.tracks[{index}].id")
        if identifier not in by_id or identifier in seen:
            raise ValueError("direction.tracks: playlist와 정확히 같은 고유 id 필요")
        seen.add(identifier)
        track = by_id[identifier]
        if _sha(item["sourceSha256"], f"direction.tracks[{index}].sourceSha256") != track["sourceSha256"]:
            raise ValueError(f"direction.tracks[{index}]: 원곡 SHA-256 불일치")
        interpretation = _object(item["interpretation"], f"direction.tracks[{index}].interpretation", {"genre", "mood", "lyricTheme", "rationale"})
        interpretation = {key: _string(interpretation[key], f"direction.tracks[{index}].interpretation.{key}") for key in interpretation}
        if not isinstance(item["sections"], list) or not item["sections"]:
            raise ValueError(f"direction.tracks[{index}].sections: 비어 있지 않은 목록 필요")
        sections, last_end = [], None
        for section_index, section in enumerate(item["sections"]):
            optional = ({"label"} if isinstance(section, dict) and "label" in section else set()) | ({"imageId"} if isinstance(section, dict) and "imageId" in section else set()) | ({"imageOpacity"} if isinstance(section, dict) and "imageOpacity" in section else set())
            _object(section, f"direction.tracks[{index}].sections[{section_index}]", {"startSeconds", "endSeconds", "style", "palette", "intensity", "motif"} | optional)
            start = _number(section["startSeconds"], f"direction.tracks[{index}].sections[{section_index}].startSeconds", 0)
            end = _number(section["endSeconds"], f"direction.tracks[{index}].sections[{section_index}].endSeconds", 0)
            if end <= start or (last_end is not None and abs(start - last_end) > 1e-6):
                raise ValueError(f"direction.tracks[{index}].sections: 원곡 시계 구간은 겹치거나 비면 안 됩니다")
            last_end = end
            if section["style"] not in STYLES or section["motif"] not in MOTIFS:
                raise ValueError(f"direction.tracks[{index}].sections[{section_index}]: 지원하지 않는 style/motif")
            palette = _object(section["palette"], f"direction.tracks[{index}].sections[{section_index}].palette", {"background", "foreground", "accent", "secondary"})
            mapped = {"sourceStartSeconds": start, "sourceEndSeconds": end, "style": section["style"], "palette": {key: _hex(palette[key], f"palette.{key}") for key in palette}, "intensity": _number(section["intensity"], f"direction.tracks[{index}].sections[{section_index}].intensity", 0, 1), "motif": section["motif"]}
            if "label" in section:
                mapped["label"] = _string(section["label"], f"direction.tracks[{index}].sections[{section_index}].label")
            if "imageOpacity" in section and "imageId" not in section:
                raise ValueError(f"direction.tracks[{index}].sections[{section_index}].imageOpacity: imageId와 함께 필요")
            if "imageId" in section:
                image_id = _string(section["imageId"], f"direction.tracks[{index}].sections[{section_index}].imageId")
                if image_id not in image_ids:
                    raise ValueError(f"direction.tracks[{index}].sections[{section_index}].imageId: media.images에 없는 id")
                mapped["imageId"] = image_id
                mapped["imageOpacity"] = _number(section.get("imageOpacity", .8), f"direction.tracks[{index}].sections[{section_index}].imageOpacity", 0, 1)
            sections.append(mapped)
        accents = []
        if "accents" in item:
            if not isinstance(item["accents"], list):
                raise ValueError(f"direction.tracks[{index}].accents: 목록 필요")
            for accent_index, accent in enumerate(item["accents"]):
                _object(accent, f"direction.tracks[{index}].accents[{accent_index}]", {"timeSeconds", "kind", "strength"})
                if accent["kind"] not in ACCENT_KINDS:
                    raise ValueError(f"direction.tracks[{index}].accents[{accent_index}].kind: 지원하지 않는 값")
                accents.append({"timeSeconds": _number(accent["timeSeconds"], f"direction.tracks[{index}].accents[{accent_index}].timeSeconds", 0), "kind": accent["kind"], "strength": _number(accent["strength"], f"direction.tracks[{index}].accents[{accent_index}].strength", 0, 1)})
        result.append((track, interpretation, sections, accents))
    return result, media


def _direction_media(value):
    if not isinstance(value, dict) or not value or set(value) - {"thumbnail", "images"}:
        raise ValueError("direction.media: thumbnail/images만 포함한 객체 필요")
    images_value = value.get("images", [])
    if not isinstance(images_value, list):
        raise ValueError("direction.media.images: 목록 필요")
    images, seen = [], set()
    for index, image in enumerate(images_value):
        _object(image, f"direction.media.images[{index}]", {"id", "path"})
        identifier = _asset_id(image["id"], f"direction.media.images[{index}].id")
        if identifier in seen:
            raise ValueError("direction.media.images: 고유 id 필요")
        seen.add(identifier)
        images.append({"id": identifier, "path": _string(image["path"], f"direction.media.images[{index}].path")})
    result = {"images": images}
    if "thumbnail" in value:
        thumbnail = _object(value["thumbnail"], "direction.media.thumbnail", {"path", "durationSeconds"})
        duration = _number(thumbnail["durationSeconds"], "direction.media.thumbnail.durationSeconds", 0)
        if abs(duration - .5) > 1e-9:
            raise ValueError("direction.media.thumbnail.durationSeconds: 0.5초 필요")
        result["thumbnail"] = {"path": _string(thumbnail["path"], "direction.media.thumbnail.path"), "durationSeconds": duration}
        if "thumbnail" in seen:
            raise ValueError("direction.media.images: thumbnail은 썸네일 예약 id")
    return result


def compile_direction(direction, playlist, native_analysis, render_duration):
    """Map source-clock direction to the concatenated playlist clock without moving audio."""
    source_tracks, audible_duration = _source_tracks(playlist)
    render_duration = _number(render_duration, "render_duration", audible_duration)
    padding = render_duration - audible_duration
    if padding < -1e-6 or padding >= FRAME_SECONDS + 1e-9:
        raise ValueError("render_duration: 오디오 끝 이후 1프레임 미만 padding만 허용")
    direction_tracks, media = _direction_tracks(direction, source_tracks)
    if media is not None and "thumbnail" in media and source_tracks[0]["cutStartSeconds"] > 1e-6:
        media = {"images": media["images"]}
    hits, energy = _analysis(native_analysis, audible_duration)
    sections, manual, interpretations = [], [], []
    for track, interpretation, source_sections, accents in direction_tracks:
        mapped_sections = []
        for section in source_sections:
            start = max(section["sourceStartSeconds"], track["cutStartSeconds"])
            end = min(section["sourceEndSeconds"], track["cutEndSeconds"])
            if end <= start:
                continue
            mapped = {key: value for key, value in section.items() if key not in {"sourceStartSeconds", "sourceEndSeconds"}}
            mapped.update(trackId=track["id"], startSeconds=track["startSeconds"] + start - track["cutStartSeconds"], endSeconds=track["startSeconds"] + end - track["cutStartSeconds"])
            mapped_sections.append(mapped)
        if not mapped_sections or abs(mapped_sections[0]["startSeconds"] - track["startSeconds"]) > 1e-6 or abs(mapped_sections[-1]["endSeconds"] - track["endSeconds"]) > 1e-6:
            raise ValueError(f"{track['id']}: 선택한 원곡 절단 범위를 direction.sections가 모두 덮어야 합니다")
        for left, right in zip(mapped_sections, mapped_sections[1:]):
            if abs(left["endSeconds"] - right["startSeconds"]) > 1e-6:
                raise ValueError(f"{track['id']}: 선택 구간에 direction.sections 공백이 있습니다")
        sections.extend(mapped_sections)
        interpretations.append({"trackId": track["id"], **interpretation})
        for accent in accents:
            if track["cutStartSeconds"] <= accent["timeSeconds"] < track["cutEndSeconds"]:
                manual.append({"timeSeconds": track["startSeconds"] + accent["timeSeconds"] - track["cutStartSeconds"], "kind": accent["kind"], "strength": accent["strength"], "origin": "manual-choice"})
    for left, right in zip(sections, sections[1:]):
        if abs(left["endSeconds"] - right["startSeconds"]) > 1e-6:
            raise ValueError("direction.sections: 재생목록 전역 시계에 공백 또는 겹침이 있습니다")
    if not sections or abs(sections[0]["startSeconds"]) > 1e-6 or abs(sections[-1]["endSeconds"] - audible_duration) > 1e-6:
        raise ValueError("direction.sections: 전체 가청 길이를 정확히 덮어야 합니다")
    if padding > 1e-9:
        sections[-1]["endSeconds"] = render_duration

    auto, last_auto = [], None
    kinds = ("ring", "rays", "sweep", "punch")
    for hit in hits:
        if hit >= audible_duration or _interpolate_energy(energy, hit) is None or _interpolate_energy(energy, hit) < -70:
            continue
        section = next((item for item in sections if item["startSeconds"] <= hit < min(item["endSeconds"], audible_duration)), None)
        if section is None:
            continue
        spacing = 1.6 - section["intensity"]
        if last_auto is not None and hit - last_auto < spacing - 1e-9:
            continue
        auto.append({"timeSeconds": hit, "kind": kinds[len(auto) % len(kinds)], "strength": round(.35 + section["intensity"] * .65, 6), "origin": "native-hit"})
        last_auto = hit

    # A manual choice replaces a simultaneous automatic hit; nearby manual choices are
    # retained while automatic hits stay sparse.
    manual_by_time = {round(item["timeSeconds"], 6): item for item in manual}
    manual_times = sorted(manual_by_time)
    if any(right - left < .2 - 1e-9 for left, right in zip(manual_times, manual_times[1:])):
        raise ValueError("direction.accents: 수동 큰 효과는 0.2초 이상 간격이 필요합니다")
    accents = [item for item in auto if round(item["timeSeconds"], 6) not in manual_by_time]
    accents.extend(manual_by_time.values())
    accents.sort(key=lambda item: item["timeSeconds"])
    result = {"schemaVersion": 1, "durationSeconds": render_duration, "audibleDurationSeconds": audible_duration, "sections": sections, "accents": accents, "interpretations": interpretations}
    if media is not None:
        result["media"] = media
    return result


def _local_media(media, project):
    if media is None:
        return None, []
    try:
        from PIL import Image
    except ImportError as error:
        raise ValueError("이미지 미디어에는 Pillow가 필요합니다") from error

    target_root = project / "assets/motion"
    pending, local_images = [], []

    def copy_asset(identifier, source_value):
        source = Path(source_value)
        if not source.is_absolute():
            raise ValueError(f"media.{identifier}.path: 절대 로컬 경로 필요")
        source = source.resolve(strict=True)
        if not source.is_file() or source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError(f"media.{identifier}.path: PNG/JPEG/WebP 파일 필요")
        try:
            with Image.open(source) as image:
                image.verify()
            with Image.open(source) as image:
                width, height = image.size
        except (OSError, ValueError) as error:
            raise ValueError(f"media.{identifier}.path: 유효한 이미지 필요") from error
        if width < 960 or height < 540:
            raise ValueError(f"media.{identifier}.path: 최소 960x540 필요")
        target = target_root / f"{identifier}{source.suffix.lower()}"
        if target.exists():
            raise ValueError(f"media.{identifier}: 프로젝트 미디어 파일이 이미 있습니다")
        data = source.read_bytes()
        item = {"src": target.relative_to(project).as_posix(), "sha256": hashlib.sha256(data).hexdigest(), "width": width, "height": height}
        pending.append((target, data))
        return item

    for image in media["images"]:
        local_images.append({"id": image["id"], **copy_asset(image["id"], image["path"])})
    result = {"images": local_images}
    if "thumbnail" in media:
        result["thumbnail"] = {**copy_asset("thumbnail", media["thumbnail"]["path"]), "durationSeconds": media["thumbnail"]["durationSeconds"]}
    return result, pending


def apply(project_value, direction_value):
    project_input, direction_input = Path(project_value), Path(direction_value)
    if not project_input.is_absolute() or not direction_input.is_absolute():
        raise ValueError("--project와 --direction은 절대 경로여야 합니다")
    project = project_input.resolve(strict=True)
    direction_path = direction_input.resolve(strict=True)
    if not project.is_dir() or not direction_path.is_file():
        raise ValueError("프로젝트 폴더와 direction JSON 파일이 필요합니다")
    print(json.dumps({"event": "validating", "project": str(project)}, ensure_ascii=False), file=sys.stderr)
    playlist_path, production_path, preset_path = project / "playlist.json", project / "production.json", project / "preset.json"
    audio_path, analysis_path = project / "audio/music/music.wav", project / "audio/music/analysis.json"
    output_path, script_path = project / "motion-direction.json", project / "reel/direction.js"
    required = (playlist_path, production_path, preset_path, audio_path, analysis_path, script_path)
    if any(not path.is_file() for path in required):
        raise ValueError("완성되지 않은 rhythm-canvas 프로젝트입니다")
    if output_path.exists():
        raise ValueError("motion-direction.json이 이미 존재합니다. 새 프로젝트에만 적용할 수 있습니다")
    if any((project / "out").glob("*.mp4")):
        raise ValueError("이미 렌더된 프로젝트에는 적용할 수 없습니다. 새 프로젝트를 사용하세요")
    preset = _read_json(preset_path)
    if preset.get("id") != "rhythm-canvas":
        raise ValueError("rhythm-canvas 프로젝트에만 적용할 수 있습니다")
    production = _read_json(production_path)
    if "motionDirection" in production:
        raise ValueError("이미 방향 데이터가 적용된 프로젝트입니다")
    if not isinstance(production.get("audio"), dict) or production["audio"].get("sha256") != _digest(audio_path):
        raise ValueError("audio/music/music.wav 해시가 production.json과 일치하지 않습니다")
    initial = script_path.read_text(encoding="utf-8-sig")
    if not _initial_direction_script(initial):
        raise ValueError("reel/direction.js가 초기 상태가 아닙니다")
    compiled = compile_direction(_read_json(direction_path), _read_json(playlist_path), _read_json(analysis_path), production.get("renderDurationSeconds"))
    local_media, media_writes = _local_media(compiled.get("media"), project)
    if local_media is not None:
        compiled["media"] = local_media
    source_hash, analysis_hash = _digest(direction_path), _digest(analysis_path)
    rendered = _json_bytes(compiled)
    rendered_hash = hashlib.sha256(rendered).hexdigest()
    updated = dict(production)
    updated["motionDirection"] = {"source": {"path": str(direction_path), "sha256": source_hash}, "audioAnalysis": {"path": "audio/music/analysis.json", "sha256": analysis_hash}, "renderData": {"path": "motion-direction.json", "sha256": rendered_hash}}
    if local_media is not None:
        updated["motionDirection"]["media"] = local_media
    script = ("window.PLAYLIST_DIRECTION = " + json.dumps(compiled, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + ";\n").encode("utf-8")
    print(json.dumps({"event": "writing", "sections": len(compiled["sections"]), "accents": len(compiled["accents"])}, ensure_ascii=False), file=sys.stderr)
    _atomic_many((*media_writes, (output_path, rendered), (script_path, script), (production_path, _json_bytes(updated))))
    return {"project": str(project), "motionDirection": str(output_path), "sections": len(compiled["sections"]), "accents": len(compiled["accents"]), "audibleDurationSeconds": compiled["audibleDurationSeconds"], "durationSeconds": compiled["durationSeconds"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--project", required=True)
    apply_parser.add_argument("--direction", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "apply":
            result = apply(args.project, args.direction)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

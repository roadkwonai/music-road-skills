#!/usr/bin/env python3
"""Create, apply, validate, and render a native Showreel music composition."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import selectors
import subprocess
import sys
import tempfile

from PIL import Image

from cd_presets import load_captions, map_captions, prepare_playlist, probe, srt, song_inputs
from playlist_tools import normalize_display, spectrum_data


ROOT = Path(__file__).resolve().parents[1]
DESIGN_SCRIPTS = ROOT.parent / "road-music-video-studio" / "scripts"
if str(DESIGN_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DESIGN_SCRIPTS))
from html_design import apply_design
SHOWREEL = Path(os.environ.get("SHOWREEL_HOME", str(Path.home() / ".local/share/roadmusic-video-tools/showreel")))
PYTHON = os.environ.get("SHOWREEL_PYTHON", sys.executable)
FPS = 30
DISPLAY_KEYS = {"showSpectrum", "showQueue", "showNowPlaying", "channelName"}
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,62}$")
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,62}$")
SHA = re.compile(r"^[0-9a-f]{64}$")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: JSON 형식 오류: {error.msg}") from error


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix="." + path.name + ".", delete=False) as temp:
        temp.write(_json_bytes(value))
        name = temp.name
    os.replace(name, path)


def _write_text(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix="." + path.name + ".", delete=False) as temp:
        temp.write(value)
        name = temp.name
    os.replace(name, path)


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _number(value, label, low=0, high=float("inf")):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label}: 유한한 숫자 {low}..{high} 필요")
    return float(value)


def _string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: 비어 있지 않은 문자열 필요")
    return value.strip()


def _run(args):
    process = subprocess.Popen([str(item) for item in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    selector, tail = selectors.DefaultSelector(), []
    for stream in (process.stdout, process.stderr): selector.register(stream, selectors.EVENT_READ)
    while selector.get_map():
        for key, _ in selector.select():
            chunk = key.fileobj.readline()
            if not chunk:
                selector.unregister(key.fileobj); continue
            sys.stderr.write(chunk); sys.stderr.flush()
            tail.append(chunk)
            if len(tail) > 200: tail.pop(0)
    code = process.wait()
    selector.close()
    if process.stdout is not None: process.stdout.close()
    if process.stderr is not None: process.stderr.close()
    if code:
        raise ValueError("".join(tail).strip() or "실행 실패")
    return code


def _require_native_shell():
    source = ROOT / "assets/native-music"
    required = ("index.html", "film-runtime.js", "scenes.js")
    if not source.is_dir() or any(not (source / name).is_file() for name in required):
        raise ValueError(f"native-music 셸이 준비되지 않았습니다: {source}")
    return source


def _display(path):
    value = read_json(path)
    if not isinstance(value, dict) or set(value) != DISPLAY_KEYS:
        missing = sorted(DISPLAY_KEYS - set(value) if isinstance(value, dict) else DISPLAY_KEYS)
        unknown = sorted(set(value) - DISPLAY_KEYS) if isinstance(value, dict) else []
        detail = ", ".join([*(f"누락: {', '.join(missing)}" for _ in [0] if missing), *(f"지원하지 않는 키: {', '.join(unknown)}" for _ in [0] if unknown)])
        raise ValueError("display: 네 가지 표시 응답이 모두 필요" + (f" ({detail})" if detail else ""))
    return normalize_display(value)


def _copy_input(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError(f"동결 입력 파일 충돌: {target}")
    shutil.copy2(source, target)
    return target


def _playlist_inputs(music, captions, instrumental, title, start, duration, playlist):
    if playlist:
        payload = read_json(playlist)
        if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
            raise ValueError("playlist: schemaVersion=1 객체 필요")
        tracks = song_inputs(payload.get("tracks"), Path(playlist).resolve().parent, allow_multiline=True)
        return tracks, True
    if not music:
        raise ValueError("--music 또는 --playlist 필요")
    item = {"path": str(Path(music).resolve()), "instrumental": instrumental}
    if captions:
        item["captions"] = str(Path(captions).resolve())
    if title:
        item["title"] = title
    if start is not None:
        item["startSeconds"] = start
    if duration is not None:
        item["durationSeconds"] = duration
    return song_inputs([item], Path.cwd(), default_instrumental=instrumental, allow_multiline=True), False


def _build_runtime(project, duration):
    """Use upstream project/analyze/timeline/mix tools; no renderer is started here."""
    for script in ("new_project.py", "music_tools.py", "timeline.py", "mix.py"):
        if not (SHOWREEL / "scripts" / script).is_file():
            raise ValueError(f"Showreel 설치를 찾지 못함: {SHOWREEL}")
    if not (SHOWREEL / "scripts/node_modules/playwright-core").is_dir():
        raise ValueError("Showreel playwright-core 설치가 없습니다. 기존 설치를 복구한 뒤 다시 실행하세요.")
    _run([PYTHON, SHOWREEL / "scripts/new_project.py", project, "--ratio", "16:9", "--duration", duration, "--fps", FPS])
    shell = _require_native_shell()
    for name in ("index.html", "film-runtime.js", "scenes.js"):
        shutil.copy2(shell / name, Path(project) / "reel" / name)
    index = Path(project) / "reel" / "index.html"
    _write_text(index, apply_design(index.read_text(encoding="utf-8"), index, ui=False))
    audio = Path(project) / "audio/music/music.wav"
    _run([PYTHON, SHOWREEL / "scripts/music_tools.py", "analyze", audio, "--out", Path(project) / "audio/music/analysis.json"])
    script = {"duration": duration, "fps": FPS, "music": {"file": "audio/music/music.wav", "start": 0}}
    write_json(Path(project) / "script.json", script)
    _run([PYTHON, SHOWREEL / "scripts/timeline.py", Path(project) / "script.json", "--music-analysis", Path(project) / "audio/music/analysis.json"])
    _run([PYTHON, SHOWREEL / "scripts/mix.py", Path(project) / "timeline.json", "--out", Path(project) / "audio/mix.wav"])


def prepare(*, music=None, captions=None, instrumental=False, display=None, out=None, title=None, start=0, duration=None, playlist=None):
    if not display or not out:
        raise ValueError("--display와 --out 필요")
    output = Path(out).resolve()
    if output.exists():
        raise ValueError("출력 폴더가 이미 존재함. 새 경로 사용")
    chosen_display = _display(display)
    tracks, multiple = _playlist_inputs(music, captions, instrumental, title, start, duration, playlist)
    if not tracks:
        raise ValueError("한 곡 이상 필요")
    output.mkdir(parents=True)
    try:
        frozen = []
        for track in tracks:
            music_target = _copy_input(track["path"], output / "inputs/music" / (track["id"] + track["path"].suffix.lower()))
            captions_target = _copy_input(track["captions"], output / "inputs/captions" / (track["id"] + track["captions"].suffix.lower())) if track["captions"] else None
            frozen.append((track, music_target, captions_target))
        playlist_doc, cues = prepare_playlist(tracks, output, multiple, allow_multiline=True)
        for record, (track, music_target, captions_target) in zip(playlist_doc["tracks"], frozen):
            record["source"]["originalPath"] = record["source"]["path"]
            record["source"]["path"] = str(music_target.relative_to(output))
            if record.get("inputTiming"):
                record["inputTiming"]["originalPath"] = record["inputTiming"]["path"]
                record["inputTiming"]["path"] = str(captions_target.relative_to(output))
        actual = _number(playlist_doc["durationSeconds"], "실제 전체 길이", .001)
        render_duration = math.ceil(actual * FPS) / FPS
        _build_runtime(output, render_duration)
        mix = output / "audio/mix.wav"
        if not mix.is_file():
            raise ValueError("upstream mix가 audio/mix.wav를 만들지 않았습니다")
        spectrum = spectrum_data(mix) if chosen_display["showSpectrum"] else None
        if spectrum is not None:
            write_json(output / "audio/spectrum.json", spectrum)
        write_json(output / "display.json", chosen_display)
        write_json(output / "playlist.json", playlist_doc)
        (output / "captions").mkdir(exist_ok=True)
        _write_text(output / "captions/lyrics.srt", srt(cues))
        statuses = {record["captionStatus"] for record in playlist_doc["tracks"]}
        caption_status = "instrumental-no-lyrics" if all(track["instrumental"] for track in tracks) else next(iter(statuses)) if len(statuses) == 1 else "mixed"
        caption_sources = [{"trackId": track["id"], "status": track["captionDoc"].get("status"), "source": track["captionDoc"].get("source")} for track in tracks if track["captions"]]
        write_json(output / "captions/lyrics.json", {"schemaVersion": 1, "status": caption_status, "cues": cues, "sources": caption_sources})
        film_input = {"schemaVersion": 1, "duration": render_duration, "fps": FPS, "width": 1920, "height": 1080,
                      "audio": "../audio/mix.wav", "display": chosen_display, "playlist": {"tracks": playlist_doc["tracks"]},
                      "captions": {"status": caption_status, "cues": cues},
                      "spectrum": spectrum}
        _write_text(output / "reel/film-input.js", "window.FILM_INPUT = " + json.dumps(film_input, ensure_ascii=False) + ";\n")
        _write_text(output / "reel/film-plan.js", "window.FILM_PLAN = null;\n")
        write_json(output / "composition.json", {"schemaVersion": 1, "concept": None, "tracks": []})
        production = {"schemaVersion": 1, "mode": "native-composition", "durationSeconds": actual, "renderDurationSeconds": render_duration,
                      "expectedFrames": int(round(render_duration * FPS)), "audio": {"path": "audio/mix.wav", "sha256": sha256(mix)},
                      "spectrum": {"path": "audio/spectrum.json", "sha256": sha256(output / "audio/spectrum.json"), "audioSha256": sha256(mix)} if spectrum is not None else None,
                      "playlistInput": multiple, "inputs": [{"id": track["id"], "music": str(music_target.relative_to(output)), "sha256": track["sha256"],
                                  "captions": str(captions_target.relative_to(output)) if captions_target else None,
                                  "captionsSha256": sha256(captions_target) if captions_target else None} for track, music_target, captions_target in frozen]}
        write_json(output / "production.json", production)
        return {"project": str(output), "mode": production["mode"], "durationSeconds": actual, "expectedFrames": production["expectedFrames"]}
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise


def _source_tracks(project):
    playlist = read_json(project / "playlist.json")
    tracks = playlist.get("tracks") if isinstance(playlist, dict) else None
    if not isinstance(tracks, list) or not tracks:
        raise ValueError("playlist.tracks: 비어 있지 않은 목록 필요")
    return playlist, tracks


def _source_cue_ids(track, root):
    timing = track.get("inputTiming")
    if not timing:
        return set()
    source = root / timing["path"]
    return {str(cue.get("id")) for cue in load_captions(source).get("cues", [])}


def _read_global(path, name):
    source = Path(path).read_text(encoding="utf-8")
    marker = re.search(rf"^\s*window\.{re.escape(name)}\s*=\s*", source, re.MULTILINE)
    if not marker:
        raise ValueError(f"{path.name}: window.{name} JSON 필요")
    try:
        return json.loads(source[marker.end():].strip().removesuffix(";"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path.name}: window.{name} JSON 형식 오류") from error


def _image_details(path, require_alpha, label):
    try:
        with Image.open(path) as image:
            image.load()
            width, height, bands = image.width, image.height, image.getbands()
            if require_alpha:
                if "A" not in bands:
                    raise ValueError(f"{label}: alpha 채널 필요")
                lo, hi = image.getchannel("A").getextrema()
                if lo == hi:
                    raise ValueError(f"{label}: 실제 alpha 변화 필요")
            return width, height
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f"이미지를 해독할 수 없습니다: {path}") from error


def _read_media(path, project):
    if not path:
        return {}, []
    manifest_path = Path(path).resolve(strict=True)
    doc = read_json(manifest_path)
    if not isinstance(doc, dict) or doc.get("schemaVersion") != 1 or not isinstance(doc.get("assets"), list):
        raise ValueError("media: schemaVersion=1 assets 목록 필요")
    indexed, normalized = {}, []
    for index, item in enumerate(doc["assets"]):
        if not isinstance(item, dict) or set(item) - {"id", "path", "roles", "requireAlpha", "source"}:
            raise ValueError(f"media.assets[{index}]: 지원하지 않는 필드")
        asset_id = _string(item.get("id"), f"media.assets[{index}].id")
        if not ID.fullmatch(asset_id) or asset_id in indexed:
            raise ValueError("media asset id는 중복 없는 영문/숫자/_/- 필요")
        roles = item.get("roles")
        if not isinstance(roles, list) or not roles or any(not isinstance(role, str) or not role.strip() for role in roles):
            raise ValueError(f"media.assets[{index}].roles: 하나 이상의 열린 문자열 역할 필요")
        source = item.get("source")
        if not isinstance(source, dict) or source.get("kind") not in {"image_gen", "provided", "reuse"}:
            raise ValueError(f"media.assets[{index}].source.kind 필요")
        if source["kind"] == "image_gen" and (source.get("tool") != "image_gen" or not isinstance(source.get("prompt"), str) or not source["prompt"].strip()):
            raise ValueError("image_gen 자산에는 tool=image_gen과 실제 prompt 필요")
        value = _string(item.get("path"), f"media.assets[{index}].path")
        original = Path(value)
        original = original if original.is_absolute() else (manifest_path.parent / original)
        original = original.resolve(strict=True)
        if original.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError(f"지원하지 않는 이미지 형식: {original}")
        require_alpha = item.get("requireAlpha", False)
        if not isinstance(require_alpha, bool):
            raise ValueError(f"{asset_id}.requireAlpha: bool 필요")
        width, height = _image_details(original, require_alpha, asset_id)
        indexed[asset_id] = {"sourcePath": original, "roles": list(roles), "source": source, "width": width, "height": height, "sha256": sha256(original), "requireAlpha": require_alpha}
    return indexed, normalized


def _semantic_scene(scene, index):
    required = {"id", "startSeconds", "endSeconds", "lyricCueIds", "meaning", "subject", "action", "medium", "composition", "transition", "assets"}
    if not isinstance(scene, dict) or set(scene) != required:
        raise ValueError(f"scene {index + 1}: 정확한 계약 필드 필요")
    identifier = _string(scene["id"], "scene.id")
    if not ID.fullmatch(identifier):
        raise ValueError("scene.id: 영문/숫자/_/- 필요")
    start = _number(scene["startSeconds"], "scene.startSeconds", 0)
    end = _number(scene["endSeconds"], "scene.endSeconds", 0)
    if end <= start:
        raise ValueError("scene: endSeconds는 startSeconds보다 커야 함")
    for field in ("meaning", "subject", "action", "medium", "composition", "transition"):
        _string(scene[field], f"scene.{field}")
    if not isinstance(scene["lyricCueIds"], list) or len({str(value) for value in scene["lyricCueIds"]}) != len(scene["lyricCueIds"]):
        raise ValueError("scene.lyricCueIds: 중복 없는 목록 필요")
    if not isinstance(scene["assets"], list) or any(not isinstance(value, str) for value in scene["assets"]) or len(set(scene["assets"])) != len(scene["assets"]):
        raise ValueError("scene.assets: 중복 없는 asset id 목록 필요")
    return copy.deepcopy(scene)


def _coverage(scenes, start, end, label):
    cursor = start
    for scene in scenes:
        left, right = max(start, scene["startSeconds"]), min(end, scene["endSeconds"])
        if right <= left:
            continue
        if left > cursor + 1e-6:
            raise ValueError(f"{label}: 장면 gap")
        if left < cursor - 1e-6:
            raise ValueError(f"{label}: 장면 overlap")
        cursor = right
    if abs(cursor - end) > 1e-6:
        raise ValueError(f"{label}: 선택 범위를 모두 덮지 않음")


def _stored_media(root):
    path = root / "assets/media.json"
    if not path.is_file():
        return {}
    doc = read_json(path)
    assets = doc.get("assets") if isinstance(doc, dict) else None
    if not isinstance(assets, dict):
        raise ValueError("기존 assets/media.json 형식 오류")
    result = {}
    for asset_id, value in assets.items():
        if not isinstance(value, dict) or not ID.fullmatch(asset_id) or not isinstance(value.get("src"), str):
            raise ValueError("기존 media 항목 형식 오류")
        source = (root / "reel" / value["src"]).resolve()
        if not source.is_file() or root / "assets/media" not in source.parents:
            raise ValueError("기존 media 파일이 없습니다")
        require_alpha = value.get("requireAlpha", False)
        if not isinstance(require_alpha, bool) or not isinstance(value.get("width"), int) or not isinstance(value.get("height"), int) or not SHA.fullmatch(value.get("sha256", "")):
            raise ValueError("기존 media 검증 메타데이터 형식 오류")
        width, height = _image_details(source, require_alpha, asset_id)
        if (width, height) != (value["width"], value["height"]) or sha256(source) != value["sha256"]:
            raise ValueError("저장 media 파일이 준비 시 검증값과 다릅니다")
        result[asset_id] = {"sourcePath": source, "roles": value.get("roles"), "source": value.get("source"), "width": width, "height": height, "sha256": value["sha256"], "requireAlpha": require_alpha}
    return result


def _media_result(root, media_by_id):
    result = []
    for asset_id, value in media_by_id.items():
        source = value["sourcePath"]
        result.append({"id": asset_id, "src": "../assets/media/" + asset_id + source.suffix.lower(), "width": value["width"], "height": value["height"], "sha256": value["sha256"], "roles": value["roles"], "source": value["source"], "requireAlpha": value["requireAlpha"]})
    return result


def _timeline(root, resolved):
    script_path = root / "script.json"
    script = read_json(script_path)
    script["scenes"] = [{"id": scene["id"], "start": scene["startSeconds"], "end": scene["endSeconds"]} for scene in resolved]
    write_json(script_path, script)
    command = [PYTHON, SHOWREEL / "scripts/timeline.py", script_path]
    analysis = root / "audio/music/analysis.json"
    if analysis.is_file():
        command += ["--music-analysis", analysis]
    _run(command)


def _file_snapshots(paths):
    return {Path(path): Path(path).read_bytes() if Path(path).is_file() else None for path in paths}


def _restore_files(snapshots):
    for path, content in snapshots.items():
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def apply(*, project, composition, media=None):
    root = Path(project).resolve(strict=True)
    production = read_json(root / "production.json")
    if production.get("mode") != "native-composition":
        raise ValueError("native-composition 프로젝트 필요")
    plan = read_json(composition)
    if not isinstance(plan, dict) or set(plan) - {"schemaVersion", "concept", "opening", "tracks"} or plan.get("schemaVersion") != 1:
        raise ValueError("composition: schemaVersion=1 계약 필요")
    concept = _string(plan.get("concept"), "composition.concept")
    playlist, source_tracks = _source_tracks(root)
    media_requested = media is not None
    media_by_id = _read_media(media, root)[0] if media_requested else _stored_media(root)
    plan_tracks = plan.get("tracks")
    if not isinstance(plan_tracks, list) or len(plan_tracks) != len(source_tracks):
        raise ValueError("composition.tracks: 프로젝트의 모든 트랙 하나씩 필요")
    resolved, referenced = [], set()
    for source_track, track_plan in zip(source_tracks, plan_tracks):
        if not isinstance(track_plan, dict) or set(track_plan) != {"id", "sourceSha256", "scenes"} or track_plan.get("id") != source_track["id"]:
            raise ValueError("composition.tracks: id/sourceSha256/scenes 계약 필요")
        if track_plan.get("sourceSha256") != source_track["source"]["sha256"]:
            raise ValueError(f"{source_track['id']}: sourceSha256 불일치")
        scenes = track_plan.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise ValueError(f"{source_track['id']}: scenes 필요")
        scenes = [_semantic_scene(scene, index) for index, scene in enumerate(scenes)]
        if len({scene["id"] for scene in scenes}) != len(scenes):
            raise ValueError(f"{source_track['id']}: scene id 중복")
        scenes.sort(key=lambda scene: scene["startSeconds"])
        source_start, source_end = source_track["source"]["cutStartSeconds"], source_track["source"]["cutEndSeconds"]
        _coverage(scenes, source_start, source_end, source_track["id"])
        known_cues = _source_cue_ids(source_track, root)
        if source_track["instrumental"]:
            if any(scene["lyricCueIds"] for scene in scenes):
                raise ValueError(f"{source_track['id']}: 연주곡 lyricCueIds는 빈 배열 필요")
        elif any(not set(map(str, scene["lyricCueIds"])).issubset(known_cues) for scene in scenes):
            raise ValueError(f"{source_track['id']}: 알 수 없는 lyricCueIds")
        for scene in scenes:
            for asset in scene["assets"]:
                if asset not in media_by_id:
                    raise ValueError(f"scene asset 참조 없음: {asset}")
                referenced.add(asset)
            left, right = max(scene["startSeconds"], source_start), min(scene["endSeconds"], source_end)
            if right <= left:
                continue
            item = dict(scene, id=f"{source_track['id']}.{scene['id']}", trackId=source_track["id"],
                        startSeconds=round(source_track["startSeconds"] + left - source_start, 6),
                        endSeconds=round(source_track["startSeconds"] + right - source_start, 6),
                        sourceStartSeconds=round(left, 6), sourceEndSeconds=round(right, 6),
                        originStartSeconds=scene["startSeconds"], originEndSeconds=scene["endSeconds"])
            resolved.append(item)
    if not resolved:
        raise ValueError("선택한 원곡 범위와 겹치는 장면이 없습니다")
    render_duration = production["renderDurationSeconds"]
    audible_duration = playlist["durationSeconds"]
    if render_duration - audible_duration >= 1 / FPS - 1e-8:
        raise ValueError("마지막 패딩은 한 프레임 미만이어야 합니다")
    resolved[-1]["endSeconds"] = render_duration
    opening = plan.get("opening")
    if opening is not None:
        if not isinstance(opening, dict) or set(opening) != {"thumbnailId", "seconds"} or opening.get("thumbnailId") not in media_by_id:
            raise ValueError("opening: 실제 media thumbnailId와 seconds 필요")
        _number(opening["seconds"], "opening.seconds", 0, .5)
        referenced.add(opening["thumbnailId"])
    if set(media_by_id) != referenced:
        raise ValueError("media asset은 scene 또는 opening에서 한 번 이상 참조해야 합니다")
    media_result = _media_result(root, media_by_id)
    media_index = {item["id"]: {key: value for key, value in item.items() if key != "id"} for item in media_result}
    document_tracks = [{"id": track["id"], "sourceSha256": track["sourceSha256"], "scenes": [scene for scene in resolved if scene["trackId"] == track["id"]]} for track in plan_tracks]
    document = {"schemaVersion": 1, "concept": concept, "tracks": document_tracks, "scenes": resolved, "opening": opening}
    film_plan = {"schemaVersion": 1, "concept": concept, "scenes": resolved, "media": media_result, "opening": opening}
    media_root = root / "assets/media"
    (root / "assets").mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".media-", dir=root / "assets")) if media_requested else None
    try:
        if stage is not None:
            for asset_id, value in media_by_id.items():
                shutil.copy2(value["sourcePath"], stage / (asset_id + value["sourcePath"].suffix.lower()))
        paths = [root / "composition.json", root / "assets/media.json", root / "reel/film-plan.js", root / "script.json", root / "timeline.json", root / "reel/timeline.js"]
        snapshots = _file_snapshots(paths)
        backup_parent = Path(tempfile.mkdtemp(prefix=".media-before-", dir=root / "assets")) if media_requested and media_root.exists() else None
        try:
            if media_requested:
                if backup_parent is not None:
                    os.replace(media_root, backup_parent / "media")
                os.replace(stage, media_root)
                stage = None
            write_json(root / "composition.json", document)
            write_json(root / "assets/media.json", {"schemaVersion": 1, "assets": media_index})
            _write_text(root / "reel/film-plan.js", "window.FILM_PLAN = " + json.dumps(film_plan, ensure_ascii=False) + ";\n")
            _timeline(root, resolved)
        except BaseException:
            _restore_files(snapshots)
            if media_requested:
                if media_root.exists(): shutil.rmtree(media_root)
                if backup_parent is not None and (backup_parent / "media").exists(): os.replace(backup_parent / "media", media_root)
            raise
        finally:
            if backup_parent is not None:
                shutil.rmtree(backup_parent, ignore_errors=True)
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
    return {"project": str(root), "scenes": len(resolved), "media": len(media_result)}


def fingerprint(project):
    root = Path(project).resolve(strict=True)
    wanted = [root / "reel", root / "inputs", root / "composition.json", root / "playlist.json", root / "production.json", root / "script.json", root / "timeline.json", root / "display.json", root / "captions", root / "assets/media", root / "assets/media.json", root / "audio/music/music.wav", root / "audio/mix.wav", root / "audio/spectrum.json"]
    files = {}
    for candidate in wanted:
        if candidate.is_file():
            files[str(candidate.relative_to(root))] = sha256(candidate)
        elif candidate.is_dir():
            for item in sorted(candidate.rglob("*")):
                if item.is_file():
                    files[str(item.relative_to(root))] = sha256(item)
    return files


def _canonical_captions(root, playlist, multiple):
    tracks = playlist["tracks"]
    cues, sources, statuses = [], [], set()
    for track in tracks:
        timing = track.get("inputTiming")
        statuses.add(track.get("captionStatus"))
        if not timing:
            continue
        path = root / timing["path"]
        if not path.is_file() or sha256(path) != timing.get("sha256"):
            raise ValueError("동결 가사 입력이 바뀌었거나 없습니다")
        doc = load_captions(path)
        local, origin = map_captions(doc, track["source"]["cutStartSeconds"], track["durationSeconds"], timing.get("originSeconds"), allow_multiline=True)
        if origin != timing.get("originSeconds"):
            raise ValueError("동결 가사 원점이 준비 기록과 다릅니다")
        for cue in local:
            item = copy.deepcopy(cue)
            item.update(startSeconds=max(track["startSeconds"], track["startSeconds"] + cue["startSeconds"]), endSeconds=min(track["endSeconds"], track["startSeconds"] + cue["endSeconds"]))
            if "words" in item:
                item["words"] = [dict(word, startSeconds=round(max(track["startSeconds"], track["startSeconds"] + word["startSeconds"]), 6), endSeconds=round(min(track["endSeconds"], track["startSeconds"] + word["endSeconds"]), 6)) for word in item["words"]]
            if multiple:
                item.update(id=f'{track["id"]}:{cue["id"]}', sourceCueId=cue["id"], trackId=track["id"])
            cues.append(item)
        sources.append({"trackId": track["id"], "status": doc.get("status"), "source": doc.get("source")})
    status = "instrumental-no-lyrics" if all(track["instrumental"] for track in tracks) else next(iter(statuses)) if len(statuses) == 1 else "mixed"
    return {"schemaVersion": 1, "status": status, "cues": cues, "sources": sources}


def _scene_fields(scene):
    keys = ("id", "startSeconds", "endSeconds", "trackId", "sourceStartSeconds", "sourceEndSeconds", "originStartSeconds", "originEndSeconds")
    if not isinstance(scene, dict) or any(key not in scene for key in keys):
        raise ValueError("resolved scene 필수 binding 필드가 없습니다")
    return {key: scene[key] for key in keys}


def _scene_binding(root):
    composition = read_json(root / "composition.json")
    scenes = composition.get("scenes") if isinstance(composition, dict) else None
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("빈 author scenes 프로젝트는 검수할 수 없습니다")
    expected = [_scene_fields(scene) for scene in scenes]
    plan = _read_global(root / "reel/film-plan.js", "FILM_PLAN")
    if not isinstance(plan, dict) or plan.get("scenes") != scenes:
        raise ValueError("composition과 FILM_PLAN 장면 binding이 다릅니다")
    if plan.get("concept") != composition.get("concept") or plan.get("opening") != composition.get("opening"):
        raise ValueError("FILM_PLAN 콘셉트/오프닝이 composition과 다릅니다")
    if plan.get("media") != _media_result(root, _stored_media(root)):
        raise ValueError("FILM_PLAN media가 검증된 저장 이미지와 다릅니다")
    timeline = read_json(root / "timeline.json")
    actual = timeline.get("scenes") if isinstance(timeline, dict) else None
    expected_timeline = [{"id": scene["id"], "start": round(scene["startSeconds"], 3), "end": round(scene["endSeconds"], 3)} for scene in expected]
    if actual != expected_timeline:
        raise ValueError("timeline 장면 시각이 composition과 다릅니다")
    return expected


def _prepared_contract(root, production):
    audio = production.get("audio")
    if not isinstance(audio, dict) or audio.get("path") != "audio/mix.wav" or not SHA.fullmatch(audio.get("sha256", "")) or not (root / audio["path"]).is_file() or sha256(root / audio["path"]) != audio["sha256"]:
        raise ValueError("준비 mix.wav가 production.audio와 다릅니다")
    playlist, tracks = _source_tracks(root)
    inputs = production.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != len(tracks):
        raise ValueError("production.inputs가 playlist와 다릅니다")
    for item, track in zip(inputs, tracks):
        if not isinstance(item, dict) or item.get("id") != track["id"] or item.get("music") != track["source"].get("path") or item.get("sha256") != track["source"].get("sha256"):
            raise ValueError("production 원곡 입력이 playlist와 다릅니다")
        music = root / item["music"]
        if not music.is_file() or sha256(music) != item["sha256"]:
            raise ValueError("동결 원곡 입력이 바뀌었거나 없습니다")
        pcm = track.get("audio")
        pcm_path = root / pcm.get("path", "") if isinstance(pcm, dict) else None
        if not pcm_path or not pcm_path.is_file() or not SHA.fullmatch(pcm.get("sha256", "")) or sha256(pcm_path) != pcm["sha256"]:
            raise ValueError("각 트랙 PCM 오디오가 준비 기록과 다릅니다")
        timing = track.get("inputTiming")
        if timing:
            if item.get("captions") != timing.get("path") or item.get("captionsSha256", timing.get("sha256")) != timing.get("sha256"):
                raise ValueError("production 동결 가사 입력이 playlist와 다릅니다")
        elif item.get("captions") is not None:
            raise ValueError("무가사 production 입력에 가사가 있습니다")
    canonical = _canonical_captions(root, playlist, bool(production.get("playlistInput")) or any(str(track.get("audio", {}).get("path", "")).startswith("audio/tracks/") for track in tracks))
    saved = read_json(root / "captions/lyrics.json")
    if saved != canonical or (root / "captions/lyrics.srt").read_text(encoding="utf-8") != srt(canonical["cues"]):
        raise ValueError("저장 captions JSON/SRT가 동결 가사와 다릅니다")
    film_input = _read_global(root / "reel/film-input.js", "FILM_INPUT")
    if film_input.get("captions") != {"status": canonical["status"], "cues": canonical["cues"]}:
        raise ValueError("FILM_INPUT captions가 동결 가사와 다릅니다")
    display = read_json(root / "display.json")
    if film_input.get("playlist") != {"tracks": tracks} or film_input.get("display") != display:
        raise ValueError("FILM_INPUT playlist/display가 저장 선택과 다릅니다")
    if any(film_input.get(key) != value for key, value in {"audio": "../audio/mix.wav", "duration": production.get("renderDurationSeconds"), "fps": FPS, "width": 1920, "height": 1080}.items()):
        raise ValueError("FILM_INPUT 오디오/길이/규격이 준비 기록과 다릅니다")
    expected_spectrum = None
    if display.get("showSpectrum"):
        signal = production.get("spectrum")
        if not isinstance(signal, dict) or signal.get("path") != "audio/spectrum.json" or signal.get("audioSha256") != audio["sha256"] or not (root / signal["path"]).is_file() or sha256(root / signal["path"]) != signal.get("sha256"):
            raise ValueError("실제 FFT가 준비 mix와 연결되지 않았습니다")
        expected_spectrum = read_json(root / signal["path"])
    if film_input.get("spectrum") != expected_spectrum:
        raise ValueError("FILM_INPUT FFT가 검증된 분석과 다릅니다")


def check(*, project):
    root = Path(project).resolve(strict=True)
    production = read_json(root / "production.json")
    if production.get("mode") != "native-composition":
        raise ValueError("native-composition 프로젝트 필요")
    if not (root / "reel/film-input.js").is_file() or not (root / "reel/film-plan.js").is_file():
        raise ValueError("native film 입력 파일이 없습니다")
    _prepared_contract(root, production)
    scenes = _scene_binding(root)
    return {"project": str(root), "prepared": bool(scenes), "files": fingerprint(root), "scenes": scenes}


def _same_files(value, current, label):
    if not isinstance(value, dict) or value != current:
        raise ValueError(f"{label} fingerprint가 현재 입력과 일치하지 않습니다")


def _creative_review(root, files, scene_ids):
    review = read_json(root / "qa/creative-review.json")
    if review.get("schemaVersion") != 1:
        raise ValueError("creative-review.schemaVersion=1 필요")
    _same_files(review.get("files"), files, "creative-review")
    scenes = review.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != len(scene_ids) or any(not isinstance(item, dict) for item in scenes) or {item.get("id") for item in scenes} != set(scene_ids):
        raise ValueError("creative-review는 모든 현재 scene의 판정 필요")
    for item in scenes:
        if item.get("decision") != "keep" or not isinstance(item.get("note"), str) or not item["note"].strip() or not isinstance(item.get("evidence"), list) or not item["evidence"]:
            raise ValueError("final은 모든 scene의 keep/note/실제 evidence 필요")
        for relative in item["evidence"]:
            if not isinstance(relative, str) or Path(relative).is_absolute() or not (root / relative).is_file():
                raise ValueError("creative-review evidence 파일이 없습니다")


def _motion_issues(motion):
    issues = motion.get("issues") if isinstance(motion, dict) else None
    if not isinstance(issues, list):
        raise ValueError("motion JSON issues 목록 필요")
    result = []
    for issue in issues:
        if isinstance(issue, str) and issue.strip():
            result.append(issue)
        elif isinstance(issue, dict):
            result.append(json.dumps(issue, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        else:
            raise ValueError("motion issue 형식 오류")
    return result


def _motion_status(motion):
    issues = _motion_issues(motion)
    def soft(issue):
        value = issue.removeprefix('- [ ] ').strip()
        return value.startswith(('멈춘 화면 ', '큰 움직임 p90 ', '그 밖에 1초 넘는 멈춤 ', 'still_ratio=', 'p90=', 'long_still=')) or bool(re.match(r'^\d+(?:\.\d+)?~\d+(?:\.\d+)?s 동안 .+멈춤', value))
    if any("flash" in issue.lower() or "섬광" in issue or not soft(issue) for issue in issues):
        return "failed", issues
    return ("needs-review" if issues else "passed"), issues


def _native_qa_passes(report, motion):
    status, motion_issues = _motion_status(motion)
    if status == "failed":
        return False
    if "## 고칠 것" not in report:
        return "## 자동 검사 통과" in report
    issues = report.split("## 고칠 것", 1)[1].split("## 사람이 볼 것", 1)[0]
    pending = [re.sub(r' \[장면 [A-Za-z0-9_.:-]+\]$', '', line.removeprefix('- [ ] ').strip()) for line in issues.splitlines() if line.startswith("- [ ]")]
    return not pending or all(line in motion_issues and _motion_status({"issues": [line]})[0] == "needs-review" for line in pending)


def _motion_review(root, issues, motion_path):
    review = read_json(root / "qa/creative-review.json")
    value = review.get("motionReview")
    if not isinstance(value, dict) or value.get("issues") != issues or not isinstance(value.get("reason"), str) or not value["reason"].strip() or value.get("motionReportSha256") != sha256(motion_path):
        raise ValueError("저운동 final은 현재 motion issues/reason/report SHA가 든 creative-review 필요")
    evidence = value.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(not isinstance(item, str) or Path(item).is_absolute() or not (root / item).is_file() for item in evidence):
        raise ValueError("저운동 final motionReview 실제 evidence 필요")


def _current_runtime(root, files, scenes):
    runtime = read_json(root / 'qa/native-runtime.json')
    _same_files(runtime.get('files'), files, 'native runtime')
    actual = runtime.get('registeredScenes')
    if runtime.get('pass') is not True or runtime.get('sceneBindings') != scenes or not isinstance(actual, list) or len(actual) != len(scenes):
        raise ValueError('native runtime 장면 binding이 현재 composition과 다릅니다')
    indexed = {item.get('id'): item for item in actual if isinstance(item, dict)}
    if len(indexed) != len(scenes):
        raise ValueError('native runtime 장면 id가 중복되거나 없습니다')
    for scene in scenes:
        registered = indexed.get(scene['id'], {})
        for field in ('startSeconds', 'endSeconds'):
            value = _number(registered.get(field), 'native runtime ' + field, -.5 / FPS)
            if abs(value - scene[field]) > .5 / FPS + 1e-7:
                raise ValueError('native runtime 장면 시각이 계획에서 벗어났습니다')


def finalize(*, project, name):
    root = Path(project).resolve(strict=True)
    if not NAME.fullmatch(name):
        raise ValueError("--name: ASCII ID 필요")
    prepared = check(project=str(root)); files = fingerprint(root)
    _current_runtime(root, files, prepared['scenes'])
    _creative_review(root, files, [scene["id"] for scene in prepared["scenes"]])
    video = root / "out" / (name + ".mp4")
    motion = root / "qa" / (name + "-motion.json")
    receipt = read_json(root / 'qa' / (name + '-render.json'))
    if receipt.get('schemaVersion') != 1 or receipt.get('name') != name or receipt.get('draft') is not False:
        raise ValueError('검증된 final 렌더 기록이 없습니다')
    _same_files(receipt.get('files'), files, 'render receipt')
    required_outputs = {'out/' + name + suffix for suffix in ('.mp4', '_공유용.mp4', '_포스터.jpg', '.srt')}
    required_reports = {'qa/' + name + suffix for suffix in ('-motion.json', '-qa-report.md')}
    if set(receipt.get('outputs', {})) != required_outputs or set(receipt.get('qaReports', {})) != required_reports:
        raise ValueError('final 출력/검수 기록이 불완전합니다')
    for relative, expected in {**receipt['outputs'], **receipt['qaReports']}.items():
        file = root / relative
        if not file.is_file() or sha256(file) != expected:
            raise ValueError('렌더 후 출력 또는 검수 기록이 변경됐습니다: ' + relative)
    status, warnings = _motion_status(read_json(motion))
    if not _native_qa_passes((root / 'qa' / (name + '-qa-report.md')).read_text(), read_json(motion)):
        raise ValueError("final motion에 허용 불가 문제가 있습니다")
    if status == "needs-review":
        _motion_review(root, warnings, motion)
        review = read_json(root / "qa/creative-review.json")
        if review.get("motionReview", {}).get("finalOutputSha256") != sha256(video):
            raise ValueError("motionReview finalOutputSha256가 현재 기존 출력과 다릅니다")
    return {"video": str(video), "warnings": warnings, "motionReviewed": status == 'needs-review', "checks": receipt['checks'], "status": "finalized"}


def _video_checks(video, expected_frames):
    media = probe(video)
    streams = media.get("streams", [])
    visual = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not visual or not audio:
        raise ValueError("완성본에 영상과 오디오 스트림이 모두 필요")
    count = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", str(video)], capture_output=True, text=True, check=True).stdout.strip()
    checks = {"dimensions": [visual.get("width"), visual.get("height")], "fps": visual.get("r_frame_rate"), "frames": int(count), "pixelFormat": visual.get("pix_fmt"), "range": visual.get("color_range"), "audioRate": audio.get("sample_rate"), "audioChannels": audio.get("channels")}
    if checks != {"dimensions": [1920, 1080], "fps": "30/1", "frames": expected_frames, "pixelFormat": "yuv420p", "range": "tv", "audioRate": "48000", "audioChannels": 2}:
        raise ValueError(f"렌더 규격 불일치: {checks}")
    _run(["ffmpeg", "-xerror", "-v", "error", "-i", video, "-f", "null", "-"])
    return checks


def render(*, project, draft=False, name=None):
    root = Path(project).resolve(strict=True)
    prepared = check(project=str(root))
    scenes = prepared["scenes"]
    files = fingerprint(root)
    _current_runtime(root, files, scenes)
    if not draft:
        _creative_review(root, files, [scene["id"] for scene in scenes])
    rendered_name = name or ("preview" if draft else "native-video")
    if not NAME.fullmatch(rendered_name):
        raise ValueError("--name: ASCII ID 필요")
    out = root / "out"
    picture, video = out / (rendered_name + "-picture.mp4"), out / (rendered_name + ".mp4")
    shared = out / (rendered_name + "_공유용.mp4")
    if any(path.exists() for path in (picture, video, shared, out / (rendered_name + "_포스터.jpg"), out / (rendered_name + ".srt"))):
        raise ValueError("기존 완성 출력은 덮어쓸 수 없습니다")
    production = read_json(root / "production.json")
    _run(["node", SHOWREEL / "scripts/render.mjs", "--dir", root / "reel", "--out", picture, "--scale", 1, "--sub", 1 if draft else 4, "--format", "png", "--keep"])
    finish = [PYTHON, SHOWREEL / "scripts/finish.py", "--video", picture, "--audio", root / "audio/mix.wav", "--name", rendered_name, "--outdir", out, "--poster", min(max(0, production["durationSeconds"] - .5), 16.2)]
    if draft: finish.append("--no-web")
    _run(finish)
    shutil.copy2(root / "captions/lyrics.srt", out / (rendered_name + ".srt"))
    checks = _video_checks(video, production["expectedFrames"])
    if not draft and not shared.is_file():
        raise ValueError("최종 공유용 MP4가 없습니다")
    motion = root / "qa" / (rendered_name + "-motion.json")
    _run([PYTHON, SHOWREEL / "scripts/motion_check.py", video, "--timeline", root / "timeline.json", "--json", motion])
    _run([PYTHON, SHOWREEL / "scripts/qa_check.py", video, "--timeline", root / "timeline.json", "--qa", root / "qa"])
    motion_doc = read_json(motion)
    report = (root / "qa/qa_report.md").read_text(encoding="utf-8")
    status, warnings = _motion_status(motion_doc)
    if not _native_qa_passes(report, motion_doc):
        raise ValueError("native QA가 실제 문제를 보고했습니다")
    saved_report = root / 'qa' / (rendered_name + '-qa-report.md')
    _write_text(saved_report, report)
    outputs = [video, out / (rendered_name + '_포스터.jpg'), out / (rendered_name + '.srt')]
    if not draft: outputs.append(shared)
    write_json(root / 'qa' / (rendered_name + '-render.json'), {'schemaVersion': 1, 'name': rendered_name, 'draft': draft, 'files': files, 'outputs': {str(p.relative_to(root)): sha256(p) for p in outputs}, 'qaReports': {str(p.relative_to(root)): sha256(p) for p in (motion, saved_report)}, 'checks': checks})
    return {"video": str(video), "shared": str(shared) if not draft else None, "poster": str(out / (rendered_name + "_포스터.jpg")), "srt": str(out / (rendered_name + ".srt")), "checks": checks, "warnings": warnings, "motionReviewRequired": status == "needs-review", "status": "rendered-needs-review" if status == "needs-review" else "rendered-needs-final-visual-review"}


def _result(fn, **kwargs):
    try:
        print(json.dumps(fn(**kwargs), ensure_ascii=False, allow_nan=False))
    except (ValueError, FileNotFoundError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--music"); prep.add_argument("--captions"); prep.add_argument("--instrumental", action="store_true")
    prep.add_argument("--playlist"); prep.add_argument("--display", required=True); prep.add_argument("--out", required=True); prep.add_argument("--title")
    prep.add_argument("--start", type=float, default=0); prep.add_argument("--duration", type=float)
    app = sub.add_parser("apply"); app.add_argument("--project", required=True); app.add_argument("--composition", required=True); app.add_argument("--media")
    chk = sub.add_parser("check"); chk.add_argument("--project", required=True)
    fp = sub.add_parser("fingerprint"); fp.add_argument("--project", required=True)
    rnd = sub.add_parser("render"); rnd.add_argument("--project", required=True); rnd.add_argument("--draft", action="store_true"); rnd.add_argument("--name")
    fin = sub.add_parser("finalize"); fin.add_argument("--project", required=True); fin.add_argument("--name", required=True)
    args = parser.parse_args()
    values = vars(args).copy()
    command = values.pop("command")
    if command == "prepare": _result(prepare, **values)
    elif command == "apply": _result(apply, **values)
    elif command == "check": _result(check, **values)
    elif command == "fingerprint": _result(lambda project: {"files": fingerprint(project)}, project=values["project"])
    elif command == "render": _result(render, **values)
    else: _result(finalize, **values)


if __name__ == "__main__":
    main()

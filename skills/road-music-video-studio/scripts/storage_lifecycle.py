"""제작 producer가 명시 소유 캐시만 StorageManager에 등록하는 작은 연결점."""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

from management_db import ManagementDBError
from storage_manager import StorageError, StorageManager, _atomic_json, _snapshot


OWNED_RENDER_STEMS = ("audio/mix_bed.wav", "audio/mix_premaster.wav", "audio/mix_vo.wav")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _trusted_workspace():
    """Return this source kit only when its Output directory is a real workspace root."""
    from storage_packaging import TRUSTED_ROOT
    root = TRUSTED_ROOT
    if root is None:
        return None
    output = root / "Output"
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        return None
    return root if (root / "cli/road-music.js").is_file() else None


def _final_only_workspace(workspace):
    marker = workspace / ".roadmusic" / "structure.json"
    if not marker.is_file() or marker.is_symlink() or marker.stat().st_size > 64 * 1024:
        return False
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and value.get("schemaVersion") == 1 and value.get("phase") == "completed" and value.get("owner") == "road-music" and value.get("workspace") in {str(workspace), str(workspace.resolve())}


def working_project_path(requested, source_sha256=None):
    """Keep new producer work out of Output while leaving legacy and external paths intact."""
    path = Path(requested).expanduser().resolve(strict=False)
    workspace = _trusted_workspace()
    if workspace is None:
        return path
    output = (workspace / "Output").resolve(strict=False)
    if not _inside(output, path):
        return path
    if path.exists() and not _final_only_workspace(workspace):
        return path
    relative = path.relative_to(output)
    if not relative.parts:
        raise ValueError("Output 자체는 제작 폴더로 사용할 수 없습니다")
    source = source_sha256.lower() if isinstance(source_sha256, str) else ""
    music_id = source[:12] if _SHA256.fullmatch(source) else "unassigned"
    label = re.sub(r"[^\w.-]+", "-", relative.name, flags=re.UNICODE).strip(".-_") or "project"
    project_id = hashlib.sha256(str(relative).encode("utf-8")).hexdigest()[:12]
    target = workspace / ".roadmusic/work" / music_id / f"{label[:48]}--{project_id}"
    shared_storage_manager().management_db.claim_path(
        str(target), "producer-work", project_id=hashlib.sha256(str(target).encode("utf-8")).hexdigest(),
        group_id=source if _SHA256.fullmatch(source) else None, workspace=str(workspace),
    )
    return target


@lru_cache(maxsize=8)
def _profile_storage_manager(data_dir):
    return StorageManager(data_dir)


def shared_storage_manager():
    from html_design import studio_session_file
    return _profile_storage_manager(str(studio_session_file().parent.resolve()))


shared_storage_manager.cache_clear = _profile_storage_manager.cache_clear


def _project(project):
    return Path(project).resolve(strict=True)


def _sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _production_group_id(root):
    """Return a group only when the local producer metadata names one source."""
    candidates = set()
    for name in ("studio-project.json", "production.json", "native-production.json"):
        path = root / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        source = value.get("source") if isinstance(value, dict) else None
        if isinstance(source, dict) and isinstance(source.get("sha256"), str) and _SHA256.fullmatch(source["sha256"].lower()):
            candidates.add(source["sha256"].lower())
        for item in value.get("media", []) if isinstance(value, dict) and isinstance(value.get("media"), list) else []:
            if isinstance(item, dict) and item.get("id") == "music" and isinstance(item.get("sha256"), str) and _SHA256.fullmatch(item["sha256"].lower()):
                candidates.add(item["sha256"].lower())
    return next(iter(candidates)) if len(candidates) == 1 else None


def _event_value(value):
    """Keep production events metadata-sized; media and frame dumps stay on disk."""
    if value is None:
        return None
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) <= 96 * 1024:
        return value
    return {"summary": "large production metadata omitted", "bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}


def record_production_change(project, action, before=None, after=None, reason=""):
    """Append a compact, source-linked production event to the profile SQLite ledger."""
    if before == after:
        return None
    root = _project(project)
    if not isinstance(action, str) or not action or len(action) > 80:
        raise ValueError("제작 이력 action이 올바르지 않습니다")
    if not isinstance(reason, str) or len(reason) > 1000:
        raise ValueError("제작 이력 reason이 올바르지 않습니다")
    try:
        manager = shared_storage_manager()
        project_id = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
        after = _event_value(after)
        if before is None:
            with manager.management_db.transaction() as connection:
                previous = connection.execute("SELECT after_json FROM management_events WHERE project_id=? AND action=? ORDER BY id DESC LIMIT 1", (project_id, action)).fetchone() if manager.management_db._has_table(connection, 'management_events') else None
            if previous:
                before = json.loads(previous[0]) if previous[0] is not None else None
            if before == after:
                return None
        return manager.management_db.record_event(
            action,
            project_id=project_id,
            group_id=_production_group_id(root),
            before=_event_value(before),
            after=after,
            reason=reason,
            path=str(root),
        )
    except ManagementDBError as error:
        raise StorageError(str(error), "history_unavailable") from error


def abandon_failed_project(project):
    """Drop a failed new producer's registry only after its private files are gone."""
    root = Path(project).resolve(strict=False)
    if root.exists() or Path(project).is_symlink():
        return False
    manager = shared_storage_manager()
    project_id = manager._project_id(root)
    with manager._write_lock():
        registry = manager._read()
        entry = registry['projects'].get(project_id)
        claims = manager.management_db.paths(project_id=project_id)
        if not entry and not claims:
            return False
        if entry and (entry.get('path') != str(root) or manager._busy(registry, project_id)):
            raise StorageError('실패한 작업의 소유권·활성 상태가 달라 등록을 보존합니다.', 'busy')
        registry['projects'].pop(project_id, None)
        registry['leases'].pop(project_id, None)
        with manager.management_db.transaction(write=True) as connection:
            manager._save(registry, connection=connection)
            manager.management_db.drop_project(project_id, connection=connection, preserve_production=True)
            manager.management_db.record_event('production-failed', path=str(root), after={'removedNewWork': True}, connection=connection)
    return True


def _probe_media(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def _duration(media):
    try:
        value = float(media.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _delivery_media(path, kind, expected_hash):
    path = Path(path).resolve(strict=True)
    if path.is_symlink() or not path.is_file() or _sha256(path) != expected_hash:
        raise ValueError("완성 파일 해시가 등록 정보와 다릅니다")
    media = _probe_media(path)
    streams = media.get("streams", [])
    types = {item.get("codec_type") for item in streams if isinstance(item, dict)}
    if kind == "video" and not {"video", "audio"} <= types:
        raise ValueError("최종 영상에 영상과 오디오 스트림이 모두 필요합니다")
    if kind == "music" and "audio" not in types:
        raise ValueError("최종 음원에 오디오 스트림이 필요합니다")
    seconds = _duration(media)
    if seconds is None:
        raise ValueError("최종 파일의 길이를 확인할 수 없습니다")
    return {"path": str(path), "sha256": expected_hash, "kind": kind, "durationSeconds": seconds}


def _production_duration(root):
    path = root / "production.json"
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError("제작 길이 기록을 안전하게 읽을 수 없습니다")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("제작 길이 기록을 읽을 수 없습니다") from error
    if not isinstance(value, dict):
        raise ValueError("제작 길이 기록 형식이 올바르지 않습니다")
    for key in ("renderDurationSeconds", "durationSeconds"):
        seconds = value.get(key)
        if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and math.isfinite(seconds) and seconds > 0:
            return float(seconds)
    return None


def _verify_delivery_durations(root, source_seconds, outputs):
    expected = _production_duration(root)
    if expected is None and any(item["kind"] == "video" for item in outputs):
        raise ValueError("최종 영상 길이를 확인할 제작 기록이 없습니다")
    for item in outputs:
        target = expected if expected is not None else source_seconds
        if abs(item["durationSeconds"] - target) > 1:
            raise ValueError("최종 %s 길이가 제작 기록과 다릅니다" % ("영상" if item["kind"] == "video" else "음원"))


def _inside(root, path):
    return path == root or root in path.parents


def _owned_history_path(root):
    path = root / ".roadmusic/history/owned-render-cache.json"
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root.parent):
        raise StorageError("파생 캐시 이력 경로가 안전하지 않습니다.", "unsafe_path")
    return path


def _production_fingerprint(root):
    path = root / "production.json"
    if path.is_symlink() or not path.is_file():
        raise StorageError("production.json이 필요합니다.", "missing_proof")
    return _sha256(path)


def _owned_path(root, relative):
    if relative not in OWNED_RENDER_STEMS:
        raise StorageError("허용된 파생 WAV만 기록할 수 있습니다.", "unsafe_path")
    path = root / relative
    parent = path.parent
    while parent != root.parent:
        if parent.is_symlink():
            raise StorageError("파생 WAV 상위 경로가 안전하지 않습니다.", "unsafe_path")
        parent = parent.parent
    if path.is_symlink() or not path.is_file():
        raise StorageError("파생 WAV 경로가 안전하지 않습니다.", "unsafe_path")
    resolved = path.resolve(strict=True)
    if not _inside(root, resolved) or resolved != path:
        raise StorageError("파생 WAV 경로가 안전하지 않습니다.", "unsafe_path")
    return path


def _record_generated_cache(root, generated_cache):
    if not isinstance(generated_cache, (list, tuple)) or len(set(generated_cache)) != len(generated_cache):
        raise StorageError("명시 생성한 파생 WAV 경로가 필요합니다.", "unsafe_path")
    if any(item not in OWNED_RENDER_STEMS for item in generated_cache):
        raise StorageError("허용된 파생 WAV만 기록할 수 있습니다.", "unsafe_path")
    files = []
    for relative in generated_cache:
        path = root / relative
        if not path.exists() and not path.is_symlink():
            continue
        path = _owned_path(root, relative)
        snapshot = _snapshot(path)
        if snapshot["nlink"] != 1:
            raise StorageError("hardlink 파생 WAV는 자동 정리하지 않습니다.", "shared_hardlink")
        files.append({"relativePath": relative, "sha256": _sha256(path), "snapshot": snapshot})
    history = _owned_history_path(root)
    _atomic_json(history, {"schemaVersion": 1, "productionSha256": _production_fingerprint(root), "files": files})
    return history


def _is_open(path):
    try:
        result = subprocess.run(["lsof", "-F", "n", str(path)], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return True
    return any(line.startswith("n") for line in result.stdout.splitlines())


def _owned_cleanup(manager, root, project_id, listed, media, source_path, production_sha):
    history = _owned_history_path(root)
    if not history.is_file() or history.is_symlink():
        return {"removedFiles": 0, "freedBytes": 0, "skipped": []}
    try:
        value = json.loads(history.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return {"removedFiles": 0, "freedBytes": 0, "skipped": [{"reason": f"파생 캐시 이력을 확인할 수 없습니다: {error}"}]}
    if not isinstance(value, dict) or value.get("schemaVersion") != 1 or value.get("productionSha256") != production_sha or not isinstance(value.get("files"), list):
        return {"removedFiles": 0, "freedBytes": 0, "skipped": [{"reason": "파생 캐시 이력이 현재 제작 기록과 다릅니다"}]}
    if listed["busy"] or not listed["autoCleanup"] or any(entry.get("pinned") for entry in listed["entries"]):
        return {"removedFiles": 0, "freedBytes": 0, "skipped": [{"reason": "진행 중·자동 정리 해제·보존 핀 상태입니다"}]}
    protected = {source_path.resolve(strict=True)}
    for item in media:
        try:
            path = Path(item["path"]).resolve(strict=True)
            if path.is_file() and not path.is_symlink():
                protected.add(path)
        except (KeyError, OSError):
            continue
    try:
        production = json.loads((root / "production.json").read_text(encoding="utf-8"))
        primary = production.get("audio", {}).get("path") if isinstance(production, dict) else None
        if isinstance(primary, str):
            path = (root / primary).resolve(strict=True)
            if _inside(root, path): protected.add(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"removedFiles": 0, "freedBytes": 0, "skipped": [{"reason": "현재 production.json을 확인할 수 없습니다"}]}
    protected_inodes = set()
    for path in protected:
        try:
            stat = path.stat(follow_symlinks=False); protected_inodes.add((stat.st_dev, stat.st_ino))
        except OSError:
            continue
    removed = freed = 0; skipped = []
    for item in value["files"]:
        relative = item.get("relativePath") if isinstance(item, dict) else None
        snapshot = item.get("snapshot") if isinstance(item, dict) else None
        if relative not in OWNED_RENDER_STEMS or not isinstance(snapshot, dict) or item.get("sha256") is None:
            skipped.append({"relativePath": relative, "reason": "파생 캐시 이력 형식이 올바르지 않습니다"}); continue
        path = root / relative
        try:
            path = _owned_path(root, relative)
            current = _snapshot(path)
            if current != snapshot or current["nlink"] != 1 or _sha256(path) != item["sha256"]:
                raise StorageError("파생 WAV가 생성 뒤 변경됐습니다")
            if (current["dev"], current["inode"]) in protected_inodes:
                raise StorageError("원음·최종본·주 믹스와 같은 파일은 보존합니다")
            if _is_open(path):
                raise StorageError("열려 있는 파생 WAV는 보존합니다")
            manager._unlink_verified(root, relative, (current["dev"], current["inode"], current["bytes"], current["mtimeNs"]))
            removed += 1; freed += current["bytes"]
        except (OSError, StorageError) as error:
            skipped.append({"relativePath": relative, "reason": str(error)})
    _atomic_json(root / ".roadmusic/history/owned-render-cache-cleanup.json", {"schemaVersion": 1, "productionSha256": production_sha, "removedFiles": removed, "freedBytes": freed, "skipped": skipped})
    return {"removedFiles": removed, "freedBytes": freed, "skipped": skipped}


def complete_published_project(manager, project, media, source_sha256):
    """Verify a published delivery before enabling immediate producer-cache cleanup."""
    root = _project(project)
    if not isinstance(source_sha256, str):
        return {"completed": False, "reason": "원음 SHA-256이 지정되지 않았습니다"}
    source_sha256 = source_sha256.lower()
    listed = manager.dispatch("list", {"projectId": manager.dispatch("register", {"project": str(root)})["id"]})["projects"][0]
    if listed["busy"]:
        return {"completed": False, "reason": "진행 중인 제작 lease가 있습니다"}
    if not listed["autoCleanup"]:
        return {"completed": False, "reason": "자동 정리가 꺼진 프로젝트입니다"}
    if listed["state"] == "archived":
        return {"completed": False, "reason": "보관 프로젝트입니다"}
    source = next((item for item in media if item.get("id") == "music" and item.get("kind") == "music"), None)
    if not isinstance(source, dict) or source.get("sha256") != source_sha256:
        return {"completed": False, "reason": "현재 원음 SHA-256과 납품 연결이 일치하지 않습니다"}
    try:
        source_path = Path(source["path"]).resolve(strict=True)
        if source_path.is_symlink() or not source_path.is_file() or _sha256(source_path) != source_sha256:
            return {"completed": False, "reason": "현재 원음이 변경됐거나 확인할 수 없습니다"}
        source_media = _probe_media(source_path)
        if "audio" not in {item.get("codec_type") for item in source_media.get("streams", []) if isinstance(item, dict)} or _duration(source_media) is None:
            return {"completed": False, "reason": "현재 원음의 오디오·길이를 확인할 수 없습니다"}
        outputs = [_delivery_media(item["path"], item["kind"], item["sha256"])
                   for item in media if item.get("id") != "music" and item.get("kind") in {"video", "music"}]
        _verify_delivery_durations(root, _duration(source_media), outputs)
    except (KeyError, OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        return {"completed": False, "reason": f"완성본 검증 보류: {error}"}
    if not outputs:
        return {"completed": False, "reason": "검증된 최종 음원 또는 영상이 없습니다"}
    receipt = {
        "schemaVersion": 1,
        "source": {"path": str(source_path), "sha256": source_sha256, "durationSeconds": _duration(source_media)},
        "outputs": outputs,
    }
    history = root / ".roadmusic/history/final-delivery.json"
    _atomic_json(history, receipt)
    project_id = listed["id"]
    if listed["state"] == "editing":
        result = manager.dispatch("policy", {"projectId": project_id, "state": "completed", "retainDays": 0})
        cleanup = result.get("cleanup", {"removedFiles": 0, "freedBytes": 0})
    else:
        cleanup = manager.maybe_cleanup(project_id)
    try:
        owned = _owned_cleanup(manager, root, project_id, listed, media, source_path, _production_fingerprint(root))
    except (OSError, StorageError) as error:
        owned = {"removedFiles": 0, "freedBytes": 0, "skipped": [{"reason": f"파생 WAV 정리 보류: {error}"}]}
    cleanup = {**cleanup, "ownedRenderCache": owned}
    return {"completed": True, "projectId": project_id, "outputs": len(outputs), "cleanup": cleanup,
            "receipt": str(history)}


def prepare_project(project, generated_cache=None):
    root = _project(project)
    registered = shared_storage_manager().dispatch("register", {"project": str(root)})
    (root / ".roadmusic/cache/picture").mkdir(parents=True, exist_ok=True)
    if generated_cache is not None:
        _record_generated_cache(root, generated_cache)
    return registered


def acquire_render_lease(project):
    root = _project(project)
    registered = prepare_project(root)
    return shared_storage_manager().dispatch("lease", {
        "projectId": registered["id"], "operation": "acquire", "pid": os.getpid(),
    })


def _cleanup_over_budget_picture_cache(manager, project_id, picture):
    """성공한 편집 작업에서만, 예산을 넘긴 재생성 picture 캐시 한 항목을 정리한다."""
    listed = manager.dispatch("list", {"projectId": project_id})["projects"][0]
    if not listed["autoCleanup"]:
        return None
    cache_entries = [entry for entry in listed["entries"] if entry["kind"] == "cache"]
    cache_bytes = sum(entry["bytes"] for entry in cache_entries)
    cache_files = sum(entry["fileCount"] for entry in cache_entries)
    if cache_bytes <= listed["maxCacheBytes"] and cache_files <= listed["maxCacheFiles"]:
        return None
    picture_entry = next((entry for entry in cache_entries if entry["relativePath"] == picture), None)
    if picture_entry is None or picture_entry["pinned"]:
        return None
    preview = manager.dispatch("preview", {"projectId": project_id, "entryIds": [picture_entry["id"]], "kinds": ["cache"]})
    if not preview["fileCount"]:
        return None
    result = manager.dispatch("cleanup", {"planId": preview["planId"], "confirm": True})
    if result["skipped"] or result["warnings"]:
        return "저장공간 캐시 자동 정리 일부 보류: " + "; ".join(
            [item["reason"] for item in result["skipped"]] + result["warnings"]
        )
    return None


def finish_render(project, token, *, succeeded, project_id=None):
    """리스는 항상 해제하고, 보조 정리 실패는 성공한 제작 결과를 뒤집지 않는다."""
    root = _project(project)
    manager = shared_storage_manager()
    warning = None
    registered = None
    try:
        registered = manager.dispatch("register", {"project": str(root)})
        picture = root / ".roadmusic/cache/picture"
        if picture.exists():
            manager.dispatch("track", {
                "projectId": registered["id"], "path": str(picture.relative_to(root)),
                "kind": "cache", "description": "렌더 중간 picture와 재개용 parts",
                "reproducible": True,
            })
    except Exception as error:
        warning = f"저장공간 캐시 등록 실패: {error}"
    active_project_id = registered["id"] if registered else project_id
    if not succeeded and active_project_id:
        try:
            # 실패한 렌더는 재개 가능한 작업이므로 완료 정책의 정리를 실행하지 않는다.
            manager.dispatch("policy", {"projectId": active_project_id, "state": "editing"})
        except Exception as error:
            warning = warning or f"저장공간 작업 상태 복원 실패: {error}"
    try:
        manager.dispatch("lease", {
            "projectId": active_project_id, "operation": "release", "token": token,
        })
    except Exception as error:
        warning = warning or f"저장공간 작업 잠금 해제 실패: {error}"
    if succeeded and registered:
        try:
            manager.maybe_cleanup(registered["id"])
        except Exception as error:
            warning = warning or f"저장공간 자동 정리 실패: {error}"
        if warning is None:
            try:
                warning = _cleanup_over_budget_picture_cache(manager, registered["id"], ".roadmusic/cache/picture")
            except Exception as error:
                warning = f"저장공간 캐시 자동 정리 실패: {error}"
    return warning


def cleanup_completed(project):
    try:
        root = _project(project)
        registered = prepare_project(root)
        shared_storage_manager().maybe_cleanup(registered["id"])
    except Exception as error:
        return f"저장공간 자동 정리 실패: {error}"
    return None


# Production telemetry is deliberately best-effort: a SQLite problem must never
# turn a successfully rendered user file into a failed production.


def _production_warning(error):
    return f"제작 측정 이력 저장 실패: {str(error)[:500]}"


def production_task_failure_status(error):
    return "cancelled" if isinstance(error, KeyboardInterrupt) else "failed"


def _production_files(root, since_ns=None):
    """Stream metadata for one producer project; never scan the workspace/profile."""
    root = _project(root)
    if root in {shared_storage_manager().data_dir, _trusted_workspace()}:
        raise ValueError("전체 프로그램·프로필은 제작 파일로 수집하지 않습니다")
    def failed(error):
        raise error
    for base, directories, names in os.walk(root, followlinks=False, onerror=failed):
        directories[:] = sorted(name for name in directories if not (Path(base) / name).is_symlink())
        for name in sorted(names):
            path = Path(base) / name
            if path.is_symlink() or not path.is_file():
                continue
            if since_ns is not None:
                metadata = path.stat(follow_symlinks=False)
                if max(metadata.st_mtime_ns, metadata.st_ctime_ns) < since_ns:
                    continue
            relative = path.relative_to(root)
            parts = relative.parts
            if parts and parts[0] == "inputs":
                role = "input"
            elif parts[:2] == (".roadmusic", "cache"):
                role = "cache"
            elif parts and parts[0] == "out":
                role = "final"
            elif parts and parts[0] in {"audio", "reel", "captions"}:
                role = "intermediate"
            else:
                role = "artifact"
            yield {"path": str(path), "role": role}


def record_production_prompt(project, prompt, *, intent, source="engine", title=None, group_id=None):
    """Record an explicit producer prompt and return its id without blocking work."""
    if not isinstance(prompt, str) or not prompt.strip():
        return None, None
    try:
        from production_ledger import ProductionLedger
        root = _project(project)
        group_id = group_id or _production_group_id(root)
        params = {
            "project": str(root), "domain": "motion", "intent": intent,
            "prompt": prompt, "source": source, "title": title,
        }
        if group_id:
            params["groupId"] = group_id
        record = ProductionLedger(shared_storage_manager().data_dir).request(params)
        return record.get("requestId"), None
    except Exception as error:
        return None, _production_warning(error)


def start_production_task(project, *, task_type, engine=None, model=None, request_id=None, parent_task_id=None, title=None, group_id=None, expected_media_seconds=None, expected_frame_count=None):
    """Start a project-local telemetry task and retain a monotonic clock for it."""
    root = _project(project)
    handle = {"project": str(root), "started": time.perf_counter(), "startedNs": time.time_ns(), "taskId": None, "warning": None}
    try:
        from production_ledger import ProductionLedger
        group_id = group_id or _production_group_id(root)
        params = {
            "project": str(root), "domain": "motion", "taskType": task_type,
            "engine": engine, "model": model, "requestId": request_id,
            "parentTaskId": parent_task_id, "title": title,
        }
        if group_id:
            params["groupId"] = group_id
        if isinstance(expected_media_seconds, (int, float)) and not isinstance(expected_media_seconds, bool) and expected_media_seconds >= 0:
            params["expectedMediaSeconds"] = float(expected_media_seconds)
        if isinstance(expected_frame_count, int) and not isinstance(expected_frame_count, bool) and expected_frame_count >= 0:
            params["expectedFrameCount"] = expected_frame_count
        ledger = ProductionLedger(shared_storage_manager().data_dir)
        if request_id:
            with ledger.db.transaction() as connection:
                prompt = connection.execute("SELECT source FROM production_prompts WHERE request_id=?", (request_id,)).fetchone() if ledger.db._has_table(connection, "production_prompts") else None
            if prompt and prompt[0] == "engine":
                params["engineRequestId"] = request_id
                params["requestId"] = None
        record = ledger.start_task(params)
        handle["taskId"] = record.get("taskId")
    except Exception as error:
        handle["warning"] = _production_warning(error)
    return handle


def progress_production_task(handle, *, progress=None, current_stage=None, summary=None):
    """Persist an observed producer boundary; callers never invent a fraction."""
    warning = handle.get("warning") if isinstance(handle, dict) else None
    if not isinstance(handle, dict) or not handle.get("taskId"):
        return warning
    payload = {"taskId": handle["taskId"]}
    if isinstance(progress, (int, float)) and not isinstance(progress, bool) and 0 <= progress <= 1:
        payload["progress"] = float(progress)
    if isinstance(current_stage, str) and current_stage:
        payload["currentStage"] = current_stage[:240]
    if isinstance(summary, str) and summary:
        payload["summary"] = summary[:4000]
    if len(payload) == 1:
        return warning
    try:
        from production_ledger import ProductionLedger
        ProductionLedger(shared_storage_manager().data_dir).progress_task(payload)
    except Exception as error:
        warning = warning or _production_warning(error)
    return warning


def finish_production_task(handle, *, status, media_seconds=None, frame_count=None, ai_summary=None, result_summary=None, error_summary=None, file_records=None):
    """Finish a telemetry task, retaining removed-file history through SQLite rows."""
    warning = handle.get("warning") if isinstance(handle, dict) else None
    if not isinstance(handle, dict) or not handle.get("taskId"):
        return warning
    try:
        from production_ledger import ProductionLedger
        root = _project(handle["project"])
        elapsed_ms = round((time.perf_counter() - handle["started"]) * 1000)
        ledger = ProductionLedger(shared_storage_manager().data_dir)
        inventory_complete = True
        inventory_warning = None
        try:
            files = _production_files(root, since_ns=handle.get("startedNs")) if file_records is None else iter(file_records)
            batch = []
            for record in files:
                batch.append(record)
                if len(batch) == 200:
                    ledger.record_files({"taskId": handle["taskId"], "files": batch})
                    batch = []
            if batch:
                ledger.record_files({"taskId": handle["taskId"], "files": batch})
        except Exception as error:
            inventory_complete = False
            inventory_warning = f"생성 파일 일부의 기록을 확인하지 못했습니다: {str(error)[:500]}"
        payload = {
            "taskId": handle["taskId"], "status": status,
            "elapsedMs": elapsed_ms,
            "fileInventoryComplete": inventory_complete,
        }
        if inventory_warning:
            payload["fileInventoryWarning"] = inventory_warning
        if isinstance(media_seconds, (int, float)) and not isinstance(media_seconds, bool):
            payload["mediaSeconds"] = float(media_seconds)
        if isinstance(frame_count, int) and not isinstance(frame_count, bool):
            payload["frameCount"] = frame_count
        for key, value in (("aiSummary", ai_summary), ("resultSummary", result_summary), ("errorSummary", error_summary)):
            if isinstance(value, str) and value:
                payload[key] = value[:4000]
        ledger.finish_task(payload)
        if inventory_warning:
            warning = warning or inventory_warning
    except Exception as error:
        warning = warning or _production_warning(error)
    return warning

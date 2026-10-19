"""Canonical Output delivery files with a small SQLite version history."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from zoneinfo import ZoneInfo

from storage_packaging import TRUSTED_ROOT


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
PROJECT_ID = re.compile(r"[0-9a-f]{64}\Z")
FINAL_KINDS = frozenset({"music", "video", "lyrics", "captions", "storyboard"})
SNAPSHOT_FILES = ("studio-project.json", "meta.json", "production.json", "native-production.json", "playlist.json", "composition.json", "display.json", "script.json", "project.jizura.json", "production-request.json", "showreel-request.json", "selection.json", "feedback.json")
MAX_TEXT = 256 * 1024
MAX_SNAPSHOT = 2 * 1024 * 1024


def _sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _slug(value, fallback):
    value = re.sub(r"[\\/\x00-\x1f]+", "-", str(value).strip())
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return value[:80] or fallback


def _label(value, fallback):
    return re.sub(r"--[0-9a-f]{12}\Z", "", _slug(value, fallback)) or fallback


def _snapshot_json(value):
    try:
        result = json.loads(value) if isinstance(value, str) else {}
    except json.JSONDecodeError:
        result = {}
    return result if isinstance(result, dict) else {}


class DeliveryStore:
    """Stores only final copies under Output; SQLite retains the compact change history."""

    def __init__(self, root=None):
        root = TRUSTED_ROOT if root is None else root
        if root is None:
            raise ValueError("현재 설치의 Road Music 작업 폴더를 찾을 수 없습니다")
        root = Path(root)
        if not root.is_absolute() or root.is_symlink():
            raise ValueError("작업 폴더는 심볼릭 링크가 아닌 절대 경로여야 합니다")
        self.root = root.resolve(strict=True)
        self.history = self.root / ".roadmusic" / "history.sqlite3"

    def _connect(self):
        self._mkdir(self.history.parent)
        for path in (self.history, self.history.with_name(f'{self.history.name}-wal'), self.history.with_name(f'{self.history.name}-shm')):
            if path.exists() and path.is_symlink():
                raise ValueError("버전 이력 파일에 심볼릭 링크를 사용할 수 없습니다")
        connection = sqlite3.connect(self.history)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS delivery_groups (
              group_id TEXT PRIMARY KEY, title TEXT NOT NULL, source_sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS delivery_projects (
              project_id TEXT PRIMARY KEY, group_id TEXT NOT NULL REFERENCES delivery_groups(group_id), logical_project_id TEXT NOT NULL DEFAULT '', name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS delivery_versions (
              id TEXT PRIMARY KEY, group_id TEXT NOT NULL REFERENCES delivery_groups(group_id),
              project_id TEXT NOT NULL REFERENCES delivery_projects(project_id), created_at TEXT NOT NULL,
              stamp TEXT NOT NULL, summary TEXT NOT NULL, reason TEXT NOT NULL, fingerprint TEXT NOT NULL,
              snapshot_json TEXT NOT NULL, UNIQUE(group_id, project_id, fingerprint), UNIQUE(group_id, project_id, stamp)
            );
            CREATE TABLE IF NOT EXISTS delivery_files (
              version_id TEXT NOT NULL REFERENCES delivery_versions(id) ON DELETE CASCADE,
              kind TEXT NOT NULL, path TEXT NOT NULL, original_path TEXT NOT NULL DEFAULT '', name TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
              PRIMARY KEY(version_id, kind, name)
            );
            CREATE INDEX IF NOT EXISTS delivery_versions_group ON delivery_versions(group_id, created_at DESC);
        """)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(delivery_files)")}
        if "original_path" not in columns:
            connection.execute("ALTER TABLE delivery_files ADD COLUMN original_path TEXT NOT NULL DEFAULT ''")
        project_columns = {row[1] for row in connection.execute("PRAGMA table_info(delivery_projects)")}
        if "logical_project_id" not in project_columns:
            connection.execute("ALTER TABLE delivery_projects ADD COLUMN logical_project_id TEXT NOT NULL DEFAULT ''")
        return connection

    def _mkdir(self, target):
        target = Path(target)
        relative = target.relative_to(self.root)
        current = self.root
        if current.is_symlink():
            raise ValueError("작업 폴더 심볼릭 링크는 사용할 수 없습니다")
        for part in relative.parts:
            current /= part
            if current.exists() and current.is_symlink():
                raise ValueError("출력 경로에 심볼릭 링크가 있습니다")
            current.mkdir(exist_ok=True)

    def _project(self, value):
        path = Path(value)
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("프로젝트는 심볼릭 링크가 아닌 절대 폴더여야 합니다")
        path = path.resolve(strict=True)
        if not path.is_dir():
            raise ValueError("프로젝트 폴더가 필요합니다")
        return path

    @staticmethod
    def _regular(item):
        path = Path(item.get("path", ""))
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("심볼릭 링크가 아닌 절대 일반 파일만 완성본으로 게시할 수 있습니다")
        path = path.resolve(strict=True)
        if not path.is_file() or path.is_symlink():
            raise ValueError("완성본 일반 파일이 필요합니다")
        return path

    def _media(self, media, source_sha256, allow_source_only=False):
        if not isinstance(media, list) or not media:
            raise ValueError("게시할 제작실 미디어가 필요합니다")
        if not isinstance(source_sha256, str) or not SHA256.fullmatch(source_sha256.lower()):
            raise ValueError("원음 SHA-256이 올바르지 않습니다")
        source_sha256 = source_sha256.lower()
        final, artifacts = [], []
        source_seen = False
        names = set()
        for item in media:
            if not isinstance(item, dict) or not isinstance(item.get("kind"), str):
                raise ValueError("제작실 미디어 형식이 올바르지 않습니다")
            kind = item["kind"]
            path = self._regular(item)
            stat = path.stat()
            digest = _sha256(path)
            if item.get("sha256") not in {None, digest} or item.get("size") not in {None, stat.st_size}:
                raise ValueError("게시 전 미디어가 변경되었습니다")
            entry = {"id": item.get("id"), "kind": kind, "path": str(path), "name": path.name, "sha256": digest, "bytes": stat.st_size}
            if kind == "artifact":
                artifacts.append({key: item.get(key) for key in ("id", "name", "kind", "artifactType")})
                artifacts[-1].update({"sha256": digest, "bytes": stat.st_size})
                continue
            if kind not in FINAL_KINDS:
                raise ValueError("완성본 종류가 올바르지 않습니다")
            if item.get("id") == "music":
                if digest != source_sha256:
                    raise ValueError("등록 원음과 source_sha256이 일치하지 않습니다")
                source_seen = True
            marker = (kind, path.name.casefold())
            if marker in names:
                raise ValueError("같은 종류의 완성본 파일명이 중복됩니다")
            names.add(marker)
            final.append(entry)
        if not source_seen:
            raise ValueError("등록된 입력 원음을 함께 게시해야 합니다")
        if not allow_source_only and not any(item["kind"] in {"music", "video"} and item.get("id") != "music" for item in final):
            raise ValueError("완성 음원 또는 영상이 필요합니다")
        return final, artifacts

    @staticmethod
    def _read_json(path):
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_TEXT:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _snapshot(self, project, media, artifacts):
        result = {"project": {}, "text": {}, "artifacts": artifacts}
        for name in SNAPSHOT_FILES:
            path = project / name
            value = self._read_json(path)
            if name == "studio-project.json" and isinstance(value, dict):
                value = {key: value.get(key) for key in ("schemaVersion", "name", "projectName", "host", "mode", "imagePolicy") if key in value}
                value["media"] = [{key: item.get(key) for key in ("id", "kind", "name", "sha256", "size", "sourceMusicSha256", "producedAt", "forVideoSha256", "artifactType") if key in item} for item in media]
            if value is not None:
                result["project"][name] = value
        scenes = project / 'reel' / 'scenes.js'
        if scenes.is_file() and not scenes.is_symlink() and scenes.stat().st_size <= MAX_TEXT:
            result['text']['authored:reel/scenes.js'] = scenes.read_text(encoding='utf-8-sig')
        for item in media:
            if item["kind"] not in {"lyrics", "captions"}:
                continue
            if item["bytes"] > MAX_TEXT:
                continue
            try:
                result["text"][f'{item["kind"]}:{item["name"]}'] = Path(item["path"]).read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                continue
        if len(_json(result).encode()) > MAX_SNAPSHOT:
            raise ValueError("버전 이력이 너무 커서 게시하지 않습니다")
        return result

    @staticmethod
    def _created(value):
        if value is None:
            return datetime.now(ZoneInfo("Asia/Seoul"))
        if not isinstance(value, str):
            raise ValueError("created_at은 ISO 시각이어야 합니다")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("created_at은 ISO 시각이어야 합니다") from error
        if parsed.tzinfo is None:
            raise ValueError("created_at에는 시간대가 필요합니다")
        return parsed.astimezone(ZoneInfo("Asia/Seoul"))

    @staticmethod
    def _fingerprint(group_id, project_id, files, snapshot):
        payload = {"groupId": group_id, "projectId": project_id,
                   "files": [{key: item[key] for key in ("kind", "name", "sha256", "bytes")} for item in files],
                   "snapshot": snapshot}
        return hashlib.sha256(_json(payload).encode()).hexdigest()

    def _copy(self, source, destination, expected):
        before = source.stat()
        if source.is_symlink() or _sha256(source) != expected:
            raise ValueError("게시 중 원본이 변경되었습니다")
        with tempfile.NamedTemporaryFile("wb", dir=destination.parent, prefix=f".{destination.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            with source.open("rb") as input_stream:
                shutil.copyfileobj(input_stream, stream, 1024 * 1024)
            stream.flush(); os.fsync(stream.fileno())
        try:
            if _sha256(temporary) != expected or temporary.stat().st_size != before.st_size:
                raise ValueError("완성본 복사를 검증하지 못했습니다")
            after = source.stat()
            if after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns or _sha256(source) != expected:
                raise ValueError("게시 중 원본이 변경되었습니다")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _version_data(self, row, files, previous=None, tombstones=None):
        tombstones = tombstones or {}
        for item in files:
            removed = tombstones.get((item["kind"], item["name"], item["path"]))
            if removed is not None:
                item["deleted"] = True; item["deletedAt"] = removed
        return {"id": row["id"], "groupId": row["group_id"], "projectId": row["project_id"], "logicalProjectId": row["logical_project_id"], "projectName": row["project_name"],
                "createdAt": row["created_at"], "stamp": row["stamp"], "summary": row["summary"], "reason": row["reason"] or "", "files": files,
                "changes": self._changes(_snapshot_json(previous["snapshot_json"]) if previous else None, _snapshot_json(row["snapshot_json"]), previous["reason"] if previous else "", row["reason"] or "")}

    def _version(self, connection, row):
        files = [dict(file) for file in connection.execute("SELECT kind,path,original_path originalPath,name,sha256,bytes FROM delivery_files WHERE version_id=? ORDER BY kind,name", (row["id"],))]
        tombstones = self._tombstones(connection, row["id"])
        previous = self._previous(connection, row)
        return self._version_data(row, files, previous, tombstones)

    @staticmethod
    def _tombstones(connection, version_id):
        try:
            try:
                rows = connection.execute("SELECT kind,name,path,deleted_at FROM delivery_file_tombstones WHERE version_id=? AND state='applied'", (version_id,)).fetchall()
            except sqlite3.OperationalError:
                rows = connection.execute("SELECT kind,name,path,deleted_at FROM delivery_file_tombstones WHERE version_id=?", (version_id,)).fetchall()
        except sqlite3.OperationalError:
            return {}
        return {(row["kind"], row["name"], row["path"]): row["deleted_at"] for row in rows}

    @staticmethod
    def _tombstones_many(connection, version_ids):
        if not version_ids:
            return {}
        placeholders = ",".join("?" for _ in version_ids)
        try:
            try:
                rows = connection.execute(f"SELECT version_id,kind,name,path,deleted_at FROM delivery_file_tombstones WHERE version_id IN ({placeholders}) AND state='applied'", version_ids).fetchall()
            except sqlite3.OperationalError:
                rows = connection.execute(f"SELECT version_id,kind,name,path,deleted_at FROM delivery_file_tombstones WHERE version_id IN ({placeholders})", version_ids).fetchall()
        except sqlite3.OperationalError:
            return {}
        result = {}
        for row in rows:
            result.setdefault(row["version_id"], {})[(row["kind"], row["name"], row["path"])] = row["deleted_at"]
        return result

    @staticmethod
    def _previous(connection, row):
        return connection.execute("""SELECT v.*, p.name project_name, p.logical_project_id, v.rowid delivery_rowid
            FROM delivery_versions v JOIN delivery_projects p USING(project_id)
            WHERE v.group_id=? AND v.project_id=? AND (v.created_at<? OR (v.created_at=? AND v.rowid<?))
            ORDER BY v.created_at DESC, v.rowid DESC LIMIT 1""", (row["group_id"], row["project_id"], row["created_at"], row["created_at"], row["delivery_rowid"])).fetchone()

    @staticmethod
    def _verify_delivery_files(connection, version_id):
        if DeliveryStore._tombstones(connection, version_id):
            raise ValueError("제거된 완성본이 포함된 기존 게시본은 재사용하지 않습니다")
        for item in connection.execute("SELECT path,sha256,bytes FROM delivery_files WHERE version_id=?", (version_id,)):
            raw = Path(item["path"])
            try:
                if not raw.is_absolute() or raw.is_symlink() or raw.resolve(strict=True) != raw or not raw.is_file():
                    raise ValueError()
                stat = raw.stat()
                if stat.st_size != item["bytes"] or _sha256(raw) != item["sha256"]:
                    raise ValueError()
            except (OSError, ValueError):
                raise ValueError("기존 완성본이 없거나 변경되어 같은 게시를 재사용하지 않습니다") from None

    @staticmethod
    def _flat(value, prefix=""):
        if isinstance(value, dict):
            result = {}
            for key in sorted(value):
                result.update(DeliveryStore._flat(value[key], f"{prefix}.{key}" if prefix else str(key)))
            return result
        if isinstance(value, list):
            return {prefix: value}
        return {prefix: value}

    def _changes(self, before, after, before_reason, after_reason):
        left, right = self._flat(before or {}), self._flat(after or {})
        left["reason"] = before_reason or "미기록"; right["reason"] = after_reason or "미기록"
        return [{"field": key, "before": left.get(key), "after": right.get(key)} for key in sorted(set(left) | set(right)) if left.get(key) != right.get(key)]

    def publish(self, project, media, *, source_sha256, title, reason="", created_at=None, project_id=None, _allow_source_only=False, studio_name=None):
        """Verify, copy and index one immutable final delivery version."""
        project = self._project(project)
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 180:
            raise ValueError("완성본 제목이 필요합니다")
        if not isinstance(reason, str) or len(reason) > 12_000:
            raise ValueError("변경 사유가 올바르지 않습니다")
        group_id = source_sha256.lower()
        if not SHA256.fullmatch(group_id):
            raise ValueError("원음 SHA-256이 올바르지 않습니다")
        logical_project_id = project_id or hashlib.sha256(str(project).encode()).hexdigest()
        if not isinstance(logical_project_id, str) or not PROJECT_ID.fullmatch(logical_project_id):
            raise ValueError("프로젝트 ID가 올바르지 않습니다")
        project_id = hashlib.sha256(f"{group_id}\0{logical_project_id}".encode()).hexdigest()
        files, artifacts = self._media(media, group_id, _allow_source_only)
        snapshot = self._snapshot(project, files, artifacts)
        if studio_name is not None:
            if not isinstance(studio_name, str) or not 1 <= len(studio_name.strip()) <= 240:
                raise ValueError('제작실 프로젝트 이름이 올바르지 않습니다')
            snapshot['project'].setdefault('studio-project.json', {})['name'] = studio_name.strip()
        fingerprint = self._fingerprint(group_id, project_id, files, snapshot)
        created = self._created(created_at)
        project_metadata = snapshot.get("project", {}).get("studio-project.json", {})
        project_name = _label(project_metadata.get("projectName") or project_metadata.get("name") or project.name, "project")
        title = title.strip()
        connection = self._connect()
        staging = None
        try:
            existing = connection.execute("""SELECT v.*, p.name project_name, p.logical_project_id, v.rowid delivery_rowid FROM delivery_versions v JOIN delivery_projects p USING(project_id)
                WHERE v.group_id=? AND v.project_id=? AND v.fingerprint=?""", (group_id, project_id, fingerprint)).fetchone()
            if existing is not None:
                self._verify_delivery_files(connection, existing["id"])
                result = self._version(connection, existing)
                inputs = {(item['kind'], item['sha256'], item['name']): item for item in files}
                media = []
                for item in result['files']:
                    original = inputs.get((item['kind'], item['sha256'], Path(item['originalPath']).name)) or inputs.get((item['kind'], item['sha256'], item['name']))
                    if original is None:
                        raise ValueError('기존 게시 파일과 입력 미디어의 연결을 확인할 수 없습니다')
                    media.append({**item, 'id': original.get('id'), 'size': item['bytes']})
                result['media'] = media
                return result
            base = created.strftime("%Y%m%d-%H%M%S")
            stamps = {row[0] for row in connection.execute("SELECT stamp FROM delivery_versions WHERE group_id=? AND project_id=?", (group_id, project_id))}
            stamp, sequence = base, 2
            while stamp in stamps or (self.root / "Output" / f"{_slug(title, 'music')}--{group_id[:12]}" / f"{project_name}--{project_id[:12]}" / stamp).exists():
                stamp = f"{base}-{sequence}"; sequence += 1
            destination = self.root / "Output" / f"{_label(title, 'music')}--{group_id[:12]}" / f"{project_name}--{project_id[:12]}" / stamp
            self._mkdir(destination.parent)
            staging = destination.parent / f".{stamp}-{os.getpid()}-{next(tempfile._get_candidate_names())}"
            staging.mkdir(mode=0o700)
            published = []
            used = set()
            for item in files:
                name = item["name"]
                stem, suffix = Path(name).stem, Path(name).suffix
                number = 2
                while name.casefold() in used:
                    name = f"{stem}-{number}{suffix}"; number += 1
                used.add(name.casefold())
                target = staging / name
                self._copy(Path(item["path"]), target, item["sha256"])
                published.append({**item, "originalPath": item["path"], "path": str(destination / name), "name": name})
            os.replace(staging, destination); staging = None
            version_id = hashlib.sha256(f"{group_id}\0{project_id}\0{stamp}\0{fingerprint}".encode()).hexdigest()
            summary = reason.strip() or "변경 사유 미기록"
            try:
                with connection:
                    connection.execute("INSERT INTO delivery_groups(group_id,title,source_sha256) VALUES(?,?,?) ON CONFLICT(group_id) DO UPDATE SET title=excluded.title", (group_id, title, group_id))
                    connection.execute("INSERT INTO delivery_projects(project_id,group_id,logical_project_id,name) VALUES(?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET name=excluded.name", (project_id, group_id, logical_project_id, project_name))
                    connection.execute("INSERT INTO delivery_versions(id,group_id,project_id,created_at,stamp,summary,reason,fingerprint,snapshot_json) VALUES(?,?,?,?,?,?,?,?,?)", (version_id, group_id, project_id, created.isoformat(), stamp, summary, reason.strip(), fingerprint, _json(snapshot)))
                    connection.executemany("INSERT INTO delivery_files(version_id,kind,path,original_path,name,sha256,bytes) VALUES(?,?,?,?,?,?,?)", [(version_id, item["kind"], item["path"], item["originalPath"], item["name"], item["sha256"], item["bytes"]) for item in published])
            except Exception:
                shutil.rmtree(destination, ignore_errors=True)
                raise
            row = connection.execute("SELECT v.*, p.name project_name, p.logical_project_id, v.rowid delivery_rowid FROM delivery_versions v JOIN delivery_projects p USING(project_id) WHERE v.id=?", (version_id,)).fetchone()
            result = self._version(connection, row)
            result["media"] = [{**item, "size": item["bytes"]} for item in published]
            return result
        finally:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
            connection.close()

    def versions(self, params):
        """Return paged delivery versions for one source-audio group."""
        if not isinstance(params, dict) or set(params) - {"groupId", "projectId", "limit", "offset"}:
            raise ValueError("버전 목록 조건이 올바르지 않습니다")
        group_id = params.get("groupId")
        if not isinstance(group_id, str) or not SHA256.fullmatch(group_id):
            raise ValueError("그룹 ID가 올바르지 않습니다")
        project_id = params.get("projectId")
        if project_id is not None and (not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id)):
            raise ValueError("프로젝트 ID가 올바르지 않습니다")
        limit, offset = params.get("limit", 50), params.get("offset", 0)
        if not isinstance(limit, int) or not 1 <= limit <= 200 or not isinstance(offset, int) or offset < 0:
            raise ValueError("페이지 조건이 올바르지 않습니다")
        connection = self._connect()
        try:
            where, values = "v.group_id=?", [group_id]
            if project_id is not None: where += " AND v.project_id=?"; values.append(project_id)
            total = connection.execute(f"SELECT count(*) FROM delivery_versions v WHERE {where}", values).fetchone()[0]
            rows = connection.execute(f"""SELECT * FROM (
                SELECT v.*, p.name project_name, p.logical_project_id, v.rowid delivery_rowid,
                       LAG(v.snapshot_json) OVER (PARTITION BY v.group_id,v.project_id ORDER BY v.created_at,v.rowid) previous_snapshot_json,
                       LAG(v.reason) OVER (PARTITION BY v.group_id,v.project_id ORDER BY v.created_at,v.rowid) previous_reason
                FROM delivery_versions v JOIN delivery_projects p USING(project_id) WHERE {where}
            ) ORDER BY created_at DESC,delivery_rowid DESC LIMIT ? OFFSET ?""", [*values, limit, offset]).fetchall()
            ids = [row["id"] for row in rows]
            files = {identifier: [] for identifier in ids}
            if ids:
                placeholders = ",".join("?" for _ in ids)
                for item in connection.execute(f"SELECT version_id,kind,path,original_path originalPath,name,sha256,bytes FROM delivery_files WHERE version_id IN ({placeholders}) ORDER BY kind,name", ids):
                    files[item["version_id"]].append(dict(item))
            tombstones = self._tombstones_many(connection, ids)
            projects = [dict(row) for row in connection.execute("SELECT project_id id,logical_project_id logicalProjectId,name FROM delivery_projects WHERE group_id=? ORDER BY name", (group_id,))]
            versions = []
            for row in rows:
                previous = None if row["previous_snapshot_json"] is None else {"snapshot_json": row["previous_snapshot_json"], "reason": row["previous_reason"]}
                versions.append(self._version_data(row, files[row["id"]], previous, tombstones.get(row["id"], {})))
            return {"versions": versions, "projects": projects, "total": total}
        finally:
            connection.close()

    def diff(self, params):
        """Compare snapshots and final file hashes for two versions."""
        if not isinstance(params, dict) or set(params) != {"fromId", "toId"}:
            raise ValueError("비교할 두 버전 ID가 필요합니다")
        connection = self._connect()
        try:
            rows = [connection.execute("SELECT v.*,p.name project_name,p.logical_project_id FROM delivery_versions v JOIN delivery_projects p USING(project_id) WHERE v.id=?", (params[key],)).fetchone() for key in ("fromId", "toId")]
            if any(row is None for row in rows):
                raise ValueError("등록된 버전을 찾을 수 없습니다")
            before, after = rows
            if before["group_id"] != after["group_id"] or before["project_id"] != after["project_id"]:
                raise ValueError("같은 음악과 프로젝트 버전만 비교할 수 있습니다")
            file_rows = [connection.execute("SELECT kind,name,sha256,bytes,path,original_path originalPath FROM delivery_files WHERE version_id=?", (row["id"],)).fetchall() for row in rows]
            left, right = ({(item["kind"], item["name"]): dict(item) for item in values} for values in file_rows)
            changes = []
            for key in sorted(set(left) | set(right)):
                old, new = left.get(key), right.get(key)
                status = "added" if old is None else "removed" if new is None else "changed" if (old["sha256"], old["bytes"]) != (new["sha256"], new["bytes"]) else "unchanged"
                if status != "unchanged": changes.append({"status": status, "kind": key[0], "name": key[1], "before": old, "after": new})
            return {"fromId": before["id"], "toId": after["id"], "groupId": before["group_id"], "projectId": before["project_id"],
                    "changes": self._changes(_snapshot_json(before["snapshot_json"]), _snapshot_json(after["snapshot_json"]), before["reason"] or "", after["reason"] or ""), "fileChanges": changes}
        finally:
            connection.close()


def record_song(root, song_dir, reason=""):
    """Publish a verified completed song folder without changing its generated source."""
    song_dir = Path(song_dir)
    if not song_dir.is_absolute() or song_dir.is_symlink():
        raise ValueError("곡 폴더는 심볼릭 링크가 아닌 절대 경로여야 합니다")
    song_dir = song_dir.resolve(strict=True)
    meta_path = song_dir / "meta.json"
    if not meta_path.is_file() or meta_path.is_symlink() or meta_path.stat().st_size > MAX_TEXT:
        raise ValueError("검증된 meta.json이 필요합니다")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("meta.json을 읽을 수 없습니다") from error
    if not isinstance(meta, dict) or meta.get("status") != "done" or not isinstance(meta.get("audio"), str):
        raise ValueError("완료된 곡 meta.json이 필요합니다")
    audio = Path(meta["audio"])
    if not audio.is_absolute():
        audio = song_dir / audio
    item = {"id": "music", "kind": "music", "path": str(audio)}
    media = [item]
    for key, kind in (("lyrics", "lyrics"), ("captions", "captions")):
        value = meta.get(key)
        if not isinstance(value, str):
            continue
        path = Path(value)
        if not path.is_absolute():
            path = song_dir / path
        if path == audio:
            continue
        media.append({"id": f"{kind}-{len(media)}", "kind": kind, "path": str(path)})
    for path in sorted(song_dir.iterdir()):
        if not path.is_file() or path.is_symlink() or path in {audio, meta_path}:
            continue
        kind = "lyrics" if path.suffix.lower() in {".txt", ".md"} else "captions" if path.suffix.lower() in {".srt", ".vtt", ".lrc", ".ass"} else None
        if kind and all(Path(entry["path"]) != path for entry in media):
            media.append({"id": f"{kind}-{len(media)}", "kind": kind, "path": str(path)})
    title = meta.get("title") if isinstance(meta.get("title"), str) and meta["title"].strip() else song_dir.name
    created_at = meta.get("createdAt") if isinstance(meta.get("createdAt"), str) else None
    return DeliveryStore(root).publish(song_dir, media, source_sha256=_sha256(audio), title=title, reason=reason, created_at=created_at, _allow_source_only=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    song = commands.add_parser("record-song")
    song.add_argument("--root", required=True)
    song.add_argument("--song-dir", required=True)
    song.add_argument("--reason", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "record-song":
            result = record_song(args.root, args.song_dir, args.reason)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, sqlite3.Error) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=__import__("sys").stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

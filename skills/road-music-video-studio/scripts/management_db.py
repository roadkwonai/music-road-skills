"""Small SQLite ledger for Road Music management metadata, never media bytes."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import time

MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_EVENT_BYTES = 256 * 1024


class ManagementDBError(ValueError):
    pass


def _json(value, limit=MAX_DOCUMENT_BYTES):
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ManagementDBError("관리 메타데이터는 JSON 값이어야 합니다") from error
    if len(encoded) > limit:
        raise ManagementDBError("관리 메타데이터가 안전 한도를 초과했습니다")
    return encoded.decode("utf-8")


def _decode(raw):
    try:
        return json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ManagementDBError("SQLite 관리 메타데이터가 손상되었습니다") from error


def _iso(epoch=None):
    return datetime.fromtimestamp(time.time() if epoch is None else epoch, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class ManagementDB:
    """Per-profile ledger. JSON is only a one-time compatible import source."""

    def __init__(self, data_dir):
        raw = Path(data_dir)
        if not raw.is_absolute():
            raise ManagementDBError("관리 데이터 경로는 절대 경로여야 합니다")
        if raw.is_symlink():
            raise ManagementDBError("관리 데이터 경로 symlink는 허용하지 않습니다")
        self.data_dir = raw.resolve()
        self.path = self.data_dir / "storage.sqlite3"

    @contextmanager
    def transaction(self, write=False):
        if self.path.is_symlink():
            raise ManagementDBError("SQLite 관리 DB symlink는 허용하지 않습니다")
        if not write and not self.path.exists():
            yield None
            return
        connection = None
        try:
            if write:
                self.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            creating = write and not self.path.exists()
            target = self.path if write else self.path.as_uri() + "?mode=ro"
            connection = sqlite3.connect(target, timeout=5, isolation_level=None, uri=not write)
            if creating:
                os.chmod(self.path, 0o600)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if write:
                self._schema(connection)
            yield connection
            connection.commit()
        except sqlite3.Error as error:
            raise ManagementDBError("SQLite 관리 DB를 읽거나 기록할 수 없습니다") from error
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    def _connection(self, connection, write=False):
        return nullcontext(connection) if connection is not None else self.transaction(write=write)

    @staticmethod
    def _has_table(connection, name):
        return connection is not None and connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

    @staticmethod
    def _schema(connection):
        schema = """
            CREATE TABLE IF NOT EXISTS management_documents (
              name TEXT PRIMARY KEY, value_json TEXT NOT NULL, imported_from TEXT,
              updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS management_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
              project_id TEXT, group_id TEXT, path TEXT, before_json TEXT,
              after_json TEXT, reason TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS management_events_project_idx ON management_events(project_id, id DESC);
            CREATE INDEX IF NOT EXISTS management_events_group_idx ON management_events(group_id, id DESC);
            CREATE TABLE IF NOT EXISTS management_paths (
              path TEXT PRIMARY KEY, role TEXT NOT NULL, project_id TEXT, group_id TEXT,
              workspace TEXT, kind TEXT NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS management_paths_project_idx ON management_paths(project_id);
            CREATE INDEX IF NOT EXISTS management_paths_group_idx ON management_paths(group_id);
            CREATE TABLE IF NOT EXISTS storage_tracking_files (
              workspace TEXT NOT NULL, relative_path TEXT NOT NULL,
              dev INTEGER, inode INTEGER, size INTEGER NOT NULL, allocated_bytes INTEGER NOT NULL,
              mtime_ns INTEGER, ctime_ns INTEGER, nlink INTEGER, file_type TEXT NOT NULL,
              classification TEXT NOT NULL, label TEXT NOT NULL, protection_reason TEXT NOT NULL,
              indexed_at INTEGER NOT NULL, scan_id TEXT NOT NULL,
              PRIMARY KEY(workspace, relative_path)
            );
            CREATE INDEX IF NOT EXISTS storage_tracking_files_class_idx ON storage_tracking_files(workspace, classification);
            CREATE INDEX IF NOT EXISTS storage_tracking_files_inode_idx ON storage_tracking_files(workspace, dev, inode);
            CREATE TABLE IF NOT EXISTS production_projects (
              project_id TEXT PRIMARY KEY, group_id TEXT, path TEXT NOT NULL UNIQUE,
              title TEXT NOT NULL DEFAULT '', domain TEXT NOT NULL,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS production_projects_group_idx ON production_projects(group_id);
            CREATE TABLE IF NOT EXISTS production_prompts (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE,
              project_id TEXT NOT NULL REFERENCES production_projects(project_id) ON DELETE CASCADE,
              group_id TEXT, domain TEXT NOT NULL, intent TEXT NOT NULL, prompt TEXT NOT NULL,
              source TEXT NOT NULL, is_main INTEGER NOT NULL DEFAULT 0,
              requested_at INTEGER NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS production_prompts_main_idx ON production_prompts(project_id,domain) WHERE is_main=1;
            CREATE INDEX IF NOT EXISTS production_prompts_project_idx ON production_prompts(project_id, seq DESC);
            CREATE INDEX IF NOT EXISTS production_prompts_group_idx ON production_prompts(group_id, seq DESC);
            CREATE TABLE IF NOT EXISTS production_tasks (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL UNIQUE,
              project_id TEXT NOT NULL REFERENCES production_projects(project_id) ON DELETE CASCADE,
              group_id TEXT, request_id TEXT REFERENCES production_prompts(request_id) ON DELETE SET NULL,
              engine_request_id TEXT REFERENCES production_prompts(request_id) ON DELETE SET NULL,
              parent_task_id TEXT REFERENCES production_tasks(task_id) ON DELETE CASCADE,
              domain TEXT NOT NULL, task_type TEXT NOT NULL, engine TEXT, model TEXT,
              status TEXT NOT NULL, queued_at INTEGER, started_at INTEGER NOT NULL, finished_at INTEGER,
              elapsed_ms INTEGER, media_seconds REAL, frame_count INTEGER,
              expected_media_seconds REAL, expected_frame_count INTEGER,
              progress REAL, current_stage TEXT, progress_summary TEXT, progress_updated_at INTEGER,
              ai_summary TEXT, result_summary TEXT, error_summary TEXT,
              file_inventory_complete INTEGER, file_inventory_warning TEXT
            );
            CREATE INDEX IF NOT EXISTS production_tasks_project_idx ON production_tasks(project_id, seq DESC);
            CREATE INDEX IF NOT EXISTS production_tasks_group_idx ON production_tasks(group_id, seq DESC);
            CREATE INDEX IF NOT EXISTS production_tasks_request_idx ON production_tasks(request_id, seq DESC);
            CREATE INDEX IF NOT EXISTS production_tasks_dashboard_idx ON production_tasks(domain,task_type,engine,model,status,finished_at);
            CREATE TABLE IF NOT EXISTS production_files (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL REFERENCES production_tasks(task_id) ON DELETE CASCADE,
              project_id TEXT NOT NULL, group_id TEXT, path TEXT NOT NULL, role TEXT NOT NULL,
              bytes INTEGER, mtime_ns INTEGER, exists_at_finish INTEGER NOT NULL, observed_state TEXT NOT NULL DEFAULT 'present',
              recorded_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS production_files_project_idx ON production_files(project_id, seq DESC);
            CREATE INDEX IF NOT EXISTS production_files_group_idx ON production_files(group_id, seq DESC);
            CREATE INDEX IF NOT EXISTS production_files_task_idx ON production_files(task_id, seq DESC);
            CREATE TABLE IF NOT EXISTS production_components (
              component_id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
              installed_version TEXT, latest_version TEXT, check_status TEXT NOT NULL,
              checked_at INTEGER NOT NULL, source_url TEXT
            );
            CREATE INDEX IF NOT EXISTS production_components_checked_idx ON production_components(checked_at DESC);
            CREATE TABLE IF NOT EXISTS work_favorites (
              group_id TEXT PRIMARY KEY, liked_at INTEGER NOT NULL
            );
        """
        for statement in schema.split(";"):
            if statement.strip():
                connection.execute(statement)
        # Existing profile DBs from the first production-ledger preview retain their
        # records; only writer transactions perform this small forward migration.
        columns = {row[1] for row in connection.execute("PRAGMA table_info(production_tasks)")}
        if "file_inventory_complete" not in columns:
            connection.execute("ALTER TABLE production_tasks ADD COLUMN file_inventory_complete INTEGER")
        if "file_inventory_warning" not in columns:
            connection.execute("ALTER TABLE production_tasks ADD COLUMN file_inventory_warning TEXT")
        if "queued_at" not in columns:
            connection.execute("ALTER TABLE production_tasks ADD COLUMN queued_at INTEGER")
        if "engine_request_id" not in columns:
            connection.execute("ALTER TABLE production_tasks ADD COLUMN engine_request_id TEXT REFERENCES production_prompts(request_id) ON DELETE SET NULL")
        if "expected_media_seconds" not in columns:
            connection.execute("ALTER TABLE production_tasks ADD COLUMN expected_media_seconds REAL")
        if "expected_frame_count" not in columns:
            connection.execute("ALTER TABLE production_tasks ADD COLUMN expected_frame_count INTEGER")
        if "progress" not in columns:
            connection.execute("ALTER TABLE production_tasks ADD COLUMN progress REAL")
        if "current_stage" not in columns:
            connection.execute("ALTER TABLE production_tasks ADD COLUMN current_stage TEXT")
        if "progress_summary" not in columns:
            connection.execute("ALTER TABLE production_tasks ADD COLUMN progress_summary TEXT")
        if "progress_updated_at" not in columns:
            connection.execute("ALTER TABLE production_tasks ADD COLUMN progress_updated_at INTEGER")
        connection.execute("CREATE INDEX IF NOT EXISTS production_tasks_engine_request_idx ON production_tasks(engine_request_id, seq DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS production_tasks_active_idx ON production_tasks(status, queued_at, seq)")
        file_columns = {row[1] for row in connection.execute("PRAGMA table_info(production_files)")}
        if "observed_state" not in file_columns:
            connection.execute("ALTER TABLE production_files ADD COLUMN observed_state TEXT NOT NULL DEFAULT 'present'")
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='production_files_task_path_role_idx'").fetchone() is None:
            connection.execute("DELETE FROM production_files WHERE rowid NOT IN (SELECT max(rowid) FROM production_files GROUP BY task_id,path,role)")
            connection.execute("CREATE UNIQUE INDEX production_files_task_path_role_idx ON production_files(task_id,path,role)")
        if connection.execute("PRAGMA user_version").fetchone()[0] < 3:
            connection.execute("PRAGMA user_version=3")

    @staticmethod
    def _legacy_value(path, fallback):
        legacy = Path(path)
        if legacy.is_symlink():
            raise ManagementDBError("기존 관리 JSON이 안전하지 않습니다")
        if not legacy.exists():
            return deepcopy(fallback)
        if not legacy.is_file() or legacy.stat().st_size > MAX_DOCUMENT_BYTES:
            raise ManagementDBError("기존 관리 JSON이 안전하지 않습니다")
        try:
            return json.loads(legacy.read_text(encoding="utf-8-sig"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise ManagementDBError("기존 관리 JSON을 읽을 수 없습니다") from error

    def read_document(self, name, legacy_path=None, fallback=None, validate=None, connection=None):
        if not isinstance(name, str) or not name or len(name) > 120:
            raise ManagementDBError("관리 문서 이름이 올바르지 않습니다")
        with self._connection(connection) as connection:
            row = connection.execute("SELECT value_json FROM management_documents WHERE name=?", (name,)).fetchone() if self._has_table(connection, "management_documents") else None
            if row:
                value = _decode(row[0])
            else:
                value = self._legacy_value(legacy_path, fallback) if legacy_path is not None else deepcopy(fallback)
            if validate is not None:
                validate(value)
            return deepcopy(value)

    def migrate_legacy(self, name, legacy_path, fallback=None, validate=None, connection=None):
        """Import once, keeping the original and a verified backup for recovery."""
        if not isinstance(name, str) or not name or len(name) > 120:
            raise ManagementDBError("관리 문서 이름이 올바르지 않습니다")
        legacy = Path(legacy_path)
        # Invalid legacy documents must not create a database or alter a previous import.
        with self._connection(connection) as reader:
            row = reader.execute("SELECT value_json FROM management_documents WHERE name=?", (name,)).fetchone() if self._has_table(reader, "management_documents") else None
        if row:
            value = _decode(row[0])
            if validate is not None:
                validate(value)
            return deepcopy(value)
        value = self._legacy_value(legacy, fallback)
        if validate is not None:
            validate(value)
        payload = _json(value)
        backup = None
        if legacy.exists():
            backup = legacy.with_name(legacy.name + ".migration-backup")
            if backup.is_symlink() or (backup.exists() and (not backup.is_file() or backup.read_bytes() != legacy.read_bytes())):
                raise ManagementDBError("기존 관리 JSON 백업 경로가 이미 사용 중입니다")
            if not backup.exists():
                try:
                    with legacy.open("rb") as source, backup.open("xb") as target:
                        while chunk := source.read(1024 * 1024):
                            target.write(chunk)
                        target.flush()
                        os.fsync(target.fileno())
                    os.chmod(backup, 0o600)
                except OSError as error:
                    raise ManagementDBError("기존 관리 JSON 백업을 만들 수 없습니다") from error
            if self._legacy_value(backup, None) != value:
                raise ManagementDBError("기존 관리 JSON 백업을 검증할 수 없습니다")
        with self._connection(connection, write=True) as writer:
            writer.execute("INSERT OR IGNORE INTO management_documents(name,value_json,imported_from,updated_at) VALUES(?,?,?,?)", (name, payload, str(backup) if backup else None, int(time.time())))
            stored = writer.execute("SELECT value_json FROM management_documents WHERE name=?", (name,)).fetchone()
        return deepcopy(_decode(stored[0]))

    def write_document(self, name, value, legacy_path=None, validate=None, connection=None):
        if not isinstance(name, str) or not name or len(name) > 120:
            raise ManagementDBError("관리 문서 이름이 올바르지 않습니다")
        payload = _json(value)
        if validate is not None:
            validate(value)
        if legacy_path is not None:
            self.migrate_legacy(name, legacy_path, fallback=value, validate=validate, connection=connection)
        with self._connection(connection, write=True) as writer:
            writer.execute("INSERT INTO management_documents(name,value_json,updated_at) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at", (name, payload, int(time.time())))

    def delete_document(self, name, connection=None):
        with self._connection(connection, write=True) as connection:
            connection.execute("DELETE FROM management_documents WHERE name=?", (name,))

    def record_event(self, action, project_id=None, group_id=None, before=None, after=None, reason="", path=None, connection=None):
        if not isinstance(action, str) or not action or len(action) > 80:
            raise ManagementDBError("이력 action이 올바르지 않습니다")
        if not isinstance(reason, str) or len(reason) > 1000:
            raise ManagementDBError("이력 reason이 올바르지 않습니다")
        if path is not None and (not isinstance(path, str) or not Path(path).is_absolute()):
            raise ManagementDBError("이력 path는 절대 경로여야 합니다")
        if project_id is not None and (not isinstance(project_id, str) or len(project_id) > 160):
            raise ManagementDBError("이력 projectId가 올바르지 않습니다")
        if group_id is not None and (not isinstance(group_id, str) or len(group_id) > 160):
            raise ManagementDBError("이력 groupId가 올바르지 않습니다")
        before_json = _json(before, MAX_EVENT_BYTES) if before is not None else None
        after_json = _json(after, MAX_EVENT_BYTES) if after is not None else None
        if len((before_json or "").encode()) + len((after_json or "").encode()) > MAX_EVENT_BYTES:
            raise ManagementDBError("이력 상세가 안전 한도를 초과했습니다")
        now = int(time.time())
        production_now = time.time_ns() // 1_000_000
        with self._connection(connection, write=True) as connection:
            if project_id is not None and group_id is not None:
                connection.execute("UPDATE management_events SET group_id=? WHERE project_id=? AND group_id IS NULL", (group_id, project_id))
                connection.execute("UPDATE management_paths SET group_id=? WHERE project_id=? AND group_id IS NULL", (group_id, project_id))
                if self._has_table(connection, "production_projects"):
                    connection.execute("UPDATE production_projects SET group_id=?,updated_at=? WHERE project_id=? AND group_id IS NULL", (group_id, production_now, project_id))
                    for table in ("production_prompts", "production_tasks", "production_files"):
                        connection.execute("UPDATE " + table + " SET group_id=? WHERE project_id=? AND group_id IS NULL", (group_id, project_id))
            cursor = connection.execute("INSERT INTO management_events(action,project_id,group_id,path,before_json,after_json,reason,created_at) VALUES(?,?,?,?,?,?,?,?)", (action, project_id, group_id, path, before_json, after_json, reason, now))
            event_id = cursor.lastrowid
        return {"id": event_id, "action": action, "projectId": project_id, "groupId": group_id, "path": path, "before": before, "after": after, "reason": reason, "createdAt": _iso(now)}

    def events(self, project_id=None, group_id=None, limit=50, cursor=None):
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ManagementDBError("이력 limit이 올바르지 않습니다")
        if cursor is not None and (type(cursor) is not int or cursor < 1):
            raise ManagementDBError("이력 cursor가 올바르지 않습니다")
        where, values = [], []
        if project_id is not None: where.append("project_id=?"); values.append(project_id)
        if group_id is not None: where.append("group_id=?"); values.append(group_id)
        if cursor is not None: where.append("id<?"); values.append(cursor)
        query = "SELECT id,action,project_id,group_id,path,before_json,after_json,reason,created_at FROM management_events" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
        with self.transaction() as connection:
            rows = connection.execute(query, (*values, limit)).fetchall() if self._has_table(connection, "management_events") else []
        result = [{"id": row[0], "action": row[1], "projectId": row[2], "groupId": row[3], "path": row[4], "before": _decode(row[5]) if row[5] is not None else None, "after": _decode(row[6]) if row[6] is not None else None, "reason": row[7], "createdAt": _iso(row[8])} for row in rows]
        return {"events": result, "nextCursor": result[-1]["id"] if len(result) == limit else None}

    def claim_path(self, path, role, project_id=None, group_id=None, workspace=None, kind="directory", connection=None):
        if not isinstance(path, str) or not Path(path).is_absolute() or not isinstance(role, str) or not role or not isinstance(kind, str) or not kind:
            raise ManagementDBError("소유 경로 정보가 올바르지 않습니다")
        if workspace is not None and (not isinstance(workspace, str) or not Path(workspace).is_absolute()):
            raise ManagementDBError("workspace는 절대 경로여야 합니다")
        now = int(time.time())
        with self._connection(connection, write=True) as connection:
            connection.execute("INSERT INTO management_paths(path,role,project_id,group_id,workspace,kind,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET role=excluded.role,project_id=excluded.project_id,group_id=excluded.group_id,workspace=excluded.workspace,kind=excluded.kind,updated_at=excluded.updated_at WHERE management_paths.role IS NOT excluded.role OR management_paths.project_id IS NOT excluded.project_id OR management_paths.group_id IS NOT excluded.group_id OR management_paths.workspace IS NOT excluded.workspace OR management_paths.kind IS NOT excluded.kind", (path, role, project_id, group_id, workspace, kind, now))

    def paths(self, workspace=None, project_id=None, group_id=None):
        where, values = [], []
        for column, value in (("workspace", workspace), ("project_id", project_id), ("group_id", group_id)):
            if value is not None: where.append(column + "=?"); values.append(value)
        query = "SELECT path,role,project_id,group_id,workspace,kind,updated_at FROM management_paths" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY path"
        with self.transaction() as connection:
            rows = connection.execute(query, values).fetchall() if self._has_table(connection, "management_paths") else []
        return [{"path": row[0], "role": row[1], "projectId": row[2], "groupId": row[3], "workspace": row[4], "kind": row[5], "updatedAt": _iso(row[6])} for row in rows]

    @staticmethod
    def _favorite_time(value):
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    def favorites(self, group_ids=None, connection=None):
        if group_ids is not None and (not isinstance(group_ids, (set, list, tuple)) or any(not isinstance(group_id, str) or len(group_id) > 160 for group_id in group_ids)):
            raise ManagementDBError("좋아요 그룹 ID가 올바르지 않습니다")
        with self._connection(connection) as writer:
            if not self._has_table(writer, "work_favorites"):
                return {}
            if group_ids is None:
                rows = writer.execute("SELECT group_id,liked_at FROM work_favorites").fetchall()
            elif not group_ids:
                rows = []
            else:
                rows = writer.execute("SELECT group_id,liked_at FROM work_favorites WHERE group_id IN (" + ",".join("?" for _ in group_ids) + ")", tuple(group_ids)).fetchall()
        return {group_id: {"favorite": True, "likedAt": self._favorite_time(liked_at), "likedAtMs": liked_at} for group_id, liked_at in rows}

    def set_favorite(self, group_id, favorite, connection=None):
        if not isinstance(group_id, str) or len(group_id) > 160 or type(favorite) is not bool:
            raise ManagementDBError("좋아요 정보가 올바르지 않습니다")
        with self._connection(connection, write=True) as writer:
            previous = writer.execute("SELECT liked_at FROM work_favorites WHERE group_id=?", (group_id,)).fetchone()
            if favorite:
                liked_at = previous[0] if previous else time.time_ns() // 1_000_000
                if previous is None:
                    writer.execute("INSERT INTO work_favorites(group_id,liked_at) VALUES(?,?)", (group_id, liked_at))
                return {"groupId": group_id, "favorite": True, "likedAt": self._favorite_time(liked_at), "likedAtMs": liked_at}
            writer.execute("DELETE FROM work_favorites WHERE group_id=?", (group_id,))
            return {"groupId": group_id, "favorite": False, "likedAt": None, "likedAtMs": None}

    def drop_project(self, project_id, connection=None, *, preserve_production=False):
        if not isinstance(project_id, str) or not project_id or len(project_id) > 160:
            raise ManagementDBError("projectId가 올바르지 않습니다")
        with self._connection(connection, write=True) as connection:
            roots = connection.execute("SELECT path,role,workspace FROM management_paths WHERE project_id=? AND kind='directory' AND role IN ('project','producer-work','producer-metadata')", (project_id,)).fetchall()
            index_files = documents = 0
            for root, role, workspace in roots:
                if root == str(self.data_dir) or (root == workspace and role != 'project'):
                    continue
                index_files += connection.execute("DELETE FROM storage_tracking_files WHERE workspace=?", (root,)).rowcount
                digest = hashlib.sha256(root.encode('utf-8')).hexdigest()
                documents += connection.execute("DELETE FROM management_documents WHERE name IN (?,?)", ('workspace-scan:' + digest, 'workspace-metadata:' + digest)).rowcount
            paths = connection.execute("DELETE FROM management_paths WHERE project_id=?", (project_id,)).rowcount
            events = connection.execute("DELETE FROM management_events WHERE project_id=?", (project_id,)).rowcount
            production = connection.execute("DELETE FROM production_projects WHERE project_id=?", (project_id,)).rowcount if not preserve_production and self._has_table(connection, "production_projects") else 0
        return {"projectId": project_id, "removedPaths": paths, "removedEvents": events, "removedProductionProjects": production, "removedIndexFiles": index_files, "removedDocuments": documents}

    def drop_group(self, group_id, connection=None):
        if not isinstance(group_id, str) or not group_id or len(group_id) > 160:
            raise ManagementDBError("groupId가 올바르지 않습니다")
        with self._connection(connection, write=True) as connection:
            paths = connection.execute("DELETE FROM management_paths WHERE group_id=?", (group_id,)).rowcount
            events = connection.execute("DELETE FROM management_events WHERE group_id=?", (group_id,)).rowcount
            favorites = connection.execute("DELETE FROM work_favorites WHERE group_id=?", (group_id,)).rowcount if self._has_table(connection, "work_favorites") else 0
            production = 0
            if self._has_table(connection, "production_projects"):
                production += connection.execute("DELETE FROM production_projects WHERE group_id=?", (group_id,)).rowcount
                # A project can pre-date group binding; its explicitly grouped records
                # still belong to this group and must not survive group deletion.
                for table in ("production_prompts", "production_tasks", "production_files"):
                    production += connection.execute("DELETE FROM " + table + " WHERE group_id=?", (group_id,)).rowcount
        return {"groupId": group_id, "removedPaths": paths, "removedEvents": events, "removedFavorites": favorites, "removedProductionRows": production}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("record-event", "drop-project", "drop-group"))
    parser.add_argument("--data-dir", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--json")
    source.add_argument("--stdin", action="store_true")
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(MAX_EVENT_BYTES + 1).decode("utf-8") if args.stdin else args.json
        if len(raw.encode("utf-8")) > MAX_EVENT_BYTES: raise ManagementDBError("관리 이력 입력이 안전 한도를 초과했습니다")
        payload = _decode(raw)
        if not isinstance(payload, dict): raise ManagementDBError("JSON 객체가 필요합니다")
        db = ManagementDB(args.data_dir)
        if args.action == "record-event":
            aliases = {"projectId": "project_id", "groupId": "group_id"}
            payload = {aliases.get(key, key): value for key, value in payload.items()}
            with db.transaction(write=True) as connection:
                result = db.record_event(**payload, connection=connection)
                if payload.get('action', '').startswith('song-') and payload.get('path') and payload.get('project_id'):
                    source = Path(os.path.abspath(payload['path']))
                    if hashlib.sha256(str(source).encode()).hexdigest() != payload['project_id'] or source.is_symlink():
                        raise ManagementDBError('음악 작업의 경로와 추적 ID가 일치하지 않습니다')
                    from storage_packaging import TRUSTED_ROOT
                    workspace = str(TRUSTED_ROOT) if TRUSTED_ROOT is not None and source.is_relative_to(TRUSTED_ROOT) else None
                    db.claim_path(str(source), 'music-work', project_id=payload['project_id'], group_id=payload.get('group_id'), workspace=workspace, connection=connection)
        elif args.action == "drop-project":
            result = db.drop_project(payload.get("projectId", payload.get("project_id")))
        else:
            result = db.drop_group(payload.get("groupId", payload.get("group_id")))
        print(json.dumps({"ok": True, **({"event": result} if args.action == "record-event" else {"result": result})}, ensure_ascii=False, allow_nan=False))
        return 0
    except (ManagementDBError, TypeError) as error:
        print(json.dumps({"ok": False, "error": {"message": str(error), "code": "management_db_error"}}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Bounded SQLite ledger for Road Music prompts, production tasks, and measurements.

It deliberately records metadata only: media bytes, frames, and engine logs stay in their
own work directories.  Read methods use ``ManagementDB.transaction()`` so an unopened
profile remains untouched.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time

from management_db import ManagementDB, ManagementDBError


PROJECT_ID = re.compile(r"[0-9a-f]{64}\Z")
PUBLIC_ID = re.compile(r"[0-9a-f]{48}\Z")
DOMAINS = frozenset(("music", "motion"))
RUNNING = frozenset(("queued", "running"))
TERMINAL = frozenset(("success", "failed", "cancelled"))
FILE_ROLES = frozenset(("input", "intermediate", "final", "cache", "artifact"))
COMPONENT_KINDS = frozenset(("app", "cli", "skill"))
REVISION_TASK_TYPES = ("revision", "lyrics", "title", "replace", "restore")
MAX_PROMPT_BYTES = 64 * 1024
MAX_SUMMARY = 4000
MAX_FILES = 10000
MAX_STAGE = 240
PROGRESS_WRITE_INTERVAL_MS = 1000


class ProductionLedgerError(ValueError):
    pass


def _now_ms():
    return time.time_ns() // 1_000_000


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _public_id(value, name):
    if value is None:
        return secrets.token_hex(24)
    if not isinstance(value, str) or not PUBLIC_ID.fullmatch(value):
        raise ProductionLedgerError(f"{name}는 48자리 소문자 16진수여야 합니다")
    return value


def _group_id(value):
    if value is not None and (not isinstance(value, str) or not PROJECT_ID.fullmatch(value)):
        raise ProductionLedgerError("groupId는 64자리 소문자 16진수여야 합니다")
    return value


def _text(value, name, maximum, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > maximum:
        raise ProductionLedgerError(f"{name} 값이 올바르지 않습니다")
    return value


def _number(value, name, integer=False):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (integer and type(value) is not int):
        raise ProductionLedgerError(f"{name} 값이 올바르지 않습니다")
    return value


def _path(value):
    if not isinstance(value, str) or not value:
        raise ProductionLedgerError("project와 파일 path는 절대 경로여야 합니다")
    raw = Path(value)
    if not raw.is_absolute() or raw.is_symlink():
        raise ProductionLedgerError("project와 파일 path는 안전한 절대 경로여야 합니다")
    return str(Path(os.path.abspath(raw)))


def _project_id(path):
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def _cursor(value):
    if value is None:
        return None
    if type(value) is not int or value < 1:
        raise ProductionLedgerError("cursor는 1 이상의 정수여야 합니다")
    return value


def _limit(value):
    if value is None:
        return 30
    if type(value) is not int or not 1 <= value <= 100:
        raise ProductionLedgerError("limit은 1부터 100 사이 정수여야 합니다")
    return value


def _group_ids(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 100:
        raise ProductionLedgerError("groupIds는 1개 이상 100개 이하 배열이어야 합니다")
    if any(not isinstance(item, str) or not PROJECT_ID.fullmatch(item) for item in value):
        raise ProductionLedgerError("groupIds 값이 올바르지 않습니다")
    return list(dict.fromkeys(value))


class ProductionLedger:
    """Metadata-only records, keyed by stable project paths and generated public IDs."""

    def __init__(self, data_dir):
        self.db = ManagementDB(data_dir)

    @staticmethod
    def _table(connection, name):
        return connection is not None and ProductionLedger._has(connection, name)

    @staticmethod
    def _has(connection, name):
        return connection is not None and connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

    @staticmethod
    def _columns(connection, table):
        return {row[1] for row in connection.execute("PRAGMA table_info(" + table + ")")}

    def _task_select(self, connection):
        fields = ("seq", "task_id", "project_id", "group_id", "request_id", "parent_task_id", "domain", "task_type", "engine", "model", "status", "started_at", "finished_at", "elapsed_ms", "media_seconds", "frame_count", "ai_summary", "result_summary", "error_summary", "file_inventory_complete", "file_inventory_warning", "queued_at", "engine_request_id", "expected_media_seconds", "expected_frame_count", "progress", "current_stage", "progress_summary", "progress_updated_at")
        columns = self._columns(connection, "production_tasks")
        return ",".join(field if field in columns else "NULL AS " + field for field in fields)

    def _file_select(self, connection):
        fields = ("seq", "task_id", "project_id", "group_id", "path", "role", "bytes", "mtime_ns", "exists_at_finish", "observed_state", "recorded_at")
        columns = self._columns(connection, "production_files")
        return ",".join(field if field in columns else ("'present' AS observed_state" if field == "observed_state" else "NULL AS " + field) for field in fields)

    @staticmethod
    def _domain(value):
        if value not in DOMAINS:
            raise ProductionLedgerError("domain은 music 또는 motion이어야 합니다")
        return value

    @staticmethod
    def _assert_matching_group(project_group_id, linked_group_id):
        if project_group_id is not None and linked_group_id is not None and project_group_id != linked_group_id:
            raise ProductionLedgerError("다른 음악 그룹에 이미 귀속된 프로젝트입니다. 새 프로젝트를 사용하세요.")

    def _ensure_project(self, connection, params, *, create=True):
        path = _path(params.get("project"))
        domain = self._domain(params.get("domain"))
        group_id = _group_id(params.get("groupId"))
        title = _text(params.get("title", ""), "title", 240) or ""
        project_id = _project_id(path)
        row = connection.execute("SELECT project_id,group_id,path,title,domain,created_at,updated_at FROM production_projects WHERE project_id=?", (project_id,)).fetchone()
        now = _now_ms()
        if row is None:
            if not create:
                raise ProductionLedgerError("먼저 프로젝트 제작 요청을 기록해야 합니다")
            connection.execute("INSERT INTO production_projects(project_id,group_id,path,title,domain,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (project_id, group_id, path, title, domain, now, now))
            return {"projectId": project_id, "groupId": group_id, "path": path, "title": title, "domain": domain, "createdAt": now, "updatedAt": now}
        next_domain = row[4] if row[4] in {domain, "mixed"} else "mixed"
        if row[2] != path:
            raise ProductionLedgerError("projectId와 프로젝트 경로가 일치하지 않습니다")
        self._assert_matching_group(row[1], group_id)
        if row[1] is None and group_id is not None:
            for table in ("production_prompts", "production_tasks", "production_files"):
                conflict = connection.execute("SELECT 1 FROM " + table + " WHERE project_id=? AND group_id IS NOT NULL AND group_id!=? LIMIT 1", (project_id, group_id)).fetchone()
                if conflict is not None:
                    raise ProductionLedgerError("다른 음악 그룹에 이미 귀속된 프로젝트입니다. 새 프로젝트를 사용하세요.")
        next_group = row[1] if row[1] is not None else group_id
        next_title = title or row[3]
        if next_group != row[1] or next_title != row[3] or next_domain != row[4]:
            connection.execute("UPDATE production_projects SET group_id=?,title=?,domain=?,updated_at=? WHERE project_id=?", (next_group, next_title, next_domain, now, project_id))
            if row[1] is None and next_group is not None:
                for table in ("production_prompts", "production_tasks", "production_files"):
                    connection.execute("UPDATE " + table + " SET group_id=? WHERE project_id=? AND group_id IS NULL", (next_group, project_id))
        return {"projectId": project_id, "groupId": next_group, "path": path, "title": next_title, "domain": domain, "createdAt": row[5], "updatedAt": now if (next_group != row[1] or next_title != row[3] or next_domain != row[4]) else row[6]}

    @staticmethod
    def _row_prompt(row):
        return {"seq": row[0], "requestId": row[1], "projectId": row[2], "groupId": row[3], "domain": row[4], "intent": row[5], "prompt": row[6], "source": row[7], "main": bool(row[8]), "requestedAt": _iso(row[9]), "requestedAtMs": row[9]}

    @staticmethod
    def _row_task(row):
        return {"seq": row[0], "taskId": row[1], "projectId": row[2], "groupId": row[3], "requestId": row[4], "engineRequestId": row[22], "parentTaskId": row[5], "domain": row[6], "taskType": row[7], "engine": row[8], "model": row[9], "status": "succeeded" if row[10] == "success" else row[10], "queuedAt": _iso(row[21]) if row[21] is not None else None, "queuedAtMs": row[21], "startedAt": _iso(row[11]), "startedAtMs": row[11], "waitMs": max(0, row[11] - row[21]) if row[21] is not None else None, "finishedAt": _iso(row[12]) if row[12] is not None else None, "finishedAtMs": row[12], "elapsedMs": row[13], "mediaSeconds": row[14], "frameCount": row[15], "expectedMediaSeconds": row[23], "expectedFrameCount": row[24], "progress": row[25], "currentStage": row[26], "progressSummary": row[27], "progressUpdatedAt": _iso(row[28]) if row[28] is not None else None, "progressUpdatedAtMs": row[28], "aiSummary": row[16], "resultSummary": row[17], "errorSummary": row[18], "fileInventoryComplete": bool(row[19]) if row[19] is not None else None, "fileInventoryWarning": row[20]}

    @staticmethod
    def _row_file(row):
        return {"seq": row[0], "taskId": row[1], "projectId": row[2], "groupId": row[3], "path": row[4], "role": row[5], "bytes": row[6], "mtimeNs": row[7], "existsAtFinish": None if row[9] == "unknown" else bool(row[8]), "recordedAt": _iso(row[10]), "recordedAtMs": row[10]}

    @staticmethod
    def _page(rows, limit):
        more = len(rows) > limit
        rows = rows[:limit]
        return rows, (rows[-1]["seq"] if more and rows else None)

    def _attach_task_summaries(self, connection, prompts):
        ids = [item["requestId"] for item in prompts]
        if not ids or not self._has(connection, "production_tasks"):
            for item in prompts: item["taskSummary"] = {"taskCount": 0, "latest": None}
            return
        marks = ",".join("?" for _ in ids)
        engine_link = "SELECT engine_request_id prompt_id,task_id,task_type,status,ai_summary,result_summary,error_summary,finished_at,seq,parent_task_id FROM production_tasks WHERE engine_request_id IN (" + marks + ") AND engine_request_id IS NOT request_id" if "engine_request_id" in self._columns(connection, "production_tasks") else "SELECT NULL prompt_id,NULL task_id,NULL task_type,NULL status,NULL ai_summary,NULL result_summary,NULL error_summary,NULL finished_at,NULL seq,NULL parent_task_id WHERE 0"
        query = """WITH linked AS (
          SELECT request_id prompt_id,task_id,task_type,status,ai_summary,result_summary,error_summary,finished_at,seq,parent_task_id
          FROM production_tasks WHERE request_id IN (""" + marks + ") UNION ALL " + engine_link + "), ranked AS (SELECT *,count(*) OVER (PARTITION BY prompt_id) task_count,row_number() OVER (PARTITION BY prompt_id ORDER BY (status IN ('queued','running')) DESC,(parent_task_id IS NULL) DESC,coalesce(finished_at,0) DESC,seq DESC) rn FROM linked) SELECT prompt_id,task_id,task_type,status,ai_summary,result_summary,error_summary,finished_at,task_count FROM ranked WHERE rn=1"
        rows = {row[0]: row for row in connection.execute(query, (*ids, *ids) if "engine_request_id" in self._columns(connection, "production_tasks") else ids).fetchall()}
        for item in prompts:
            row = rows.get(item["requestId"])
            item["taskSummary"] = {"taskCount": row[8], "latest": {"taskId": row[1], "taskType": row[2], "status": "succeeded" if row[3] == "success" else row[3], "summary": row[5] or row[4] or row[6], "aiSummary": row[4], "resultSummary": row[5], "errorSummary": row[6], "finishedAt": _iso(row[7]) if row[7] is not None else None, "finishedAtMs": row[7]}} if row else {"taskCount": 0, "latest": None}

    def _attach_project_titles(self, connection, prompts):
        project_ids = list(dict.fromkeys(item["projectId"] for item in prompts if item.get("projectId")))
        if not project_ids or not self._has(connection, "production_projects"):
            return
        marks = ",".join("?" for _ in project_ids)
        titles = {row[0]: row[1] or Path(row[2]).name for row in connection.execute("SELECT project_id,title,path FROM production_projects WHERE project_id IN (" + marks + ")", project_ids).fetchall()}
        for item in prompts:
            if title := titles.get(item["projectId"]):
                item["projectTitle"] = title

    def request(self, params):
        if not isinstance(params, dict):
            raise ProductionLedgerError("request는 JSON 객체여야 합니다")
        if set(params) - {"project", "domain", "intent", "prompt", "source", "requestId", "groupId", "title"}:
            raise ProductionLedgerError("지원하지 않는 request 입력입니다")
        intent = _text(params.get("intent", "create"), "intent", 80, required=True)
        prompt = _text(params.get("prompt"), "prompt", MAX_PROMPT_BYTES, required=True)
        if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise ProductionLedgerError("prompt가 64KiB를 초과했습니다")
        source = params.get("source", "user")
        if source not in {"user", "engine"}:
            raise ProductionLedgerError("source는 user 또는 engine이어야 합니다")
        request_id = _public_id(params.get("requestId"), "requestId")
        with self.db.transaction(write=True) as connection:
            project = self._ensure_project(connection, params)
            row = connection.execute("SELECT seq,request_id,project_id,group_id,domain,intent,prompt,source,is_main,requested_at FROM production_prompts WHERE request_id=?", (request_id,)).fetchone()
            if row is not None:
                item = self._row_prompt(row)
                self._assert_matching_group(project["groupId"], item["groupId"])
                expected = {"projectId": project["projectId"], "domain": project["domain"], "intent": intent, "prompt": prompt, "source": source}
                if any(item[key] != value for key, value in expected.items()):
                    raise ProductionLedgerError("같은 requestId에 다른 요청을 기록할 수 없습니다")
                return item
            revision_intent = intent.lower() in {"revision", "revise", "lyrics", "title", "replace", "restore", "review", "verification", "update", "edit"}
            is_main = int(source == "user" and not revision_intent and connection.execute("SELECT 1 FROM production_prompts WHERE project_id=? AND domain=? AND is_main=1", (project["projectId"], project["domain"])).fetchone() is None)
            now = _now_ms()
            cursor = connection.execute("INSERT INTO production_prompts(request_id,project_id,group_id,domain,intent,prompt,source,is_main,requested_at) VALUES(?,?,?,?,?,?,?,?,?)", (request_id, project["projectId"], project["groupId"], project["domain"], intent, prompt, source, is_main, now))
            return {"seq": cursor.lastrowid, "requestId": request_id, "projectId": project["projectId"], "groupId": project["groupId"], "domain": project["domain"], "intent": intent, "prompt": prompt, "source": source, "main": bool(is_main), "requestedAt": _iso(now), "requestedAtMs": now}

    def start_task(self, params):
        if not isinstance(params, dict):
            raise ProductionLedgerError("task-start는 JSON 객체여야 합니다")
        if set(params) - {"project", "domain", "taskType", "engine", "model", "requestId", "engineRequestId", "taskId", "parentTaskId", "groupId", "title", "status", "expectedMediaSeconds", "expectedFrameCount"}:
            raise ProductionLedgerError("지원하지 않는 task-start 입력입니다")
        task_type = _text(params.get("taskType"), "taskType", 80, required=True)
        task_id = _public_id(params.get("taskId"), "taskId")
        status = params.get("status", "running")
        if status not in RUNNING:
            raise ProductionLedgerError("작업 시작 상태는 queued 또는 running이어야 합니다")
        engine, model = _text(params.get("engine"), "engine", 120), _text(params.get("model"), "model", 120)
        parent_id = params.get("parentTaskId")
        if parent_id is not None: _public_id(parent_id, "parentTaskId")
        request_id = params.get("requestId")
        if request_id is not None: _public_id(request_id, "requestId")
        engine_request_id = params.get("engineRequestId")
        if engine_request_id is not None: _public_id(engine_request_id, "engineRequestId")
        expected_media_seconds = _number(params.get("expectedMediaSeconds"), "expectedMediaSeconds")
        expected_frame_count = _number(params.get("expectedFrameCount"), "expectedFrameCount", integer=True)
        with self.db.transaction(write=True) as connection:
            project = self._ensure_project(connection, params)
            if request_id is None:
                item = connection.execute("SELECT request_id,group_id FROM production_prompts WHERE project_id=? AND domain=? AND source='user' ORDER BY seq DESC LIMIT 1", (project["projectId"], project["domain"])).fetchone()
                request_id, request_group_id = item if item else (None, None)
            elif (item := connection.execute("SELECT group_id FROM production_prompts WHERE request_id=? AND project_id=? AND domain=?", (request_id, project["projectId"], project["domain"])).fetchone()) is None:
                raise ProductionLedgerError("requestId가 같은 프로젝트의 요청이 아닙니다")
            else:
                request_group_id = item[0]
            if request_id is not None:
                self._assert_matching_group(project["groupId"], request_group_id)
            if engine_request_id is not None:
                item = connection.execute("SELECT group_id FROM production_prompts WHERE request_id=? AND project_id=? AND domain=? AND source='engine'", (engine_request_id, project["projectId"], project["domain"])).fetchone()
                if item is None:
                    raise ProductionLedgerError("engineRequestId가 같은 프로젝트의 엔진 입력이 아닙니다")
                self._assert_matching_group(project["groupId"], item[0])
            if parent_id is not None:
                item = connection.execute("SELECT group_id FROM production_tasks WHERE task_id=? AND project_id=?", (parent_id, project["projectId"])).fetchone()
                if item is None:
                    raise ProductionLedgerError("parentTaskId가 같은 프로젝트의 작업이 아닙니다")
                self._assert_matching_group(project["groupId"], item[0])
            row = connection.execute("SELECT " + self._task_select(connection) + " FROM production_tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is not None:
                item = self._row_task(row)
                self._assert_matching_group(project["groupId"], item["groupId"])
                immutable = {"projectId": project["projectId"], "domain": project["domain"], "taskType": task_type, "engine": engine, "model": model, "requestId": request_id, "engineRequestId": engine_request_id, "parentTaskId": parent_id}
                if any(item[key] != value for key, value in immutable.items()):
                    raise ProductionLedgerError("같은 taskId에 다른 작업을 기록할 수 없습니다")
                for key, value, column in (("expectedMediaSeconds", expected_media_seconds, "expected_media_seconds"), ("expectedFrameCount", expected_frame_count, "expected_frame_count")):
                    if value is None:
                        continue
                    if item[key] is not None and item[key] != value:
                        raise ProductionLedgerError("같은 taskId의 예상 작업량을 바꿀 수 없습니다")
                    if item[key] is None:
                        connection.execute("UPDATE production_tasks SET " + column + "=? WHERE task_id=?", (value, task_id))
                        item[key] = value
                if item["status"] == "queued" and status == "running":
                    now = _now_ms(); connection.execute("UPDATE production_tasks SET status=?,started_at=? WHERE task_id=?", ("running", now, task_id)); item.update({"status": "running", "startedAt": _iso(now), "startedAtMs": now})
                elif item["status"] not in RUNNING or (item["status"] == "running" and status == "queued"):
                    raise ProductionLedgerError("종료된 작업을 다시 시작할 수 없습니다")
                return item
            now = _now_ms()
            cursor = connection.execute("INSERT INTO production_tasks(task_id,project_id,group_id,request_id,engine_request_id,parent_task_id,domain,task_type,engine,model,status,queued_at,started_at,expected_media_seconds,expected_frame_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (task_id, project["projectId"], project["groupId"], request_id, engine_request_id, parent_id, project["domain"], task_type, engine, model, status, now, now, expected_media_seconds, expected_frame_count))
            return {"seq": cursor.lastrowid, "taskId": task_id, "projectId": project["projectId"], "groupId": project["groupId"], "requestId": request_id, "engineRequestId": engine_request_id, "parentTaskId": parent_id, "domain": project["domain"], "taskType": task_type, "engine": engine, "model": model, "status": status, "queuedAt": _iso(now), "queuedAtMs": now, "startedAt": _iso(now), "startedAtMs": now, "waitMs": 0, "finishedAt": None, "finishedAtMs": None, "elapsedMs": None, "mediaSeconds": None, "frameCount": None, "aiSummary": None, "resultSummary": None, "errorSummary": None, "fileInventoryComplete": None, "fileInventoryWarning": None, "expectedMediaSeconds": expected_media_seconds, "expectedFrameCount": expected_frame_count, "progress": None, "currentStage": None, "progressSummary": None, "progressUpdatedAt": None, "progressUpdatedAtMs": None}

    def _files(self, task, values):
        if values is None: return []
        if not isinstance(values, list) or len(values) > MAX_FILES:
            raise ProductionLedgerError("files가 안전 한도를 초과했거나 배열이 아닙니다")
        result = []
        for value in values:
            if not isinstance(value, dict) or set(value) != {"path", "role"} or value["role"] not in FILE_ROLES:
                raise ProductionLedgerError("files 항목은 절대 path와 허용 role이 필요합니다")
            path = _path(value["path"])
            raw = Path(path)
            if raw.exists() and raw.is_symlink():
                raise ProductionLedgerError("symlink 파일은 제작 이력에 기록하지 않습니다")
            try:
                stat = raw.stat(follow_symlinks=False)
                exists = raw.is_file()
            except OSError:
                stat, exists = None, False
            result.append({"taskId": task["taskId"], "projectId": task["projectId"], "groupId": task["groupId"], "path": path, "role": value["role"], "bytes": stat.st_size if exists else None, "mtimeNs": stat.st_mtime_ns if exists else None, "existsAtFinish": exists if exists else None})
        return result

    def _record_files(self, connection, task, values, inventory_complete=None, warning=None):
        files = self._files(task, values)
        if inventory_complete is not None and type(inventory_complete) is not bool:
            raise ProductionLedgerError("fileInventoryComplete은 boolean이어야 합니다")
        warning = _text(warning, "fileInventoryWarning", MAX_SUMMARY)
        now = _now_ms()
        for item in files:
            state = "present" if item["existsAtFinish"] else "unknown"
            connection.execute("INSERT INTO production_files(task_id,project_id,group_id,path,role,bytes,mtime_ns,exists_at_finish,observed_state,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(task_id,path,role) DO UPDATE SET bytes=CASE WHEN excluded.observed_state='unknown' THEN production_files.bytes ELSE excluded.bytes END,mtime_ns=CASE WHEN excluded.observed_state='unknown' THEN production_files.mtime_ns ELSE excluded.mtime_ns END,exists_at_finish=CASE WHEN excluded.observed_state='unknown' THEN production_files.exists_at_finish ELSE excluded.exists_at_finish END,observed_state=excluded.observed_state,recorded_at=excluded.recorded_at", (item["taskId"], item["projectId"], item["groupId"], item["path"], item["role"], item["bytes"], item["mtimeNs"], int(bool(item["existsAtFinish"])), state, now))
        if inventory_complete is not None or warning is not None:
            connection.execute("UPDATE production_tasks SET file_inventory_complete=?,file_inventory_warning=? WHERE task_id=?", (int(inventory_complete) if inventory_complete is not None else task["fileInventoryComplete"], warning if warning is not None else task["fileInventoryWarning"], task["taskId"]))
            task.update({"fileInventoryComplete": inventory_complete if inventory_complete is not None else task["fileInventoryComplete"], "fileInventoryWarning": warning if warning is not None else task["fileInventoryWarning"]})
        for item in files:
            item.update({"recordedAt": _iso(now), "recordedAtMs": now})
        return files

    def record_files(self, params):
        if not isinstance(params, dict) or set(params) - {"taskId", "files", "fileInventoryComplete", "fileInventoryWarning"} or "taskId" not in params or "files" not in params:
            raise ProductionLedgerError("files-record에는 taskId와 files만 기록할 수 있습니다")
        task_id = _public_id(params.get("taskId"), "taskId")
        with self.db.transaction(write=True) as connection:
            row = connection.execute("SELECT " + self._task_select(connection) + " FROM production_tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None: raise ProductionLedgerError("파일을 기록할 taskId를 찾을 수 없습니다")
            task = self._row_task(row)
            files = self._record_files(connection, task, params["files"], params.get("fileInventoryComplete"), params.get("fileInventoryWarning"))
            return {"taskId": task_id, "projectId": task["projectId"], "files": files, "fileInventoryComplete": task["fileInventoryComplete"], "fileInventoryWarning": task["fileInventoryWarning"]}

    def progress_task(self, params):
        if not isinstance(params, dict) or set(params) - {"taskId", "progress", "currentStage", "summary"} or "taskId" not in params:
            raise ProductionLedgerError("task-progress에는 taskId와 진행 값만 기록할 수 있습니다")
        task_id = _public_id(params.get("taskId"), "taskId")
        progress = _number(params.get("progress"), "progress")
        if progress is not None and progress > 1:
            raise ProductionLedgerError("progress는 0부터 1 사이여야 합니다")
        stage = _text(params.get("currentStage"), "currentStage", MAX_STAGE)
        summary = _text(params.get("summary"), "summary", MAX_SUMMARY)
        if progress is None and stage is None and summary is None:
            raise ProductionLedgerError("진행률 또는 현재 단계가 필요합니다")
        with self.db.transaction(write=True) as connection:
            row = connection.execute("SELECT " + self._task_select(connection) + " FROM production_tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                raise ProductionLedgerError("진행률을 기록할 taskId를 찾을 수 없습니다")
            task = self._row_task(row)
            if task["status"] not in RUNNING:
                raise ProductionLedgerError("종료된 작업의 진행률은 바꿀 수 없습니다")
            next_progress = progress if progress is not None else task["progress"]
            if next_progress is not None and task["progress"] is not None and next_progress < task["progress"]:
                raise ProductionLedgerError("진행률은 뒤로 갈 수 없습니다")
            now = _now_ms()
            next_stage = stage if stage is not None else task["currentStage"]
            next_summary = summary if summary is not None else task["progressSummary"]
            if (next_progress, next_stage, next_summary) == (task["progress"], task["currentStage"], task["progressSummary"]):
                return task
            if task["progressUpdatedAtMs"] is not None and now - task["progressUpdatedAtMs"] < PROGRESS_WRITE_INTERVAL_MS and next_stage == task["currentStage"] and next_progress != 1:
                return task
            connection.execute("UPDATE production_tasks SET progress=?,current_stage=?,progress_summary=?,progress_updated_at=? WHERE task_id=?", (next_progress, next_stage, next_summary, now, task_id))
            task.update({"progress": next_progress, "currentStage": next_stage, "progressSummary": next_summary, "progressUpdatedAt": _iso(now), "progressUpdatedAtMs": now})
            return task

    def finish_task(self, params):
        if not isinstance(params, dict):
            raise ProductionLedgerError("task-finish는 JSON 객체여야 합니다")
        if set(params) - {"taskId", "status", "elapsedMs", "mediaSeconds", "frameCount", "aiSummary", "resultSummary", "errorSummary", "files", "fileInventoryComplete", "fileInventoryWarning"}:
            raise ProductionLedgerError("지원하지 않는 task-finish 입력입니다")
        task_id = _public_id(params.get("taskId"), "taskId")
        status = params.get("status")
        if status == "succeeded": status = "success"
        if status not in TERMINAL:
            raise ProductionLedgerError("작업 완료 상태는 success, failed 또는 cancelled여야 합니다")
        metrics = {"elapsedMs": _number(params.get("elapsedMs"), "elapsedMs"), "mediaSeconds": _number(params.get("mediaSeconds"), "mediaSeconds"), "frameCount": _number(params.get("frameCount"), "frameCount", integer=True)}
        summaries = {"aiSummary": _text(params.get("aiSummary"), "aiSummary", MAX_SUMMARY), "resultSummary": _text(params.get("resultSummary"), "resultSummary", MAX_SUMMARY), "errorSummary": _text(params.get("errorSummary"), "errorSummary", MAX_SUMMARY)}
        with self.db.transaction(write=True) as connection:
            row = connection.execute("SELECT " + self._task_select(connection) + " FROM production_tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None: raise ProductionLedgerError("종료할 taskId를 찾을 수 없습니다")
            task = self._row_task(row); files = self._files(task, params.get("files"))
            internal_status = "success" if task["status"] == "succeeded" else task["status"]
            if internal_status in TERMINAL:
                if internal_status != status: raise ProductionLedgerError("종료된 작업의 상태를 바꿀 수 없습니다")
                for key, value in {**metrics, **summaries}.items():
                    if value is not None and task[key] != value: raise ProductionLedgerError("종료된 작업의 결과를 바꿀 수 없습니다")
                if "files" in params:
                    old = connection.execute("SELECT task_id,project_id,group_id,path,role,bytes,mtime_ns,exists_at_finish,observed_state FROM production_files WHERE task_id=? ORDER BY seq", (task_id,)).fetchall()
                    actual = [(item["taskId"], item["projectId"], item["groupId"], item["path"], item["role"], item["bytes"], item["mtimeNs"], int(bool(item["existsAtFinish"])), "present" if item["existsAtFinish"] else "unknown") for item in files]
                    if list(old) != actual: raise ProductionLedgerError("종료된 작업의 파일 이력을 바꿀 수 없습니다")
                return task | {"files": files}
            now = _now_ms()
            connection.execute("UPDATE production_tasks SET status=?,finished_at=?,elapsed_ms=?,media_seconds=?,frame_count=?,ai_summary=?,result_summary=?,error_summary=?,progress=?,progress_updated_at=? WHERE task_id=?", (status, now, metrics["elapsedMs"], metrics["mediaSeconds"], metrics["frameCount"], summaries["aiSummary"], summaries["resultSummary"], summaries["errorSummary"], 1.0 if status == "success" else task["progress"], now, task_id))
            if "files" in params or "fileInventoryComplete" in params or "fileInventoryWarning" in params:
                files = self._record_files(connection, task, params.get("files", []), params.get("fileInventoryComplete"), params.get("fileInventoryWarning"))
            task.update({"status": "succeeded" if status == "success" else status, "finishedAt": _iso(now), "finishedAtMs": now, "progress": 1.0 if status == "success" else task["progress"], "progressUpdatedAt": _iso(now), "progressUpdatedAtMs": now, **metrics, **summaries})
            return task | {"files": files}

    def _filters(self, params, *, projects=False, group_ids=False):
        if not isinstance(params, dict): raise ProductionLedgerError("조회 조건은 JSON 객체여야 합니다")
        limit, cursor = _limit(params.get("limit")), _cursor(params.get("cursor"))
        allowed = {"projectId", "groupId", "domain", "engine", "model", "taskType", "status", "search", "since", "until", "limit", "cursor", "taskId"}
        if group_ids: allowed.add("groupIds")
        unknown = set(params) - allowed
        if unknown: raise ProductionLedgerError("지원하지 않는 조회 조건입니다")
        if params.get("groupId") is not None and params.get("groupIds") is not None:
            raise ProductionLedgerError("groupId와 groupIds를 함께 사용할 수 없습니다")
        where, values = [], []
        for column, key, pattern in (("project_id", "projectId", PROJECT_ID), ("group_id", "groupId", PROJECT_ID), ("domain", "domain", None), ("engine", "engine", None), ("model", "model", None), ("task_type", "taskType", None), ("status", "status", None)):
            value = params.get(key)
            if value is None: continue
            if key == "status" and value == "succeeded": value = "success"
            if not isinstance(value, str) or (pattern is not None and not pattern.fullmatch(value)) or (key == "domain" and value not in DOMAINS) or (key == "status" and value not in RUNNING | TERMINAL) or len(value) > 120:
                raise ProductionLedgerError(f"{key} 조회 조건이 올바르지 않습니다")
            where.append(column + "=?"); values.append(value)
        if params.get("groupIds") is not None:
            groups = _group_ids(params["groupIds"])
            where.append("group_id IN (" + ",".join("?" for _ in groups) + ")"); values.extend(groups)
        for key, op in (("since", ">="), ("until", "<=")):
            value = params.get(key)
            if value is not None:
                if type(value) is not int or value < 0: raise ProductionLedgerError(f"{key} 조회 조건이 올바르지 않습니다")
                where.append("finished_at" + op + "?"); values.append(value)
        if params.get("taskId") is not None:
            where.append("task_id=?"); values.append(_public_id(params["taskId"], "taskId"))
        search = params.get("search")
        if search is not None:
            if not projects or not isinstance(search, str) or len(search) > 200: raise ProductionLedgerError("search 조회 조건이 올바르지 않습니다")
        return where, values, limit, cursor, search

    def prompts(self, params=None):
        params = params or {}; where, values, limit, cursor, _ = self._filters(params)
        unsupported = set(params) & {"engine", "model", "taskType", "status", "taskId"}
        if unsupported: raise ProductionLedgerError("prompt 조회에는 프로젝트·그룹·영역·기간 조건만 사용할 수 있습니다")
        where = [item.replace("finished_at", "requested_at") for item in where]
        base_where, base_values = list(where), list(values)
        if cursor is not None: where.append("seq<?"); values.append(cursor)
        query = "SELECT seq,request_id,project_id,group_id,domain,intent,prompt,source,is_main,requested_at FROM production_prompts" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY seq DESC LIMIT ?"
        with self.db.transaction() as connection:
            rows = [self._row_prompt(row) for row in connection.execute(query, (*values, limit + 1)).fetchall()] if self._has(connection, "production_prompts") else []
            base = " WHERE " + " AND ".join(base_where) if base_where else ""
            counts_row = connection.execute("SELECT sum(CASE WHEN source='user' THEN 1 ELSE 0 END),sum(CASE WHEN source='engine' THEN 1 ELSE 0 END),sum(CASE WHEN source='user' AND (lower(intent) LIKE '%revis%' OR lower(intent) LIKE '%lyrics%' OR lower(intent) LIKE '%title%' OR lower(intent) LIKE '%video%' OR lower(intent) LIKE '%수정%' OR lower(intent) LIKE '%가사%' OR lower(intent) LIKE '%제목%' OR lower(intent) LIKE '%영상%') THEN 1 ELSE 0 END) FROM production_prompts" + base, base_values).fetchone() if self._has(connection, "production_prompts") else (0, 0, 0)
            main = [self._row_prompt(row) for row in connection.execute("SELECT seq,request_id,project_id,group_id,domain,intent,prompt,source,is_main,requested_at FROM production_prompts" + base + (" AND " if base else " WHERE ") + "is_main=1 ORDER BY seq DESC LIMIT 20", base_values).fetchall()] if self._has(connection, "production_prompts") else []
            task_where = [item.replace("requested_at", "finished_at") for item in base_where]
            task_base = " WHERE " + " AND ".join(task_where) if task_where else ""
            generations = connection.execute("SELECT count(*) FROM production_tasks" + task_base + (" AND " if task_base else " WHERE ") + "parent_task_id IS NULL AND status='success' AND lower(task_type) IN ('generation','generate','render')", base_values).fetchone()[0] if self._has(connection, "production_tasks") else 0
            revisions = connection.execute("SELECT count(*) FROM production_tasks" + task_base + (" AND " if task_base else " WHERE ") + "parent_task_id IS NULL AND status='success' AND lower(task_type) IN ('revision','lyrics','title','replace','restore')", base_values).fetchone()[0] if self._has(connection, "production_tasks") else 0
            self._attach_task_summaries(connection, rows)
            self._attach_task_summaries(connection, main)
            self._attach_project_titles(connection, rows + main)
        rows, next_cursor = self._page(rows, limit)
        return {"prompts": rows, "mainPrompts": main, "counts": {"requests": counts_row[0] or 0, "enginePrompts": counts_row[1] or 0, "requestedRevisions": counts_row[2] or 0, "revisions": revisions, "generations": generations}, "nextCursor": next_cursor}

    def tasks(self, params=None):
        params = params or {}; where, values, limit, cursor, _ = self._filters(params)
        if cursor is not None: where.append("seq<?"); values.append(cursor)
        with self.db.transaction() as connection:
            if self._has(connection, "production_tasks"):
                query = "SELECT " + self._task_select(connection) + " FROM production_tasks" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY seq DESC LIMIT ?"
                rows = [self._row_task(row) for row in connection.execute(query, (*values, limit + 1)).fetchall()]
            else: rows = []
        rows, next_cursor = self._page(rows, limit)
        return {"tasks": rows, "nextCursor": next_cursor}

    def files(self, params=None):
        params = params or {}; where, values, limit, cursor, _ = self._filters(params)
        unsupported = set(params) & {"domain", "engine", "model", "taskType", "status", "since", "until"}
        if unsupported: raise ProductionLedgerError("파일 조회에는 프로젝트·그룹·taskId 조건만 사용할 수 있습니다")
        if cursor is not None: where.append("seq<?"); values.append(cursor)
        with self.db.transaction() as connection:
            if self._has(connection, "production_files"):
                query = "SELECT " + self._file_select(connection) + " FROM production_files" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY seq DESC LIMIT ?"
                rows = [self._row_file(row) for row in connection.execute(query, (*values, limit + 1)).fetchall()]
            else: rows = []
        rows, next_cursor = self._page(rows, limit)
        return {"files": rows, "nextCursor": next_cursor}

    @staticmethod
    def _empty_performance():
        def section():
            return {"totalElapsedMs": None, "avgElapsedMs": None, "measuredTaskCount": 0, "missingElapsedCount": 0, "succeededCount": 0, "failedCount": 0, "cancelledCount": 0, "runningCount": 0, "mediaSeconds": None, "realtimeFactor": None, "_successElapsedMs": None, "_successMeasuredCount": 0, "_realtimeElapsedMs": None, "_realtimeMediaSeconds": None}
        result = section()
        result["music"], result["motion"] = section(), section()
        return result

    @staticmethod
    def _sum_measurements(values):
        known = [value for value in values if value is not None]
        return sum(known) if known else None

    def _performance_rows(self, connection, where, values, *, key_column):
        conditions = list(where) + ["parent_task_id IS NULL"]
        clause = " WHERE " + " AND ".join(conditions)
        query = """SELECT """ + key_column + """,domain,
          sum(CASE WHEN status IN ('success','failed','cancelled') THEN elapsed_ms END),
          sum(CASE WHEN status='success' THEN elapsed_ms END),
          sum(CASE WHEN status='success' AND elapsed_ms IS NOT NULL THEN 1 ELSE 0 END),
          sum(CASE WHEN status IN ('success','failed','cancelled') AND elapsed_ms IS NOT NULL THEN 1 ELSE 0 END),
          sum(CASE WHEN status IN ('success','failed','cancelled') AND elapsed_ms IS NULL THEN 1 ELSE 0 END),
          sum(CASE WHEN status='success' THEN 1 ELSE 0 END),
          sum(CASE WHEN status='failed' THEN 1 ELSE 0 END),
          sum(CASE WHEN status='cancelled' THEN 1 ELSE 0 END),
          sum(CASE WHEN status IN ('queued','running') THEN 1 ELSE 0 END),
          sum(CASE WHEN status='success' THEN media_seconds END),
          sum(CASE WHEN status='success' AND elapsed_ms IS NOT NULL AND media_seconds>0 THEN elapsed_ms END),
          sum(CASE WHEN status='success' AND elapsed_ms IS NOT NULL AND media_seconds>0 THEN media_seconds END)
          FROM production_tasks""" + clause + " GROUP BY " + key_column + ",domain"
        return connection.execute(query, values).fetchall()

    def _performance_by_key(self, connection, keys, where, values, *, key_column):
        result = {key: self._empty_performance() for key in keys}
        if not keys or not self._has(connection, "production_tasks"):
            return {key: self._public_performance(value) for key, value in result.items()}
        key_where = key_column + " IN (" + ",".join("?" for _ in keys) + ")"
        rows = self._performance_rows(connection, [key_where, *where], [*keys, *values], key_column=key_column)
        for row in rows:
            key, domain = row[0], row[1]
            item = result.get(key)
            if item is None or domain not in DOMAINS:
                continue
            target = item[domain]
            target.update({"totalElapsedMs": row[2], "avgElapsedMs": row[3] / row[4] if row[4] else None, "measuredTaskCount": row[5] or 0, "missingElapsedCount": row[6] or 0, "succeededCount": row[7] or 0, "failedCount": row[8] or 0, "cancelledCount": row[9] or 0, "runningCount": row[10] or 0, "mediaSeconds": row[11], "realtimeFactor": row[12] / (row[13] * 1000.0) if row[13] else None, "_successElapsedMs": row[3], "_successMeasuredCount": row[4] or 0, "_realtimeElapsedMs": row[12], "_realtimeMediaSeconds": row[13]})
        for item in result.values():
            domains = [item[domain] for domain in DOMAINS]
            item.update({
                "totalElapsedMs": self._sum_measurements([entry["totalElapsedMs"] for entry in domains]),
                "measuredTaskCount": sum(entry["measuredTaskCount"] for entry in domains),
                "missingElapsedCount": sum(entry["missingElapsedCount"] for entry in domains),
                "succeededCount": sum(entry["succeededCount"] for entry in domains),
                "failedCount": sum(entry["failedCount"] for entry in domains),
                "cancelledCount": sum(entry["cancelledCount"] for entry in domains),
                "runningCount": sum(entry["runningCount"] for entry in domains),
                "mediaSeconds": self._sum_measurements([entry["mediaSeconds"] for entry in domains]),
                "_successElapsedMs": self._sum_measurements([entry["_successElapsedMs"] for entry in domains]),
                "_successMeasuredCount": sum(entry["_successMeasuredCount"] for entry in domains),
                "_realtimeElapsedMs": self._sum_measurements([entry["_realtimeElapsedMs"] for entry in domains]),
                "_realtimeMediaSeconds": self._sum_measurements([entry["_realtimeMediaSeconds"] for entry in domains]),
            })
            item["avgElapsedMs"] = item["_successElapsedMs"] / item["_successMeasuredCount"] if item["_successMeasuredCount"] else None
            item["realtimeFactor"] = item["_realtimeElapsedMs"] / (item["_realtimeMediaSeconds"] * 1000.0) if item["_realtimeMediaSeconds"] else None
        return {key: self._public_performance(value) for key, value in result.items()}

    @staticmethod
    def _public_performance(value):
        return {key: ({child_key: child_value for child_key, child_value in child_value.items() if not child_key.startswith("_")} if key in DOMAINS else child_value) for key, child_value in value.items() if not key.startswith("_")}

    def group_summaries(self, group_ids, params=None):
        params = {**(params or {}), "groupIds": group_ids}
        where, values, _, cursor, _ = self._filters(params, group_ids=True)
        if cursor is not None:
            raise ProductionLedgerError("그룹 성능 요약은 cursor를 지원하지 않습니다")
        ids = _group_ids(group_ids)
        with self.db.transaction() as connection:
            performance = {} if connection is None else self._performance_by_key(connection, ids, where, values, key_column="group_id")
        return [{"groupId": group_id, "performance": performance.get(group_id, self._public_performance(self._empty_performance()))} for group_id in ids]

    def _stage_breakdown(self, connection, where, values):
        if not self._has(connection, "production_tasks"):
            return []
        rows = self._performance_rows(connection, where, values, key_column="task_type")
        return [{"taskType": row[0], "domain": row[1], "elapsedMs": row[2], "measuredTaskCount": row[5] or 0, "missingElapsedCount": row[6] or 0, "succeededCount": row[7] or 0, "failedCount": row[8] or 0, "cancelledCount": row[9] or 0, "runningCount": row[10] or 0} for row in rows]

    def projects(self, params=None):
        params = params or {}; where, values, limit, cursor, search = self._filters(params, projects=True)
        translated, translated_values, task_conditions, task_values = [], [], [], []
        for item, value in zip(where, values):
            if item.startswith("project_id") or item.startswith("group_id"):
                translated.append("p." + item); translated_values.append(value)
            elif item.startswith("domain"):
                translated.append("(EXISTS (SELECT 1 FROM production_prompts q WHERE q.project_id=p.project_id AND q.domain=?) OR EXISTS (SELECT 1 FROM production_tasks t WHERE t.project_id=p.project_id AND t.domain=?))")
                translated_values.extend((value, value))
            else:
                task_conditions.append("t." + item); task_values.append(value)
        if task_conditions:
            translated.append("EXISTS (SELECT 1 FROM production_tasks t WHERE t.project_id=p.project_id AND " + " AND ".join(task_conditions) + ")")
            translated_values.extend(task_values)
        if search is not None:
            translated.append("(p.title LIKE ? ESCAPE '\\' OR p.path LIKE ? ESCAPE '\\')"); escaped = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"; translated_values.extend((escaped, escaped))
        if cursor is not None: translated.append("p.rowid<?"); translated_values.append(cursor)
        sql = """SELECT p.rowid,p.project_id,p.group_id,p.path,p.title,p.domain,p.created_at,p.updated_at,
          (SELECT count(*) FROM production_prompts q WHERE q.project_id=p.project_id AND q.source='user') request_count,
          (SELECT count(*) FROM production_tasks t WHERE t.project_id=p.project_id AND t.status='success' AND t.parent_task_id IS NULL AND lower(t.task_type) IN ('generation','generate','render')) generation_count,
          (SELECT count(*) FROM production_tasks t WHERE t.project_id=p.project_id AND t.parent_task_id IS NULL AND t.status='success' AND lower(t.task_type) IN ('revision','lyrics','title','replace','restore')) revision_count,
          (SELECT count(*) FROM production_prompts q WHERE q.project_id=p.project_id AND q.source='user' AND (lower(q.intent) LIKE '%revis%' OR lower(q.intent) LIKE '%lyrics%' OR lower(q.intent) LIKE '%title%' OR lower(q.intent) LIKE '%video%' OR lower(q.intent) LIKE '%수정%' OR lower(q.intent) LIKE '%가사%' OR lower(q.intent) LIKE '%제목%' OR lower(q.intent) LIKE '%영상%')) requested_revision_count,
          (SELECT count(*) FROM production_tasks t WHERE t.project_id=p.project_id) task_count,
          (SELECT count(*) FROM production_tasks t WHERE t.project_id=p.project_id AND t.parent_task_id IS NULL AND t.status='success') succeeded_count,
          (SELECT count(*) FROM production_tasks t WHERE t.project_id=p.project_id AND t.parent_task_id IS NULL AND t.status='failed') failed_count,
          (SELECT sum(t.elapsed_ms) FROM production_tasks t WHERE t.project_id=p.project_id AND t.parent_task_id IS NULL AND t.status='success') total_elapsed_ms,
          (SELECT avg(t.elapsed_ms) FROM production_tasks t WHERE t.project_id=p.project_id AND t.parent_task_id IS NULL AND t.status='success') avg_elapsed_ms,
          (SELECT sum(bytes) FROM (SELECT path,max(bytes) bytes FROM production_files f WHERE f.project_id=p.project_id AND f.role!='input' AND f.exists_at_finish=1 GROUP BY path)) output_bytes
          FROM production_projects p""" + (" WHERE " + " AND ".join(translated) if translated else "") + " ORDER BY p.rowid DESC LIMIT ?"
        with self.db.transaction() as connection:
            rows = [] if connection is None or not self._has(connection, "production_projects") else [{"seq": row[0], "projectId": row[1], "groupId": row[2], "path": row[3], "title": row[4], "domain": row[5], "createdAt": _iso(row[6]), "createdAtMs": row[6], "updatedAt": _iso(row[7]), "updatedAtMs": row[7], "requestCount": row[8], "generationCount": row[9], "revisionCount": row[10], "requestedRevisionCount": row[11], "taskCount": row[12], "succeededCount": row[13], "failedCount": row[14], "totalElapsedMs": row[15], "avgElapsedMs": row[16], "outputBytes": row[17]} for row in connection.execute(sql, (*translated_values, limit + 1)).fetchall()]
            performance = self._performance_by_key(connection, [row["projectId"] for row in rows], where, values, key_column="project_id") if connection is not None else {}
            for row in rows:
                row["performance"] = performance.get(row["projectId"], self._public_performance(self._empty_performance()))
        rows, next_cursor = self._page(rows, limit)
        return {"projects": rows, "nextCursor": next_cursor}

    def components(self, params=None):
        params = params or {}; limit = _limit(params.get("limit")); cursor = _cursor(params.get("cursor"))
        if set(params) - {"limit", "cursor"}: raise ProductionLedgerError("지원하지 않는 component 조회 조건입니다")
        with self.db.transaction() as connection:
            if not self._has(connection, "production_components"): rows = []
            else:
                query = "SELECT rowid,component_id,kind,name,installed_version,latest_version,check_status,checked_at,source_url FROM production_components" + (" WHERE rowid<?" if cursor else "") + " ORDER BY rowid DESC LIMIT ?"
                values = ((cursor, limit + 1) if cursor else (limit + 1,))
                rows = [{"seq": row[0], "componentId": row[1], "kind": row[2], "name": row[3], "installedVersion": row[4], "latestVersion": row[5], "checkStatus": row[6], "checkedAt": _iso(row[7]), "checkedAtMs": row[7], "sourceUrl": row[8]} for row in connection.execute(query, values).fetchall()]
        rows, next_cursor = self._page(rows, limit)
        return {"components": rows, "nextCursor": next_cursor}

    def record_component(self, params):
        if not isinstance(params, dict): raise ProductionLedgerError("component-record는 JSON 객체여야 합니다")
        if set(params) - {"componentId", "kind", "name", "installedVersion", "latestVersion", "status", "checkStatus", "checkedAt", "sourceUrl"}:
            raise ProductionLedgerError("지원하지 않는 component-record 입력입니다")
        component_id = _text(params.get("componentId"), "componentId", 160, required=True)
        kind = params.get("kind")
        if kind not in COMPONENT_KINDS: raise ProductionLedgerError("component kind가 올바르지 않습니다")
        name = _text(params.get("name"), "name", 200, required=True)
        installed, latest = _text(params.get("installedVersion"), "installedVersion", 100), _text(params.get("latestVersion"), "latestVersion", 100)
        if "status" in params and "checkStatus" in params and params["status"] != params["checkStatus"]:
            raise ProductionLedgerError("status와 checkStatus가 서로 다릅니다")
        status = _text(params.get("status", params.get("checkStatus", "installed")), "status", 80, required=True)
        source = _text(params.get("sourceUrl"), "sourceUrl", 2000)
        if source is not None and not source.startswith("https://"): raise ProductionLedgerError("sourceUrl은 https URL이어야 합니다")
        checked = params.get("checkedAt", _now_ms())
        if type(checked) is not int or checked < 0: raise ProductionLedgerError("checkedAt이 올바르지 않습니다")
        with self.db.transaction(write=True) as connection:
            connection.execute("INSERT INTO production_components(component_id,kind,name,installed_version,latest_version,check_status,checked_at,source_url) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(component_id) DO UPDATE SET kind=excluded.kind,name=excluded.name,installed_version=excluded.installed_version,latest_version=excluded.latest_version,check_status=excluded.check_status,checked_at=excluded.checked_at,source_url=excluded.source_url", (component_id, kind, name, installed, latest, status, checked, source))
        return {"componentId": component_id, "kind": kind, "name": name, "installedVersion": installed, "latestVersion": latest, "checkStatus": status, "checkedAt": _iso(checked), "checkedAtMs": checked, "sourceUrl": source}

    def dashboard(self, params=None):
        params = params or {}; where, values, limit, _, _ = self._filters(params, group_ids=True)
        if params.get("cursor") is not None: raise ProductionLedgerError("dashboard는 cursor를 지원하지 않습니다")
        task_where = list(where)
        clause = " WHERE " + " AND ".join([*task_where, "parent_task_id IS NULL"])
        with self.db.transaction() as connection:
            components = self.components({"limit": 100})["components"]
            if not self._has(connection, "production_tasks"):
                return {"summary": {"totalTasks": 0, "succeeded": 0, "failed": 0, "running": 0, "totalElapsedMs": None, "avgElapsedMs": None, "requestCount": 0, "generationCount": 0, "revisionCount": 0, "outputBytes": None}, "byTask": [], "trend": [], "slowTasks": [], "groupSummaries": [], "stageBreakdown": [], "components": components}
            summary = connection.execute("SELECT count(*),sum(status='success'),sum(status='failed'),sum(status IN ('queued','running')),sum(CASE WHEN status IN ('success','failed','cancelled') THEN elapsed_ms END),avg(CASE WHEN status='success' THEN elapsed_ms END) FROM production_tasks" + clause, values).fetchone()
            prompt_where, prompt_values = [], []
            for key, column in (("projectId", "project_id"), ("groupId", "group_id"), ("domain", "domain")):
                if params.get(key) is not None:
                    prompt_where.append(column + "=?"); prompt_values.append(params[key])
            if params.get("groupIds") is not None:
                group_ids = _group_ids(params["groupIds"])
                prompt_where.append("group_id IN (" + ",".join("?" for _ in group_ids) + ")"); prompt_values.extend(group_ids)
            for key, operator in (("since", ">="), ("until", "<=")):
                if params.get(key) is not None:
                    prompt_where.append("requested_at" + operator + "?"); prompt_values.append(params[key])
            if any(params.get(key) is not None for key in ("engine", "model", "taskType", "status")):
                prompt_where.append("request_id IN (SELECT request_id FROM production_tasks" + clause + ")")
                prompt_values.extend(values)
            prompt_scope = " WHERE " + " AND ".join(prompt_where) if prompt_where else ""
            requests = connection.execute("SELECT count(*) FROM production_prompts" + prompt_scope + (" AND " if prompt_scope else " WHERE ") + "source='user'", prompt_values).fetchone()[0]
            generations = connection.execute("SELECT count(*) FROM production_tasks" + clause + " AND status='success' AND lower(task_type) IN ('generation','generate','render')", values).fetchone()[0]
            revisions = connection.execute("SELECT count(*) FROM production_tasks" + clause + " AND status='success' AND lower(task_type) IN ('revision','lyrics','title','replace','restore')", values).fetchone()[0]
            output = connection.execute("SELECT sum(bytes) FROM (SELECT path,max(bytes) bytes FROM production_files WHERE role!='input' AND exists_at_finish=1 AND task_id IN (SELECT task_id FROM production_tasks" + clause + ") GROUP BY path)", values).fetchone()[0]
            performance_conditions = task_where
            performance_clause = " WHERE " + " AND ".join(performance_conditions) if performance_conditions else ""
            performance_status = " AND " if performance_conditions else " WHERE "
            cte = "WITH filtered AS (SELECT * FROM production_tasks" + performance_clause + performance_status + "status='success' AND elapsed_ms IS NOT NULL), ranked AS (SELECT *,count(*) OVER (PARTITION BY domain,task_type,engine,model) n,row_number() OVER (PARTITION BY domain,task_type,engine,model ORDER BY elapsed_ms) rn FROM filtered) "
            groups = connection.execute(cte + "SELECT domain,task_type,engine,model,count(*),avg(elapsed_ms),avg(CASE WHEN rn IN ((n+1)/2,(n+2)/2) THEN elapsed_ms END),max(CASE WHEN rn=(n*95+99)/100 THEN elapsed_ms END),avg(CASE WHEN media_seconds>0 THEN elapsed_ms/(media_seconds*1000.0) END),avg(CASE WHEN frame_count>0 AND elapsed_ms>0 THEN frame_count*1000.0/elapsed_ms END) FROM ranked GROUP BY domain,task_type,engine,model ORDER BY count(*) DESC LIMIT 100", values).fetchall()
            by_task = [{"domain": row[0], "taskType": row[1], "engine": row[2], "model": row[3], "count": row[4], "avgElapsedMs": row[5], "medianElapsedMs": row[6], "p95ElapsedMs": row[7], "avgRealtimeFactor": row[8], "avgFps": row[9]} for row in groups]
            trend = [{"day": row[0], "count": row[1], "elapsedMs": row[2]} for row in connection.execute("SELECT strftime('%Y-%m-%d',finished_at/1000,'unixepoch','+9 hours'),count(*),sum(elapsed_ms) FROM production_tasks" + clause + " AND status='success' AND finished_at IS NOT NULL GROUP BY 1 ORDER BY 1 DESC LIMIT 90", values).fetchall()]
            slow_sql = "WITH filtered AS (SELECT * FROM production_tasks" + performance_clause + performance_status + "status='success' AND elapsed_ms IS NOT NULL), measured AS (SELECT *,CASE WHEN media_seconds>0 THEN 'realtimeFactor' WHEN frame_count>0 THEN 'msPerFrame' ELSE 'elapsedMs' END basis,CASE WHEN media_seconds>0 THEN elapsed_ms/(media_seconds*1000.0) WHEN frame_count>0 THEN elapsed_ms*1.0/frame_count ELSE elapsed_ms END metric FROM filtered), scored AS (SELECT *,count(*) OVER (PARTITION BY domain,task_type,engine,model,basis) n,sum(metric) OVER (PARTITION BY domain,task_type,engine,model,basis) sum_metric FROM measured) SELECT task_id,project_id,domain,task_type,engine,model,elapsed_ms,basis,metric,(sum_metric-metric)/(n-1),n FROM scored WHERE n>=3 AND metric>((sum_metric-metric)/(n-1))*1.5 ORDER BY metric DESC LIMIT 30"
            slow = [{"taskId": row[0], "projectId": row[1], "domain": row[2], "taskType": row[3], "engine": row[4], "model": row[5], "elapsedMs": row[6], "basis": row[7], "metric": row[8], "groupAverage": row[9], "sampleCount": row[10]} for row in connection.execute(slow_sql, values).fetchall()]
            explicit_group_scope = params.get("groupIds") is not None or params.get("groupId") is not None
            if params.get("groupIds") is not None:
                summary_ids = _group_ids(params["groupIds"])
            elif params.get("groupId") is not None:
                summary_ids = [params["groupId"]]
            else:
                group_rows = connection.execute("SELECT group_id FROM production_tasks WHERE " + " AND ".join([*task_where, "group_id IS NOT NULL"]) + " GROUP BY group_id ORDER BY max(coalesce(finished_at,started_at)) DESC LIMIT ?", (*values, limit)).fetchall()
                summary_ids = [row[0] for row in group_rows]
            group_summaries = [{"groupId": group_id, "performance": performance} for group_id, performance in self._performance_by_key(connection, summary_ids, task_where, values, key_column="group_id").items()]
            stage = self._stage_breakdown(connection, task_where, values) if explicit_group_scope and len(summary_ids) == 1 else []
        return {"summary": {"totalTasks": summary[0], "succeeded": summary[1] or 0, "failed": summary[2] or 0, "running": summary[3] or 0, "totalElapsedMs": summary[4], "avgElapsedMs": summary[5], "requestCount": requests, "generationCount": generations, "revisionCount": revisions, "outputBytes": output}, "byTask": by_task, "trend": list(reversed(trend)), "slowTasks": slow, "groupSummaries": group_summaries, "stageBreakdown": stage, "components": components}

    @staticmethod
    def _activity_params(params):
        if not isinstance(params, dict) or set(params) - {"projectId", "groupId", "domain", "limit", "offset"}:
            raise ProductionLedgerError("activity 조회 조건이 올바르지 않습니다")
        project_id = params.get("projectId")
        group_id = params.get("groupId")
        domain = params.get("domain")
        if project_id is not None and (not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id)):
            raise ProductionLedgerError("projectId 조회 조건이 올바르지 않습니다")
        if group_id is not None and (not isinstance(group_id, str) or not PROJECT_ID.fullmatch(group_id)):
            raise ProductionLedgerError("groupId 조회 조건이 올바르지 않습니다")
        if domain is not None and domain not in DOMAINS:
            raise ProductionLedgerError("domain 조회 조건이 올바르지 않습니다")
        limit = _limit(params.get("limit"))
        offset = params.get("offset", 0)
        if type(offset) is not int or not 0 <= offset <= 10_000:
            raise ProductionLedgerError("offset 조회 조건이 올바르지 않습니다")
        return {"projectId": project_id, "groupId": group_id, "domain": domain, "limit": limit, "offset": offset}

    @staticmethod
    def _runtime_queue(runtime_queue):
        value = runtime_queue or {"state": "unavailable", "paused": None, "items": [], "observedAtMs": None}
        if not isinstance(value, dict) or set(value) - {"state", "paused", "items", "observedAtMs", "truncated", "totalCount"}:
            raise ProductionLedgerError("runtime queue 형식이 올바르지 않습니다")
        state = value.get("state", "unavailable")
        if state not in {"available", "offline", "unavailable"} or value.get("paused") not in {True, False, None}:
            raise ProductionLedgerError("runtime queue 상태가 올바르지 않습니다")
        observed = value.get("observedAtMs")
        if observed is not None and (type(observed) is not int or observed < 0):
            raise ProductionLedgerError("runtime queue 시각이 올바르지 않습니다")
        raw_items = value.get("items", [])
        if not isinstance(raw_items, list) or len(raw_items) > 10_000:
            raise ProductionLedgerError("runtime queue 항목이 너무 많습니다")
        items, by_task_id = [], {}
        for index, raw in enumerate(raw_items):
            if not isinstance(raw, dict):
                raise ProductionLedgerError("runtime queue 작업 형식이 올바르지 않습니다")
            if raw.get("status") not in RUNNING:
                raise ProductionLedgerError("runtime queue 작업이 올바르지 않습니다")
            position = raw.get("position", index)
            progress = raw.get("progress")
            if type(position) is not int or position < 0 or progress is not None and (isinstance(progress, bool) or not isinstance(progress, (int, float)) or not math.isfinite(progress) or not 0 <= progress <= 1):
                raise ProductionLedgerError("runtime queue 작업 값이 올바르지 않습니다")
            stage = _text(raw.get("currentStage"), "currentStage", MAX_STAGE)
            summary = _text(raw.get("summary"), "summary", MAX_SUMMARY)
            def text(key, maximum=240):
                item = raw.get(key)
                return item if isinstance(item, str) and item and len(item) <= maximum else None
            def number(key, *, integer=False):
                try:
                    return _number(raw.get(key), key, integer=integer)
                except ProductionLedgerError:
                    return None
            job_id = text("jobId")
            task_id = text("taskId")
            ledger_task_id = task_id if task_id is not None and PUBLIC_ID.fullmatch(task_id) else None
            runtime_seed = job_id or task_id or json.dumps({"position": position, "title": text("title"), "project": text("project", 4000)}, ensure_ascii=False, sort_keys=True)
            runtime_id = hashlib.sha256(("runtime:" + runtime_seed).encode("utf-8")).hexdigest()[:48]
            if any(item["runtimeId"] == runtime_id for item in items):
                runtime_id = hashlib.sha256(("runtime:" + runtime_seed + ":" + str(position)).encode("utf-8")).hexdigest()[:48]
            item = {"runtimeId": runtime_id, "ledgerTaskId": ledger_task_id, "jobId": job_id, "project": text("project", 4000), "projectId": text("projectId", 64), "title": text("title"), "domain": text("domain", 20), "taskType": text("taskType", 80), "engine": text("engine"), "model": text("model"), "status": raw["status"], "position": position, "progress": progress, "currentStage": stage, "summary": summary, "expectedMediaSeconds": number("expectedMediaSeconds") if "expectedMediaSeconds" in raw else number("plannedSeconds"), "expectedFrameCount": number("expectedFrameCount", integer=True), "queuedAtMs": number("queuedAt", integer=True), "startedAtMs": number("startedAt", integer=True), "elapsedMs": number("elapsedMs")}
            items.append(item)
            if ledger_task_id is not None and ledger_task_id not in by_task_id:
                by_task_id[ledger_task_id] = item
        truncated = value.get("truncated", False)
        total = value.get("totalCount", len(items))
        if type(truncated) is not bool or type(total) is not int or total < len(items):
            raise ProductionLedgerError("runtime queue 개수가 올바르지 않습니다")
        return {"state": state, "paused": value.get("paused"), "items": items, "byTaskId": by_task_id, "observedAtMs": observed, "truncated": truncated, "totalCount": total}

    @staticmethod
    def _activity_estimate(connection, task, cache):
        key = (task["domain"], task["taskType"], task["engine"], task["model"], task["expectedMediaSeconds"], task["expectedFrameCount"])
        if key in cache:
            return dict(cache[key])
        rows = connection.execute("SELECT elapsed_ms,media_seconds,frame_count FROM production_tasks WHERE status='success' AND domain=? AND task_type=? AND engine IS ? AND model IS ? AND elapsed_ms IS NOT NULL ORDER BY finished_at DESC LIMIT 100", key[:4]).fetchall()
        expected_media, expected_frames = task["expectedMediaSeconds"], task["expectedFrameCount"]
        if expected_media is not None:
            values = [elapsed / media * expected_media for elapsed, media, _ in rows if media is not None and media > 0]
            basis = "expectedMediaSeconds"
        elif expected_frames is not None:
            values = [elapsed / frames * expected_frames for elapsed, _, frames in rows if frames is not None and frames > 0]
            basis = "expectedFrameCount"
        else:
            values = [elapsed for elapsed, _, _ in rows]
            basis = "elapsedMs"
        values.sort()
        count = len(values)
        if not count:
            result = {"estimatedMs": None, "avgMs": None, "lowerMs": None, "upperMs": None, "sampleCount": 0, "basis": basis, "confidence": "unavailable", "missingMeasurementCount": len(rows)}
        else:
            result = {"estimatedMs": sum(values) / count, "avgMs": sum(values) / count, "lowerMs": values[(count - 1) // 4], "upperMs": values[min(count - 1, math.ceil(count * .95) - 1)], "sampleCount": count, "basis": basis, "confidence": "high" if count >= 5 else "medium" if count >= 3 else "low", "missingMeasurementCount": len(rows) - count}
        cache[key] = result
        return dict(result)

    @staticmethod
    def _activity_task(task, title, runtime, now, estimate, phase=None):
        phase = phase or task
        runtime_item = runtime["byTaskId"].get(phase["taskId"]) or runtime["byTaskId"].get(task["taskId"])
        status = runtime_item["status"] if runtime_item else phase["status"] if phase["status"] == "running" else task["status"]
        progress = runtime_item["progress"] if runtime_item and runtime_item["progress"] is not None else phase["progress"]
        current_stage = runtime_item["currentStage"] if runtime_item and runtime_item["currentStage"] is not None else phase["currentStage"]
        summary = runtime_item["summary"] if runtime_item and runtime_item["summary"] is not None else phase["progressSummary"]
        source = "app-runtime" if runtime_item else "external-ledger" if task["domain"] == "motion" else "app-ledger"
        elapsed = runtime_item["elapsedMs"] if runtime_item and runtime_item["elapsedMs"] is not None else max(0, now - task["startedAtMs"]) if status == "running" else 0
        remaining, overrun = estimate["estimatedMs"], False
        if status == "running":
            if remaining is not None:
                if elapsed >= remaining:
                    overrun, remaining = True, None
                else:
                    remaining = max(1000, remaining - elapsed)
        observed_at = phase["progressUpdatedAtMs"] or phase["startedAtMs"]
        stale = source == "external-ledger" and now - observed_at > 300_000
        estimate.update({"remainingMs": remaining, "overrun": overrun})
        return {"taskId": task["taskId"], "phaseTaskId": phase["taskId"] if phase["taskId"] != task["taskId"] else None, "phaseTaskType": phase["taskType"] if phase["taskId"] != task["taskId"] else None, "projectId": task["projectId"], "groupId": task["groupId"], "title": title, "requestId": task["requestId"], "parentTaskId": task["parentTaskId"], "domain": task["domain"], "taskType": task["taskType"], "engine": task["engine"], "model": task["model"], "status": status, "source": source, "stale": stale, "startedAtMs": task["startedAtMs"], "currentStage": current_stage, "summary": summary, "progress": progress, "progressEstimated": False, "elapsedMs": elapsed, "estimate": estimate}

    @staticmethod
    def _runtime_only_task(item, now):
        started = item["startedAtMs"]
        elapsed = item["elapsedMs"] if item["elapsedMs"] is not None else max(0, now - started) if item["status"] == "running" and started is not None else 0
        return {"taskId": item["runtimeId"], "runtimeOnly": True, "ledgerTaskId": item["ledgerTaskId"], "jobId": item["jobId"], "phaseTaskId": None, "phaseTaskType": None, "projectId": item["projectId"] if item["projectId"] is not None and PROJECT_ID.fullmatch(item["projectId"]) else None, "groupId": None, "title": item["title"] or "연결되지 않은 앱 작업", "requestId": None, "parentTaskId": None, "domain": item["domain"] if item["domain"] in DOMAINS else None, "taskType": item["taskType"] or "알 수 없는 작업", "engine": item["engine"], "model": item["model"], "status": item["status"], "source": "app-runtime-untracked", "stale": False, "startedAtMs": started, "currentStage": item["currentStage"], "summary": item["summary"], "progress": item["progress"], "progressEstimated": False, "elapsedMs": elapsed, "expectedMediaSeconds": item["expectedMediaSeconds"], "expectedFrameCount": item["expectedFrameCount"], "estimate": {"estimatedMs": None, "remainingMs": None, "avgMs": None, "lowerMs": None, "upperMs": None, "sampleCount": 0, "basis": "runtime-unmatched", "confidence": "unavailable", "missingMeasurementCount": 0, "overrun": False}}

    @staticmethod
    def _activity_scope(item, filters):
        return (filters["projectId"] is None or item["projectId"] == filters["projectId"]) and (filters["groupId"] is None or item["groupId"] == filters["groupId"]) and (filters["domain"] is None or item["domain"] == filters["domain"])

    def _next_stages(self, connection, current_tasks, estimates):
        keys = list(dict.fromkeys((item["domain"], item["taskType"], item["engine"], item["model"]) for item in current_tasks))
        results = {}
        for offset in range(0, len(keys), 200):
            chunk = keys[offset:offset + 200]
            where = " OR ".join("(domain=? AND previous_type=? AND previous_engine IS ? AND previous_model IS ?)" for _ in chunk)
            values = [value for key in chunk for value in key]
            rows = connection.execute("""WITH ordered AS (
              SELECT project_id,domain,task_type,engine,model,
                lag(task_type) OVER (PARTITION BY project_id,domain ORDER BY seq) previous_type,
                lag(engine) OVER (PARTITION BY project_id,domain ORDER BY seq) previous_engine,
                lag(model) OVER (PARTITION BY project_id,domain ORDER BY seq) previous_model
              FROM production_tasks WHERE status IN ('success','failed','cancelled')
            ) SELECT domain,previous_type,previous_engine,previous_model,task_type,engine,model,count(*) sample_count
              FROM ordered WHERE """ + where + """
              GROUP BY domain,previous_type,previous_engine,previous_model,task_type,engine,model
              ORDER BY domain,previous_type,previous_engine,previous_model,sample_count DESC,task_type""", values).fetchall()
            for row in rows:
                key = tuple(row[:4])
                if key in results:
                    continue
                candidate = {"domain": row[0], "taskType": row[4], "engine": row[5], "model": row[6], "expectedMediaSeconds": None, "expectedFrameCount": None}
                estimate = self._activity_estimate(connection, candidate, estimates)
                results[key] = {"taskType": row[4], "estimatedMs": estimate["estimatedMs"], "sampleCount": row[7], "estimateSampleCount": estimate["sampleCount"], "inferred": True}
        return results

    def activity(self, params=None, runtime_queue=None):
        filters = self._activity_params(params or {})
        runtime = self._runtime_queue(runtime_queue)
        with self.db.transaction() as connection:
            if connection is None or not self._has(connection, "production_tasks"):
                return {"generatedAtMs": _now_ms(), "scope": filters | {"queuedCount": 0, "runningCount": 0, "knownWorkMs": 0, "unknownCount": 0, "completionEtaMs": None}, "globalQueue": {"queuedCount": 0, "runningCount": 0, "knownWorkMs": 0, "unknownCount": 0, "completionEtaMs": None}, "projects": [], "queue": {"items": [], "pageOffset": filters["offset"], "nextOffset": None, "totalCount": 0, "truncated": runtime["truncated"]}, "runtime": {key: runtime[key] for key in ("state", "paused", "observedAtMs")}}
            order_column = "queued_at" if "queued_at" in self._columns(connection, "production_tasks") else "started_at"
            raw = [self._row_task(row) for row in connection.execute("SELECT " + self._task_select(connection) + " FROM production_tasks WHERE status IN ('queued','running') ORDER BY " + order_column + ",seq LIMIT 10001").fetchall()]
            ledger_truncated = len(raw) > 10_000
            raw = raw[:10_000]
            active = {task["taskId"]: task for task in raw}
            def root_for(task):
                root, seen = task, set()
                while root["parentTaskId"] in active and root["parentTaskId"] not in seen:
                    seen.add(root["taskId"])
                    root = active[root["parentTaskId"]]
                return root
            root_tasks, phases = {}, {}
            for task in raw:
                root = root_for(task)
                root_tasks[root["taskId"]] = root
                phases.setdefault(root["taskId"], []).append(task)
            project_ids = list({task["projectId"] for task in root_tasks.values()})
            if project_ids and self._has(connection, "production_projects"):
                marks = ",".join("?" for _ in project_ids)
                titles = {row[0]: row[1] or Path(row[2]).name for row in connection.execute("SELECT project_id,title,path FROM production_projects WHERE project_id IN (" + marks + ")", project_ids).fetchall()}
            else:
                titles = {}
            estimates, now = {}, _now_ms()
            items = []
            matched_runtime_ids = {item["runtimeId"] for item in runtime["items"] if item["ledgerTaskId"] in active}
            for task in root_tasks.values():
                phase = min(phases[task["taskId"]], key=lambda child: (0 if child["taskId"] in runtime["byTaskId"] and runtime["byTaskId"][child["taskId"]]["status"] == "running" else 1 if child["status"] == "running" else 2, runtime["byTaskId"][child["taskId"]]["position"] if child["taskId"] in runtime["byTaskId"] else child["seq"]))
                item = self._activity_task(task, titles.get(task["projectId"], task["projectId"]), runtime, now, self._activity_estimate(connection, task, estimates), phase)
                item["_queueOrder"] = task["queuedAtMs"] or task["startedAtMs"]
                runtime_item = runtime["byTaskId"].get(phase["taskId"]) or runtime["byTaskId"].get(task["taskId"])
                item["_runtimePosition"] = runtime_item["position"] if runtime_item is not None else None
                items.append(item)
            for runtime_item in runtime["items"]:
                if runtime_item["runtimeId"] in matched_runtime_ids:
                    continue
                item = self._runtime_only_task(runtime_item, now)
                item["_queueOrder"] = runtime_item["queuedAtMs"] if runtime_item["queuedAtMs"] is not None else runtime_item["position"]
                item["_runtimePosition"] = runtime_item["position"]
                items.append(item)
            items.sort(key=lambda item: (0, item["_runtimePosition"]) if item["_runtimePosition"] is not None else (1, item["_queueOrder"]))
            for position, item in enumerate(items):
                item["position"] = item["_runtimePosition"] if item["_runtimePosition"] is not None else position
                del item["_queueOrder"], item["_runtimePosition"]

            running_items = [item for item in items if item["status"] == "running"]
            parallel_running = len(running_items) > 1
            running = running_items[0] if len(running_items) == 1 else None
            running_blocked = running is not None and (running["stale"] or (running["source"].startswith("app-") and (runtime["state"] != "available" or runtime["paused"] is True)) or running["estimate"]["remainingMs"] is None)
            cumulative = running["estimate"]["remainingMs"] if running is not None and not running_blocked else 0
            blocked = runtime["truncated"] or ledger_truncated or parallel_running or running_blocked
            for item in items:
                estimate = item["estimate"]
                running = item["status"] == "running"
                blocked_for_runtime = item["source"].startswith("app-") and (runtime["state"] != "available" or runtime["paused"] is True)
                blocked_for_state = item["stale"] or blocked_for_runtime or estimate["remainingMs"] is None
                if running:
                    item["estimatedWaitMs"] = 0
                    item["estimatedStartAtMs"] = item["startedAtMs"]
                    item["estimatedFinishAtMs"] = None if blocked_for_state else now + estimate["remainingMs"]
                    continue
                item["estimatedWaitMs"] = None if blocked else cumulative
                item["estimatedStartAtMs"] = None if blocked else now + cumulative
                item["estimatedFinishAtMs"] = None if blocked or blocked_for_state else now + cumulative + estimate["remainingMs"]
                if estimate["remainingMs"] is not None:
                    cumulative += estimate["remainingMs"]
                if blocked_for_state:
                    blocked = True

            def summary(rows):
                known = sum(item["estimate"]["remainingMs"] for item in rows if item["estimate"]["remainingMs"] is not None)
                unknown = sum(1 for item in rows if item["estimate"]["remainingMs"] is None)
                tail = rows[-1]["estimatedFinishAtMs"] if rows else now
                return {"queuedCount": sum(item["status"] == "queued" for item in rows), "runningCount": sum(item["status"] == "running" for item in rows), "knownWorkMs": known, "unknownCount": unknown, "completionEtaMs": tail if rows and tail is not None and unknown == 0 else None}

            visible = [item for item in items if self._activity_scope(item, filters)]
            by_project = {}
            for item in visible:
                if not item.get("runtimeOnly"):
                    by_project.setdefault(item["projectId"], []).append(item)
            project_states = []
            for project_id, active in by_project.items():
                current = next((item for item in active if item["status"] == "running"), None)
                queued = next((item for item in active if item["status"] == "queued"), None)
                active_request = current["requestId"] if current else queued["requestId"] if queued else None
                project_states.append({"projectId": project_id, "active": active, "current": current, "queued": queued, "activeRequest": active_request})
            request_rows = {}
            request_ids = list(dict.fromkeys(item["activeRequest"] for item in project_states if item["activeRequest"] is not None))
            for offset in range(0, len(request_ids), 400):
                chunk = request_ids[offset:offset + 400]
                marks = ",".join("?" for _ in chunk)
                for row in connection.execute("SELECT " + self._task_select(connection) + " FROM production_tasks WHERE request_id IN (" + marks + ") ORDER BY seq", chunk).fetchall():
                    task = self._row_task(row)
                    request_rows.setdefault(task["requestId"], []).append(task)
            roots_by_project = {}
            for task in root_tasks.values():
                roots_by_project.setdefault(task["projectId"], []).append(task)
            projects = []
            for state in project_states:
                project_id, active, current, queued, active_request = state["projectId"], state["active"], state["current"], state["queued"], state["activeRequest"]
                rows = request_rows.get(active_request, roots_by_project.get(project_id, [])) if active_request is not None else roots_by_project.get(project_id, [])
                row_ids = {task["taskId"] for task in rows}
                roots_for_progress = [task for task in rows if task["parentTaskId"] not in row_ids]
                completed, total, unknown = 0, 0, 0
                for task in roots_for_progress:
                    if task["status"] in TERMINAL:
                        if task["elapsedMs"] is None: unknown += 1
                        else: completed += task["elapsedMs"]; total += task["elapsedMs"]
                    else:
                        estimate = self._activity_estimate(connection, task, estimates)["estimatedMs"]
                        if estimate is None: unknown += 1
                        else:
                            total += estimate
                            if task["status"] == "running":
                                completed += min(max(0, now - task["startedAtMs"]), estimate * .99)
                ratio = completed / total if total else None
                if ratio is not None and any(task["status"] in RUNNING for task in roots_for_progress):
                    ratio = min(ratio, .99)
                project = {"projectId": project_id, "groupId": active[0]["groupId"], "title": active[0]["title"], "recordedScope": "request" if active_request else "active-only", "currentTask": current, "nextQueuedTask": queued, "progress": {"completedWorkMs": completed, "totalWorkMs": total or None, "ratio": ratio, "estimated": True, "unknownTaskCount": unknown}}
                projects.append(project)
            inferred = self._next_stages(connection, [project["currentTask"] for project in projects if project["currentTask"] is not None and project["nextQueuedTask"] is None], estimates)
            for project in projects:
                queued = project["nextQueuedTask"]
                if queued is not None:
                    project["nextStage"] = {"taskType": queued["taskType"], "estimatedMs": queued["estimate"]["estimatedMs"], "sampleCount": queued["estimate"]["sampleCount"], "inferred": False}
                elif project["currentTask"] is not None:
                    current = project["currentTask"]
                    project["nextStage"] = inferred.get((current["domain"], current["taskType"], current["engine"], current["model"]))
                else:
                    project["nextStage"] = None
        total = len(visible)
        page = visible[filters["offset"]:filters["offset"] + filters["limit"]]
        next_offset = filters["offset"] + len(page) if filters["offset"] + len(page) < total else None
        global_queue = summary(items)
        if blocked:
            global_queue["completionEtaMs"] = None
        return {"generatedAtMs": now, "scope": filters | summary(visible), "globalQueue": global_queue, "projects": projects, "queue": {"items": page, "pageOffset": filters["offset"], "nextOffset": next_offset, "totalCount": total, "truncated": runtime["truncated"] or ledger_truncated}, "runtime": {key: runtime[key] for key in ("state", "paused", "observedAtMs")}}

    def dispatch(self, action, params=None):
        actions = {"request": self.request, "task-start": self.start_task, "task-progress": self.progress_task, "task-finish": self.finish_task, "files-record": self.record_files, "projects": self.projects, "prompts": self.prompts, "tasks": self.tasks, "activity": self.activity, "files": self.files, "dashboard": self.dashboard, "components": self.components, "component-record": self.record_component}
        if action not in actions: raise ProductionLedgerError("지원하지 않는 production action입니다")
        return actions[action](params or {})


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("request", "task-start", "task-progress", "task-finish", "files-record", "component-record", "projects", "prompts", "tasks", "activity", "files", "dashboard", "components"))
    parser.add_argument("--data-dir", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--json")
    source.add_argument("--stdin", action="store_true")
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(16 * 1024 * 1024 + 1).decode("utf-8") if args.stdin else args.json
        if len(raw.encode("utf-8")) > 16 * 1024 * 1024: raise ProductionLedgerError("stdin JSON이 안전 한도를 초과했습니다")
        value = json.loads(raw)
        if not isinstance(value, dict): raise ProductionLedgerError("JSON 객체가 필요합니다")
        print(json.dumps({"ok": True, "result": ProductionLedger(args.data_dir).dispatch(args.action, value)}, ensure_ascii=False, allow_nan=False))
        return 0
    except (ProductionLedgerError, ManagementDBError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": {"code": "production_ledger_error", "message": str(error)}}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

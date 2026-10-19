"""Bounded Studio update jobs using only Road Music public update commands."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import re
import secrets
import subprocess
import threading
import time

from management_db import ManagementDB
from studio_status import cli_root


JOB_ID = re.compile(r"[0-9a-f]{48}\Z")
SKILL_ID = re.compile(r"[a-z0-9-]+\Z")


class StudioUpdatesError(ValueError):
    pass


def _now(): return int(time.time() * 1000)

def _family(component):
    return "skills" if component == "music-road-skills" or str(component).startswith("skill:") else component
def _at_least(current, target):
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) for value in (current, target)): return False
    try: return tuple(map(int, current.split("."))) >= tuple(map(int, target.split(".")))
    except (AttributeError, ValueError): return False


def _json(process):
    lines = [line for line in str(getattr(process, "stdout", "")).splitlines() if line.strip()]
    if len(lines) != 1:
        raise StudioUpdatesError(str(getattr(process, "stderr", "")).strip() or "업데이트 명령 실행 결과를 확인하지 못했습니다")
    try:
        payload = json.loads(lines[0])
    except json.JSONDecodeError as error:
        raise StudioUpdatesError("업데이트 명령 응답이 올바른 JSON이 아닙니다") from error
    if not isinstance(payload, dict): raise StudioUpdatesError("업데이트 명령 응답 형식이 올바르지 않습니다")
    if payload.get("ok") is not True:
        detail = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        error = StudioUpdatesError(str(detail.get("message") or "업데이트 명령이 실패했습니다"))
        error.definitive = not detail.get("uncertain", False)
        raise error
    if getattr(process, "returncode", 1) != 0 or not isinstance(payload.get("result"), dict):
        raise StudioUpdatesError("업데이트 명령 종료 상태를 확인하지 못했습니다")
    return payload["result"]


class StudioUpdates:
    """Session-scoped jobs; only compact status snapshots are persisted."""

    def __init__(self, session_data, *, root=None, skills_parent=None, runner=None, env=None):
        self.data_dir = Path(session_data).resolve()
        self.root = Path(root).resolve() if root else cli_root(env)
        self.skills_parent = Path(skills_parent).resolve() if skills_parent else Path(__file__).resolve().parents[2]
        self.runner = runner or self._run
        self.env = dict(os.environ)
        self.env.update(env or {})
        self.env["ROADMUSIC_DATA_DIR"] = str(self.data_dir)
        self.env["ROADMUSIC_STUDIO_AUTO_OPEN"] = "0"
        self.db = ManagementDB(self.data_dir)
        self.jobs = {}
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="roadmusic-update")
        self._mark_stale()

    def _doc(self, job_id): return "studio-update-job:" + job_id
    @staticmethod
    def _alive(pid):
        try:
            if isinstance(pid, int) and pid > 0: os.kill(pid, 0); return True
        except PermissionError: return True
        except OSError: return False
        return False
    def _recover_dead(self, items, connection):
        changed = False
        uncertain = {"downloading", "installing", "restart-required", "verification-required"}
        for item in items:
            if item.get("status") not in {"queued", "running", "restart-required"} or self._alive(item.get("ownerPid")): continue
            if item.get("phase") in uncertain:
                item.update(status="verification-required", phase="verification-required", progress=None, error="설치가 중단됐을 수 있습니다. 현재 설치 버전과 설치 상태를 확인한 뒤 다시 진행하세요.", finishedAt=_now())
            else:
                item.update(status="failed", phase="stale", progress=None, error="제작실이 다시 시작되어 업데이트 작업 상태를 복구할 수 없습니다.", finishedAt=_now())
            self.db.write_document(self._doc(item["jobId"]), item, connection=connection); changed = True
        return changed
    def _mark_stale(self):
        # A server restart cannot safely resume an installer process.
        if not self.db.path.exists(): return
        observed = self.db.read_document("studio-update-jobs", fallback=[])
        if not any(item.get("status") in {"queued", "running", "restart-required"} and not self._alive(item.get("ownerPid")) for item in observed): return
        with self.db.transaction(write=True) as connection:
            items = self.db.read_document("studio-update-jobs", fallback=[], connection=connection)
            changed = self._recover_dead(items, connection)
            if changed: self._write_index(items, connection)

    def _run(self, argv, *, cwd, env, timeout):
        return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False)

    def _invoke_cli(self, command, timeout=1800):
        if not self.root or not (self.root / "cli" / "road-music.js").is_file():
            raise StudioUpdatesError("Road Music CLI를 찾을 수 없습니다")
        env = dict(self.env); env["ROADMUSIC_STUDIO_AUTO_OPEN"] = "0"
        return _json(self.runner(["node", str(self.root / "cli" / "road-music.js"), command, "--no-start"], cwd=str(self.root), env=env, timeout=timeout))

    def _skill_script(self):
        direct = self.skills_parent / "road-music-skills-update" / "scripts" / "manage.cjs"
        source = self.root.parent / "music-road-skills" / "skills" / "road-music-skills-update" / "scripts" / "manage.cjs" if self.root else None
        return direct if direct.is_file() and ((self.skills_parent.parent / "manifest.json").is_file() or (self.skills_parent / ".music-road-skills/managed.json").is_file()) else source if source and source.is_file() else direct

    def _manifest_ids(self):
        try:
            installed = json.loads((self.skills_parent / ".music-road-skills/managed.json").read_text(encoding="utf-8"))
            if isinstance(installed.get("skills"), dict):
                return {identifier for identifier in installed["skills"] if SKILL_ID.fullmatch(identifier)}
        except (OSError, ValueError, TypeError, AttributeError): pass
        script = self._skill_script(); manifest = script.parents[3] / "manifest.json"
        try:
            values = json.loads(manifest.read_text(encoding="utf-8")).get("skills", [])
            return {item["id"] for item in values if isinstance(item, dict) and SKILL_ID.fullmatch(str(item.get("id", "")))}
        except (OSError, ValueError, TypeError):
            return set()

    def capabilities(self):
        root_ready = bool(self.root and (self.root / "cli" / "road-music.js").is_file())
        skill_script = self._skill_script()
        managed = skill_script.is_file()
        installed = (self.skills_parent / ".music-road-skills" / "managed.json").is_file()
        skill_reason = None if installed else "소스 버전은 확인할 수 있지만 관리 설치 상태가 없어 업데이트할 수 없습니다"
        history = self.db.read_document("studio-update-jobs", fallback=[])
        last_skill_check = next((item for item in reversed(history) if _family(item.get("componentId")) == "skills" and item.get("action") == "check" and item.get("status") == "succeeded"), None)
        if last_skill_check and (last_skill_check.get("result") or {}).get("locallyModified"):
            installed = False
            skill_reason = "스킬 파일에 로컬 수정이 있어 자동 교체를 막았습니다. 수정 보존 후 업데이트 확인을 다시 실행하세요."
        verification = {_family(item.get("componentId")) for item in self.db.read_document("studio-update-jobs", fallback=[]) if item.get("status") in {"verification-required", "restart-required"}}
        def capability(component_id, can_check, can_update, reason, kind):
            blocked = _family(component_id) in verification
            return {"componentId": component_id, "canCheck": can_check, "canUpdate": can_update and not blocked, "reason": "이전 설치 중단 상태를 먼저 확인해야 합니다" if blocked else reason, "updateKind": kind, "verificationRequired": blocked}
        result = [
            capability("road-music-app", root_ready, root_ready, None if root_ready else "Road Music CLI를 찾을 수 없습니다", "app"),
            capability("road-music-cli:current", root_ready, root_ready, None if root_ready else "Road Music CLI를 찾을 수 없습니다", "cli"),
            capability("music-road-skills", managed, managed and installed, None if managed and installed else skill_reason if managed else "관리 스킬 업데이터를 찾을 수 없습니다", "skills"),
        ]
        for identifier in sorted(self._manifest_ids()):
            result.append(capability("skill:" + identifier, managed, managed and installed, None if managed and installed else skill_reason if managed else "관리 스킬 업데이터를 찾을 수 없습니다", "skills"))
        return {"components": result, "lastJobs": self.db.read_document("studio-update-jobs", fallback=[])[-10:]}

    def _capability(self, component_id):
        if not isinstance(component_id, str): raise StudioUpdatesError("componentId가 올바르지 않습니다")
        item = next((item for item in self.capabilities()["components"] if item["componentId"] == component_id), None)
        if not item: raise StudioUpdatesError("허용되지 않은 업데이트 항목입니다")
        return item

    def _write_index(self, index, connection):
        protected = [item for item in index if item.get("status") in {"queued", "running", "verification-required", "restart-required"}]
        ordinary = [item for item in index if item not in protected]
        kept = protected + ordinary[-40:]
        self.db.write_document("studio-update-jobs", kept, connection=connection)
        for item in ordinary[:-40]:
            if isinstance(item.get("jobId"), str):
                self.db.delete_document(self._doc(item["jobId"]), connection=connection)
                self.jobs.pop(item["jobId"], None)

    def _save(self, job, connection=None):
        clean = {key: job.get(key) for key in ("jobId", "componentId", "action", "status", "phase", "progress", "result", "error", "createdAt", "finishedAt", "ownerPid", "targetVersion")}
        if connection is None:
            with self.db.transaction(write=True) as writer: return self._save(job, writer)
        index = self.db.read_document("studio-update-jobs", fallback=[], connection=connection)
        index = [item for item in index if item.get("jobId") != job["jobId"]] + [clean]
        self.db.write_document(self._doc(job["jobId"]), clean, connection=connection)
        self._write_index(index, connection)

    def start(self, action, component_id):
        if action not in {"check", "update"}: raise StudioUpdatesError("action은 check 또는 update여야 합니다")
        capability = self._capability(component_id)
        if not capability["canCheck"] or (action == "update" and not capability["canUpdate"]): raise StudioUpdatesError(capability["reason"] or "현재 환경에서는 업데이트할 수 없습니다")
        job = {"jobId": secrets.token_hex(24), "componentId": component_id, "action": action, "status": "queued", "phase": "queued", "progress": None, "result": None, "error": None, "createdAt": _now(), "finishedAt": None, "ownerPid": os.getpid()}
        with self.lock:
            with self.db.transaction(write=True) as connection:
                index = self.db.read_document("studio-update-jobs", fallback=[], connection=connection)
                self._recover_dead(index, connection)
                self._write_index(index, connection)
                for prior in index:
                    if prior.get("status") in {"verification-required", "restart-required"} and _family(prior.get("componentId")) == _family(component_id) and action == "update":
                        raise StudioUpdatesError("이전 설치 중단 상태를 먼저 확인해야 합니다")
                    if prior.get("status") in {"queued", "running"} and self._alive(prior.get("ownerPid")):
                        raise StudioUpdatesError("다른 제작실에서 업데이트 작업이 진행 중입니다")
                self.jobs[job["jobId"]] = job; self._save(job, connection)
        self.executor.submit(self._work, job["jobId"])
        return dict(job)

    def _verify_prior(self, component, current):
        if not isinstance(current, str): return
        with self.db.transaction(write=True) as connection:
            index = self.db.read_document("studio-update-jobs", fallback=[], connection=connection)
            for item in index:
                target = item.get("targetVersion")
                if _family(item.get("componentId")) == _family(component) and item.get("status") in {"verification-required", "restart-required"} and isinstance(target, str) and _at_least(current, target):
                    item.update(status="succeeded", phase="verified", progress=100, error=None, finishedAt=_now())
                    self.db.write_document(self._doc(item["jobId"]), item, connection=connection)
            self._write_index(index, connection)

    def _installed_cli_version(self):
        home = Path(self.env.get("ROADMUSIC_CLI_HOME") or Path.home() / ".local/share/road-music/cli").resolve()
        pointer = home / "current.json"
        try:
            if pointer.is_symlink() or pointer.stat().st_size > 65536: return None
            metadata = json.loads(pointer.read_text(encoding="utf-8")); version = metadata.get("cliVersion")
            if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version): return None
            target = home / version; script = target / "cli/road-music.js"
            if target.is_symlink() or script.is_symlink() or not script.is_file(): return None
            recorded = Path(metadata.get("cliPath", ""))
            if not recorded.is_absolute() or recorded.resolve() != script.resolve() or not script.resolve().is_relative_to(home): return None
            marker = json.loads((target / ".road-music-cli-install.json").read_text(encoding="utf-8"))
            if marker.get("cliVersion") != version: return None
            result = _json(self.runner(["node", str(script), "cli:version", "--no-start"], cwd=str(target), env=dict(self.env), timeout=30))
            return result.get("cliVersion") if result.get("cliVersion") == version else None
        except (OSError, ValueError, TypeError, StudioUpdatesError): return None

    def _work(self, job_id):
        with self.lock:
            job = self.jobs[job_id]; job.update(status="running", phase="checking", progress=None); self._save(job)
        try:
            component, action = job["componentId"], job["action"]
            if component == "road-music-app":
                result = self._invoke_cli("update:check")
                if action == "check": self._verify_prior(component, result.get("current"))
                if action == "update":
                    if not result.get("installable"): raise StudioUpdatesError(result.get("reason") or "설치 가능한 앱 업데이트가 없습니다")
                    with self.lock: job.update(targetVersion=result.get("version")); self._save(job)
                    with self.lock: job.update(phase="downloading", progress=None); self._save(job)
                    self._invoke_cli("update:download", timeout=7200)
                    with self.lock: job.update(phase="restart-required", progress=None); self._save(job)
                    install = self._invoke_cli("update:install", timeout=7200)
                    result = {"update": "restart-required", "observed": result, "install": install}
            elif component == "road-music-cli:current":
                result = self._invoke_cli("cli:update:check")
                if action == "check":
                    self._verify_prior(component, result.get("current"))
                    self._verify_prior(component, self._installed_cli_version())
                if action == "update":
                    with self.lock: job.update(targetVersion=result.get("version"), phase="installing", progress=None); self._save(job)
                    result = self._invoke_cli("cli:update:install", timeout=7200)
            else:
                script = self._skill_script()
                result = _json(self.runner(["node", str(script), "check", "--target", str(self.skills_parent)], cwd=str(self.skills_parent), env=dict(self.env), timeout=7200))
                if action == "check" and result.get("installed") and result.get("locallyModified") == []:
                    self._verify_prior(component, result.get("version"))
                if action == "update":
                    with self.lock: job.update(targetVersion=(result.get("latest") or {}).get("version"), phase="installing", progress=None); self._save(job)
                    result = _json(self.runner(["node", str(script), "update", "--target", str(self.skills_parent)], cwd=str(self.skills_parent), env=dict(self.env), timeout=7200))
            with self.lock:
                if job["phase"] == "restart-required": job.update(status="restart-required", result=result, error=None, finishedAt=_now())
                else: job.update(status="succeeded", phase="completed", progress=100, result=result, error=None, finishedAt=_now())
                self._save(job)
        except Exception as error:
            uncertain = job.get("action") == "update" and job.get("phase") in {"downloading", "installing", "restart-required"} and not getattr(error, "definitive", False)
            status = "verification-required" if uncertain else "failed"
            with self.lock: job.update(status=status, phase=status, progress=None, error=str(error)[:1000], finishedAt=_now()); self._save(job)

    def job(self, job_id):
        if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id): raise StudioUpdatesError("jobId가 올바르지 않습니다")
        result = self.db.read_document(self._doc(job_id), fallback=None)
        if result is None: raise StudioUpdatesError("업데이트 작업을 찾을 수 없습니다")
        return result

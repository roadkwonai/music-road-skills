"""Small read-only adapter for the live Road Music music queue.

The SQLite ledger owns durable task history.  This module only samples the
running app queue so activity views can join it to that history without
starting the app or writing transient progress back to SQLite.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import time

from studio_status import cli_root


TTL_SECONDS = 3
QUEUE_TIMEOUT_SECONDS = 3
_CACHE = {}


def _now_ms():
    return round(time.time() * 1000)


def _response(process):
    lines = [line for line in str(getattr(process, "stdout", "")).splitlines() if line.strip()]
    if len(lines) != 1:
        return None
    try:
        value = json.loads(lines[0])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _state(process, response):
    error = response.get("error") if isinstance(response, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    if code in {"SERVICE_STOPPED", "CONNECTION_LOST"}:
        return "offline"
    return "unavailable"


def _number(value, *, minimum=None, maximum=None, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if integer and int(value) != value:
        return None
    value = int(value) if integer else float(value)
    if minimum is not None and value < minimum:
        return None
    if maximum is not None and value > maximum:
        return None
    return value


def _item(value, *, status, position):
    if not isinstance(value, dict):
        return None
    result = {"status": status, "position": position}
    for key in ("taskId", "jobId", "project", "projectId", "title", "domain", "taskType", "engine", "model", "currentStage", "summary"):
        item = value.get(key)
        if isinstance(item, str) and item:
            result[key] = item[:4000 if key == "summary" else 240]
    if "taskId" not in result and isinstance(value.get("productionTaskId"), str) and value["productionTaskId"]:
        result["taskId"] = value["productionTaskId"][:240]
    item_status = value.get("status")
    if item_status in {"queued", "running"}:
        result["status"] = item_status
    progress = _number(value.get("progress"), minimum=0, maximum=1)
    if progress is not None:
        result["progress"] = progress
    expected_media = _number(value.get("expectedMediaSeconds"), minimum=0)
    if expected_media is None:
        expected_media = _number(value.get("plannedSeconds"), minimum=0)
    if expected_media is not None:
        result["expectedMediaSeconds"] = expected_media
    expected_frames = _number(value.get("expectedFrameCount"), minimum=0, integer=True)
    if expected_frames is not None:
        result["expectedFrameCount"] = expected_frames
    for key in ("queuedAt", "startedAt", "elapsedMs"):
        numeric = _number(value.get(key), minimum=0, integer=True)
        if numeric is not None:
            result[key] = numeric
    return result


def _normalise(value, observed_at_ms):
    if not isinstance(value, dict):
        return {"state": "unavailable", "paused": None, "items": [], "observedAtMs": observed_at_ms}
    items = []
    if isinstance(value.get("items"), list):
        for position, item in enumerate(value["items"]):
            normalised = _item(item, status="queued", position=position)
            if normalised is not None:
                items.append(normalised)
    else:
        current = _item(value.get("current"), status="running", position=0)
        if current is not None:
            items.append(current)
        for position, item in enumerate(value.get("waiting") if isinstance(value.get("waiting"), list) else [], start=1):
            normalised = _item(item, status="queued", position=position)
            if normalised is not None:
                items.append(normalised)
    paused = value.get("paused")
    return {"state": "available", "paused": paused if isinstance(paused, bool) else None, "items": items, "observedAtMs": observed_at_ms}


def read_runtime_queue(data_dir, *, env=None, runner=None, now=None, script_path=None):
    """Read ``queue:list --no-start`` for one profile with a three-second cache."""
    if not isinstance(data_dir, (str, os.PathLike)):
        return {"state": "unavailable", "paused": None, "items": [], "observedAtMs": _now_ms()}
    profile = str(Path(data_dir).expanduser().resolve())
    monotonic_now = time.monotonic()
    cached = _CACHE.get(profile)
    if cached and monotonic_now - cached[0] < TTL_SECONDS:
        return copy.deepcopy(cached[1])
    environment = dict(os.environ if env is None else env)
    root = cli_root(environment, script_path)
    observed_at_ms = _now_ms() if now is None else int(now)
    if root is None:
        result = {"state": "unavailable", "paused": None, "items": [], "observedAtMs": observed_at_ms}
        _CACHE[profile] = (monotonic_now, result)
        return copy.deepcopy(result)
    environment["ROADMUSIC_DATA_DIR"] = profile
    environment["ROADMUSIC_STUDIO_AUTO_OPEN"] = "0"
    argv = ["node", str(root / "cli" / "road-music.js"), "queue:list", "--no-start"]
    try:
        process = (runner or subprocess.run)(argv, cwd=str(root), env=environment, capture_output=True, text=True, timeout=QUEUE_TIMEOUT_SECONDS, check=False)
        response = _response(process)
        result = _normalise(response.get("result"), observed_at_ms) if isinstance(response, dict) and response.get("ok") is True else {"state": _state(process, response), "paused": None, "items": [], "observedAtMs": observed_at_ms}
    except (OSError, subprocess.TimeoutExpired):
        result = {"state": "unavailable", "paused": None, "items": [], "observedAtMs": observed_at_ms}
    _CACHE[profile] = (monotonic_now, result)
    return copy.deepcopy(result)

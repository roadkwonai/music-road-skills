"""Validate explicit review relationships and preserve prior feedback verbatim."""
import json
import hashlib
from datetime import datetime
import math
import os
from pathlib import Path
import re

SHA256 = re.compile(r'[0-9a-f]{64}\Z')
ARTIFACT_TYPES = frozenset({'native-project', 'direction', 'analysis', 'plan', 'validation', 'cues', 'compose', 'report', 'source-archive'})
ARTIFACT_EXTENSIONS = frozenset({'.json', '.txt', '.md', '.zip', '.jizura'})


def validate_sync_checks(checks, files):
    if not isinstance(checks, list) or len(checks) > 500:
        raise ValueError('싱크 검수는 최대 500행 목록이어야 합니다')
    known = {kind: {item.get('sha256') for item in files if item.get('kind') == kind} for kind in ('video', 'captions', 'lyrics')}
    references = {'videoSha256': 'video', 'captionSha256': 'captions', 'lyricsSha256': 'lyrics'}
    allowed = {'line', 'start', 'end', 'status', 'evidence', 'reviewedAt', *references}
    normalized = []
    for row in checks:
        if not isinstance(row, dict) or set(row) - allowed:
            raise ValueError('싱크 검수 행의 필드가 올바르지 않습니다')
        if type(row.get('line')) is not int or not 1 <= row['line'] <= 100000:
            raise ValueError('원가사 행 번호는 1 이상의 정수여야 합니다')
        for key in ('start', 'end'):
            value = row.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('싱크 시각은 0 이상의 유한한 초 단위 값이어야 합니다')
        if row['end'] <= row['start']:
            raise ValueError('싱크 끝 시각은 시작보다 뒤여야 합니다')
        if row.get('status') not in {'confirmed', 'estimated'}:
            raise ValueError('싱크 상태는 확정 또는 추정이어야 합니다')
        if not isinstance(row.get('evidence'), str) or not 1 <= len(row['evidence'].strip()) <= 2000:
            raise ValueError('싱크 판단 근거를 1~2000자로 입력하세요')
        for field, kind in references.items():
            if field in row and (not isinstance(row[field], str) or not SHA256.fullmatch(row[field]) or row[field] not in known[kind]):
                raise ValueError('싱크 검수 대상은 같은 음악의 등록된 영상·가사·자막이어야 합니다')
        if 'reviewedAt' in row:
            stamp = row['reviewedAt']
            if isinstance(stamp, str):
                try:
                    valid_time = datetime.fromisoformat(stamp.replace('Z', '+00:00')).tzinfo is not None
                except ValueError:
                    valid_time = False
            else:
                valid_time = type(stamp) in (int, float) and math.isfinite(stamp) and stamp >= 0
            if not valid_time: raise ValueError('검수 시각은 시간대가 있는 ISO 시각 또는 Unix 초여야 합니다')
        normalized.append({**row, 'evidence': row['evidence'].strip()})
    return normalized


def archive_feedback(project, previous):
    if not isinstance(previous, dict):
        return
    target = Path(project) / 'feedback-history.jsonl'
    if target.is_symlink():
        raise ValueError('검수 이력은 프로젝트 안의 일반 파일이어야 합니다')
    with target.open('a', encoding='utf-8') as stream:
        os.chmod(target, 0o600)
        stream.write(json.dumps(previous, ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def feedback_history(project, management=None):
    target = Path(project) / 'feedback-history.jsonl'
    lines = []
    if target.exists() and not target.is_symlink():
        with target.open('rb') as stream:
            size = target.stat().st_size
            stream.seek(max(0, size - 256 * 1024))
            if stream.tell():
                stream.readline()
            lines = stream.read().splitlines()[-20:]
    entries = []
    for line in lines:
        try:
            value = json.loads(line)
            if isinstance(value, dict): entries.append(value)
        except (ValueError, UnicodeDecodeError):
            continue
    if management is not None:
        project_id = hashlib.sha256(str(Path(project).resolve()).encode()).hexdigest()
        with management.transaction() as connection:
            rows = connection.execute("SELECT before_json FROM management_events WHERE project_id=? AND action='feedback-change' ORDER BY id DESC LIMIT 20", (project_id,)).fetchall() if management._has_table(connection, 'management_events') else []
        for row in reversed(rows):
            value = json.loads(row[0]) if row[0] is not None else None
            if isinstance(value, dict) and value not in entries:
                entries.append(value)
    return entries[-20:]

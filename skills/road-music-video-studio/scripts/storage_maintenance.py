"""Explicit maintenance of the current Road Music workspace, with durable plans."""
from __future__ import annotations

from contextlib import contextmanager
import json
import gzip
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import time

from management_db import ManagementDBError
from storage_manager import StorageError, PLAN_TTL, MAX_JSON, _atomic_json, _json_read, _id, _lock_for, _now, _iso
from storage_packaging import TRUSTED_ROOT, is_workspace, git_available
from storage_scan import WorkspaceScan
from storage_git import GitMaintenance
from storage_verification import VerificationMaintenance
from storage_artifacts import ArtifactMaintenance
from storage_retirement import RetirementMaintenance


def _fingerprint(value):
    return _id(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False))


class StorageMaintenance:
    @staticmethod
    def status(manager, root=None):
        workspace = Path(root) if root is not None else TRUSTED_ROOT
        if workspace is None:
            unavailable = '현재 설치에는 신뢰할 수 있는 Road Music 작업 폴더가 없습니다.'
            return {'workspace': None, 'available': False, 'capabilities': {key: {'enabled': False, 'reason': unavailable} for key in ('workspaceScan', 'retirement', 'projectCache', 'projectFinish', 'verification', 'artifacts', 'sharedVideoCache', 'git')},
                    'scanCache': {'kind': 'compressed-inventory', 'path': str(manager.data_dir / 'storage-scans'), 'writesOnStatus': False},
                    'history': {'kind': 'sqlite-metadata', 'path': None, 'writesOnStatus': False}}
        available = is_workspace(workspace)
        reason = None if available else '현재 설치에는 신뢰할 수 있는 Road Music 작업 폴더가 없습니다.'
        output = workspace / 'Output'
        output_ready = available and output.is_dir() and not output.is_symlink()
        repository = available and git_available(workspace)
        from storage_verification import PROFILES, DMG_ROOTS, DMG_DOWNLOAD
        from storage_artifacts import RESEARCH, HIGHRES, HARNESS, SIMPLE, QA, BEFORE_ROOTS, ARCHIVE
        verification_paths = [workspace / value[1] for value in PROFILES] + [workspace / value / DMG_DOWNLOAD for value in DMG_ROOTS]
        verification_ready = available and any(path.exists() and not path.is_symlink() for path in verification_paths)
        artifact_roots = (RESEARCH, HIGHRES, HARNESS, SIMPLE, QA, *BEFORE_ROOTS, ARCHIVE)
        artifacts_ready = available and any((workspace / value).exists() and not (workspace / value).is_symlink() for value in artifact_roots)
        try: registered = [value for value in manager._read().get('projects', {}).values() if isinstance(value, dict)]
        except StorageError: registered = []
        finish_ready = available and any(value.get('state') in {'completed', 'archived'} and isinstance(value.get('path'), str) and Path(value['path']).is_relative_to(workspace / '.roadmusic' / 'work') for value in registered)
        return {'workspace': str(workspace), 'available': available, 'capabilities': {
            'workspaceScan': {'enabled': available, 'reason': reason},
            'retirement': {'enabled': output_ready, 'reason': None if output_ready else reason or 'Output 폴더가 없어 이전 제작 자료를 점검할 수 없습니다.'},
            'projectCache': {'enabled': bool(registered), 'reason': None if registered else '등록된 프로젝트 캐시가 없습니다.'},
            'projectFinish': {'enabled': finish_ready, 'reason': None if finish_ready else '완료·보관 상태의 정리 가능한 private 작업 프로젝트가 없습니다.'},
            'verification': {'enabled': verification_ready, 'reason': None if verification_ready else '현재 설치에 알려진 설치 검증 경로가 없습니다.'},
            'artifacts': {'enabled': artifacts_ready, 'reason': None if artifacts_ready else '현재 작업 폴더에 알려진 제작·참조 자료 경로가 없습니다.'},
            'sharedVideoCache': {'enabled': False, 'reason': '현재 앱 프로필이 유휴 상태일 때 공용 캐시 점검을 직접 실행해 확인합니다.'},
            'git': {'enabled': repository, 'reason': None if repository else 'Git 저장소가 없어 Git 공간 관리를 사용할 수 없습니다.', 'inspection': 'not-requested'},
        }, 'scanCache': {'kind': 'compressed-inventory', 'path': str(manager.data_dir / 'storage-scans'), 'writesOnStatus': False},
                'history': {'kind': 'sqlite-metadata', 'path': str(manager.management_db.path), 'writesOnStatus': False}}

    def __init__(self, manager, root=None):
        self.manager = manager
        self.root = Path(root) if root is not None else TRUSTED_ROOT
        if self.root is None or not is_workspace(self.root):
            raise StorageError('현재 소스 작업 폴더에서만 작업 폴더 정리를 사용할 수 있습니다.', 'maintenance_unavailable')
        self.plan_dir = manager.data_dir / 'storage-maintenance-plans'
        self.audit_dir = self.root / '.roadmusic' / 'maintenance'
        self.lock_path = self.root / '.roadmusic' / '.maintenance.lock'

    def _directory(self, path):
        path = Path(path)
        for item in [path, *path.parents]:
            if item == self.root.parent or item == self.manager.data_dir.parent: break
            if item.is_symlink(): raise StorageError('유지보수 경로의 symlink는 허용하지 않습니다.', 'unsafe_path')
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir() or path.resolve() != path: raise StorageError('유지보수 폴더가 안전하지 않습니다.', 'unsafe_path')

    @contextmanager
    def _lock(self):
        if os.name != 'posix': raise StorageError('이 플랫폼의 작업 폴더 유지보수는 아직 지원하지 않습니다.', 'unsupported_platform')
        self._directory(self.lock_path.parent)
        lock = _lock_for(self.lock_path)
        if not lock.acquire(blocking=False): raise StorageError('다른 작업 폴더 정리가 진행 중입니다.', 'busy')
        descriptor = None
        try:
            import fcntl
            descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1: raise StorageError('유지보수 잠금 파일이 안전하지 않습니다.', 'unsafe_path')
            try: fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error: raise StorageError('다른 작업 폴더 정리가 진행 중입니다.', 'busy') from error
            yield
        finally:
            if descriptor is not None: os.close(descriptor)
            lock.release()

    @staticmethod
    def _public_candidate(value):
        public = {'scope': value.get('scope', 'verification'), **{key: value[key] for key in ('id', 'path', 'absolutePath', 'kind', 'description', 'fileCount', 'bytes', 'allocatedBytes', 'evidence') if key in value}}
        if public['scope'] != 'retirement':
            return public
        files = value.get('files')
        if isinstance(files, list):
            public['retirementFileList'] = [{'path': item['relativePath'], 'bytes': item['bytes']} for item in files
                                            if isinstance(item, dict) and isinstance(item.get('relativePath'), str) and isinstance(item.get('bytes'), int) and item['bytes'] >= 0]
        recovery = value.get('evidence', {}).get('archiveRecovery') if isinstance(value.get('evidence'), dict) else None
        if isinstance(recovery, list):
            unique = {}
            for plan in recovery:
                if not isinstance(plan, dict) or not isinstance(plan.get('members'), list):
                    continue
                for member in plan['members']:
                    if not isinstance(member, dict) or member.get('canonicalMember'):
                        continue
                    digest = member.get('sha256'); bytes_ = member.get('size')
                    if isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest) and isinstance(bytes_, int) and bytes_ >= 0:
                        unique.setdefault((digest, bytes_), bytes_)
            public['archiveRecovery'] = {'uniqueMemberCount': len(unique), 'uniqueMemberBytes': sum(unique.values())}
            public['grossAllocatedBytes'] = value.get('grossAllocatedBytes', value.get('allocatedBytes', 0))
            public['estimateIsUpperBound'] = True
        return public

    @staticmethod
    def _public_git(value):
        objects = value.get('objects', {})
        return {**{key: value[key] for key in ('available', 'objectsBytesAllocated', 'freeBytes', 'blocked', 'reasons', 'locks', 'writerPids', 'cutoff') if key in value},
                'estimatedReclaimableLogicalBytes': objects.get('unreachableLogicalBytes', value.get('estimatedReclaimableLogicalBytes', 0)),
                'knownOldLooseLogicalBytes': objects.get('oldLooseUnreachableLogicalBytes', 0),
                'unreachableObjects': objects.get('unreachableCount', value.get('unreachableObjects', 0)),
                'reachableObjects': objects.get('count', 0) - objects.get('unreachableCount', 0),
                'estimateIsUpperBound': True}

    def list(self, params):
        if (not isinstance(params, dict) or set(params) - {'includeRetirement', 'scope'} or
                'includeRetirement' in params and type(params['includeRetirement']) is not bool or
                params.get('scope') not in {None, 'retirement', 'git'}):
            raise StorageError('includeRetirement 또는 retirement·git 범위만 지정할 수 있습니다.')
        capabilities = self.status(self.manager, self.root)['capabilities']
        scope = params.get('scope')
        if scope and not capabilities[scope]['enabled']:
            raise StorageError(capabilities[scope]['reason'], 'maintenance_unavailable')
        scan = WorkspaceScan(self.root, self.manager.data_dir).scan()
        if not scan.get('complete'):
            return {'workspace': str(self.root), 'capabilities': capabilities, 'scan': scan, 'git': {'blocked': True, 'reasons': ['전체 스캔이 완료되지 않았습니다.']}, 'candidates': [], 'blocked': scan.get('errors', []), 'summary': {}}
        if params.get('scope') == 'retirement':
            retirement = RetirementMaintenance(self.root, self.manager).inspect()
            return {'workspace': str(self.root), 'capabilities': capabilities, 'scan': scan, 'git': {'available': False, 'blocked': False, 'reasons': [], 'inspection': 'not-requested'},
                    'candidates': [self._public_candidate(value) for value in retirement.get('candidates', [])],
                    'blocked': retirement.get('blocked', []), 'retirementReview': retirement.get('review', []),
                    'summary': {'verificationCandidates': 0, 'verificationBytes': 0, 'verificationAllocatedBytes': 0,
                                'artifactCandidates': 0, 'artifactAllocatedBytes': 0, 'gitEstimatedLogicalBytes': 0,
                                'retirementCandidates': len(retirement.get('candidates', [])),
                                'retirementAllocatedBytes': sum(value.get('allocatedBytes', 0) for value in retirement.get('candidates', []))},
                    'protected': ['현재 프로그램·모델·원음·최종 결과물', '현재 편집·승인·검수·복구 이력'],
                    'otherFiles': '이 빠른 점검은 Git·설치 검증·참조 자료 분석을 생략하고 최종본 외 제작 자료만 확인합니다.'}
        if params.get('scope') == 'git':
            try: git = GitMaintenance(self.root).inspect()
            except (StorageError, OSError, ValueError) as error:
                git = {'blocked': True, 'reasons': [str(error)], 'available': False}
            return {'workspace': str(self.root), 'capabilities': capabilities, 'scan': scan, 'git': {**self._public_git(git), 'repository': True, 'inspection': 'requested'},
                    'candidates': [], 'blocked': ([{'scope': 'git', 'reason': str(reason)} for reason in git.get('reasons', [])] if git.get('blocked') else []),
                    'retirementReview': [], 'summary': {'verificationCandidates': 0, 'verificationBytes': 0, 'verificationAllocatedBytes': 0,
                                                        'artifactCandidates': 0, 'artifactAllocatedBytes': 0, 'retirementCandidates': 0,
                                                        'retirementAllocatedBytes': 0, 'gitEstimatedLogicalBytes': git.get('estimatedReclaimableLogicalBytes', 0)},
                    'protected': ['현재 프로그램·모델·원음·최종 결과물', 'Git refs·reflog·모든 worktree index와 최근 24시간 객체'],
                    'otherFiles': '개발자 요청으로 Git 객체 상태만 점검했습니다. 자동 정리·fsck·prune은 실행하지 않습니다.'}
        blocked = []
        git = {'available': False, 'blocked': False, 'reasons': [], 'repository': capabilities['git']['enabled'], 'inspection': 'not-requested'}
        verification = VerificationMaintenance(self.root).inspect() if capabilities['verification']['enabled'] else {'candidates': [], 'blocked': []}
        artifacts = ArtifactMaintenance(self.root, self.manager).inspect() if capabilities['artifacts']['enabled'] else {'candidates': [], 'blocked': []}
        retirement = RetirementMaintenance(self.root, self.manager).inspect() if params.get('includeRetirement') and capabilities['retirement']['enabled'] else {'candidates': [], 'blocked': [], 'review': []}
        blocked.extend(verification.get('blocked', []))
        blocked.extend(artifacts.get('blocked', []))
        blocked.extend(retirement.get('blocked', []))
        candidates = verification.get('candidates', []) + artifacts.get('candidates', []) + retirement.get('candidates', [])
        return {'workspace': str(self.root), 'capabilities': capabilities, 'scan': scan, 'git': {**self._public_git(git), 'repository': git['repository'], 'inspection': git['inspection']},
                'candidates': [self._public_candidate(value) for value in candidates], 'blocked': blocked, 'retirementReview': retirement.get('review', []),
                'summary': {'verificationCandidates': len(verification.get('candidates', [])), 'verificationBytes': sum(value.get('bytes', 0) for value in verification.get('candidates', [])),
                            'verificationAllocatedBytes': sum(value.get('allocatedBytes', 0) for value in verification.get('candidates', [])),
                            'retirementCandidates': len(retirement.get('candidates', [])), 'retirementAllocatedBytes': sum(value.get('allocatedBytes', 0) for value in retirement.get('candidates', [])),
                            'artifactCandidates': len(artifacts.get('candidates', [])), 'artifactAllocatedBytes': sum(value.get('allocatedBytes', 0) for value in artifacts.get('candidates', [])),
                            'gitEstimatedLogicalBytes': git.get('estimatedReclaimableLogicalBytes', 0)},
                'protected': ['현재 프로그램·모델·원음·최종 결과물', '현재 편집·승인·검수·복구 이력', 'Git refs·reflog·모든 worktree index와 최근 24시간 객체'],
                'otherFiles': '과거 제작·참조 자료는 별도 명시 선택만 허용합니다. 원본·전체 시트·최종 납품·버전별 코드·검수 판정과 미확인 파일은 보호합니다.'}

    def _engine(self, scope):
        if scope == 'retirement': return RetirementMaintenance(self.root, self.manager)
        return ArtifactMaintenance(self.root, self.manager) if scope == 'artifacts' else VerificationMaintenance(self.root)

    def _receipt_plan(self, plan):
        if plan['scope'] not in {'artifacts', 'retirement'}: return plan
        path = self.audit_dir / (plan['planId'] + '.files.jsonl.gz')
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(descriptor, 'wb') as output:
            with gzip.GzipFile(fileobj=output, mode='wb', mtime=0) as compressed:
                for candidate in plan['candidates']:
                    for item in candidate.get('files', []):
                        compressed.write((json.dumps({'candidateId': candidate['id'], **item}, ensure_ascii=False, separators=(',', ':')) + '\n').encode())
            output.flush(); os.fsync(output.fileno())
        return {**plan, 'candidates': [{key: value for key, value in candidate.items() if key != 'files'} for candidate in plan['candidates']], 'fileInventoryPath': str(path)}

    def preview(self, params):
        if not isinstance(params, dict) or set(params) - {'scope', 'candidateIds', 'scanId'}: raise StorageError('scope와 후보 ID만 지정할 수 있습니다.')
        scope = params.get('scope')
        if scope not in {'git', 'verification', 'artifacts', 'retirement'}: raise StorageError('scope는 git, verification, artifacts 또는 retirement이어야 합니다.')
        capability = self.status(self.manager, self.root)['capabilities'][scope]
        if not capability['enabled']: raise StorageError(capability['reason'], 'maintenance_unavailable')
        scan = WorkspaceScan(self.root, self.manager.data_dir).load(params.get('scanId'))
        if not scan.get('complete'): raise StorageError('전체 스캔을 완료한 뒤 정리 계획을 만드세요.', 'scan_required')
        with self._lock():
            plan = {'schemaVersion': 1, 'workspace': str(self.root), 'scope': scope, 'createdAt': _now(),
                    'expiresAt': min(_now() + PLAN_TTL, scan.get('expiresAt', _now() + PLAN_TTL)), 'scanId': params.get('scanId'), 'scanFingerprint': scan.get('fingerprint'), 'state': 'ready', 'planId': secrets.token_hex(24)}
            if scope == 'git':
                if 'candidateIds' in params: raise StorageError('Git 정리에는 복제본 후보를 함께 지정할 수 없습니다.')
                git = GitMaintenance(self.root).inspect()
                if git.get('blocked'): raise StorageError('Git 보호 조건을 확인하세요: ' + str(git['blocked'])[:2000], 'blocked')
                plan['git'] = git
                public_git = self._public_git(git)
                public = {'entries': [], 'fileCount': public_git['unreachableObjects'], 'bytes': public_git['estimatedReclaimableLogicalBytes'],
                          'estimatedReclaimableBytes': public_git['estimatedReclaimableLogicalBytes'], 'git': public_git,
                          'warning': 'Git 예상량은 압축 전 객체 크기이며 실제 확보량이 아닙니다. 정리 중에는 다른 Git 작업을 실행하지 마세요.'}
            else:
                selected = params.get('candidateIds')
                if not isinstance(selected, list) or not selected or len(selected) > 100 or any(not isinstance(value, str) for value in selected) or len(set(selected)) != len(selected):
                    raise StorageError('정리할 검증 복제본의 서로 다른 후보 ID가 필요합니다.')
                inventory = self._engine(scope).inspect()
                candidates = {value['id']: value for value in inventory.get('candidates', [])}
                if any(value not in candidates for value in selected): raise StorageError('후보가 변경됐거나 보호됩니다. 다시 점검하세요.', 'stale_plan')
                plan['candidates'] = [candidates[value] for value in selected]
                public = {'entries': [self._public_candidate(value) for value in plan['candidates']],
                          'fileCount': sum(value.get('fileCount', 0) for value in plan['candidates']),
                          'bytes': sum(value.get('bytes', 0) for value in plan['candidates']),
                          'estimatedReclaimableBytes': sum(value.get('allocatedBytes', 0) for value in plan['candidates'])}
            plan['scanSummary'] = {key: scan[key] for key in ('scanId', 'workspace', 'createdAt', 'expiresAt', 'complete', 'totals', 'fingerprint') if key in scan}
            # The exact candidates are already stored above; duplicating the UI file list can exceed the state limit.
            plan['public'] = {key: value for key, value in public.items() if key != 'entries'}
            self._directory(self.plan_dir)
            for old in self.plan_dir.glob('*.json'):
                if old.is_symlink() or not re.fullmatch(r'[0-9a-f]{48}\.json', old.name): continue
                previous = _json_read(old, {})
                if previous.get('state') == 'used' or previous.get('expiresAt', 0) < _now(): old.unlink()
            _atomic_json(self.plan_dir / (plan['planId'] + '.json'), plan)
            return {'planId': plan['planId'], 'scope': scope, 'workspace': str(self.root), 'scanId': params.get('scanId'), 'expiresAt': plan['expiresAt'], 'blocked': [], **public}

    def cleanup(self, params):
        if not isinstance(params, dict) or set(params) - {'planId', 'confirm'} or params.get('confirm') is not True:
            raise StorageError('같은 미리보기 planId와 명시 확인이 필요합니다.', 'confirm_required')
        plan_id = params.get('planId')
        if not isinstance(plan_id, str) or not re.fullmatch(r'[0-9a-f]{48}', plan_id): raise StorageError('정리 계획이 올바르지 않습니다.', 'invalid_plan')
        with self._lock():
            self._directory(self.plan_dir)
            path = self.plan_dir / (plan_id + '.json')
            plan = _json_read(path, None)
            if not isinstance(plan, dict) or plan.get('state') != 'ready' or plan.get('workspace') != str(self.root) or plan.get('expiresAt', 0) <= _now():
                raise StorageError('사용되었거나 만료된 계획입니다. 새 미리보기를 만드세요.', 'invalid_plan')
            capability = self.status(self.manager, self.root)['capabilities'].get(plan.get('scope'), {})
            if not capability.get('enabled'): raise StorageError(capability.get('reason') or '현재 설치에서 사용할 수 없는 정리 범위입니다.', 'maintenance_unavailable')
            scan = WorkspaceScan(self.root, self.manager.data_dir).load(plan.get('scanId'))
            if not scan.get('complete') or scan.get('fingerprint') != plan.get('scanFingerprint'): raise StorageError('전체 스캔이 만료되거나 변경됐습니다.', 'stale_scan')
            if plan.get('scope') not in {'git', 'verification', 'artifacts', 'retirement'}: raise StorageError('정리 범위가 올바르지 않습니다.', 'invalid_plan')
            if plan['scope'] != 'git':
                current = {value['id']: value for value in self._engine(plan['scope']).inspect().get('candidates', [])}
                if any(value['id'] not in current or _fingerprint(current[value['id']]) != _fingerprint(value) for value in plan['candidates']):
                    raise StorageError('계획 뒤 복제본 또는 보호 상태가 변경됐습니다.', 'stale_plan')
            plan['state'] = 'used'
            _atomic_json(path, plan)
            self._directory(self.audit_dir)
            receipt_path = self.audit_dir / (plan_id + '.json')
            receipt_plan = self._receipt_plan(plan)
            _atomic_json(receipt_path, {'at': _iso(), 'status': 'intent', 'plan': receipt_plan})
            self.manager._audit(self.root, 'maintenance-cleanup-intent', {'scope': plan['scope'], 'planId': plan_id, 'manifestPath': str(receipt_path),
                                                                         'fileCount': plan['public']['fileCount'], 'estimatedBytes': plan['public']['bytes']})
            before_disk_free = shutil.disk_usage(self.root).free
            try:
                result = GitMaintenance(self.root).cleanup(plan['git']) if plan['scope'] == 'git' else self._engine(plan['scope']).cleanup(plan['candidates'])
            except (StorageError, OSError, ValueError) as error:
                try:
                    _atomic_json(receipt_path, {'at': _iso(), 'status': 'failed', 'plan': receipt_plan, 'error': str(error)[:2000]})
                    self.manager._audit(self.root, 'maintenance-cleanup-failed', {'scope': plan['scope'], 'planId': plan_id, 'message': str(error)[:2000]})
                except (StorageError, OSError): pass
                raise
            result = {'scope': plan['scope'], 'removedFiles': 0, 'freedBytes': result.get('freedAllocatedBytes', 0), 'skipped': [], 'warnings': [], **result}
            result['warnings'] = list(result.get('warnings') or [])
            result.setdefault('diskFreeDeltaBytes', shutil.disk_usage(self.root).free - before_disk_free)
            if plan['scope'] == 'git':
                result['warnings'] = [value.replace('pack 안의 미참조 객체는 사전 논리 추정치에 포함하지 않았습니다', '논리 상한에 포함된 최근 24시간 객체는 보존했습니다') for value in result['warnings']]
                result['beforeAllocatedBytes'] = result.get('beforeRepoObjectAllocatedBytes', result.get('beforeAllocatedBytes'))
                result['afterAllocatedBytes'] = result.get('afterRepoObjectAllocatedBytes', result.get('afterAllocatedBytes'))
                result['freedBytes'] = result.get('removedLogicalBytes')
                if result['beforeAllocatedBytes'] is not None and result['afterAllocatedBytes'] is not None:
                    result['allocationDeltaBytes'] = result['beforeAllocatedBytes'] - result['afterAllocatedBytes']
                result['freedBytesMeaning'] = 'Git에서 제거된 객체 논리량(미측정 시 null). 실제 할당 감소는 freedAllocatedBytes.'
            result['auditPath'] = str(self.manager.management_db.path)
            result['manifestPath'] = str(receipt_path)
            try:
                _atomic_json(receipt_path, {'at': _iso(), 'status': 'completed', 'plan': receipt_plan, 'result': result})
                self.manager._audit(self.root, 'maintenance-cleanup', {'scope': plan['scope'], 'planId': plan_id,
                    **{key: result[key] for key in ('removedFiles', 'removedObjects', 'freedBytes', 'freedAllocatedBytes', 'diskFreeDeltaBytes', 'manifestPath') if key in result}})
            except (StorageError, OSError) as error: result['warnings'].append('정리 결과는 완료됐으나 감사 기록 저장에 실패했습니다: ' + str(error))
            return result

    def history(self, params):
        if params: raise StorageError('유지보수 이력은 별도 입력값을 받지 않습니다.')
        path = self.root / '.roadmusic' / 'history.jsonl'
        legacy = []
        if path.exists() or path.is_symlink():
            if path.parent.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
                raise StorageError('이력 파일이 안전하지 않거나 조회 한도를 초과했습니다.', 'unsafe_path')
            try:
                with path.open(encoding='utf-8') as stream:
                    for line in stream:
                        value = json.loads(line)
                        if not isinstance(value, dict):
                            raise ValueError('invalid history event')
                        if str(value.get('action', '')).startswith(('maintenance-', 'mv-project-cleanup', 'sweep-')):
                            legacy.append(value)
            except (OSError, UnicodeDecodeError, ValueError) as error:
                raise StorageError('기존 유지보수 이력을 읽을 수 없습니다.', 'history_unavailable') from error
        try:
            with self.manager.management_db.transaction() as connection:
                rows = connection.execute(
                    "SELECT id,action,after_json,created_at FROM management_events WHERE path=? AND (action LIKE 'maintenance-%' OR action LIKE 'mv-project-cleanup%' OR action LIKE 'sweep-%') ORDER BY id DESC LIMIT 200", (str(self.root),)
                ).fetchall() if connection is not None else []
            events = [{**(json.loads(row[2]) if row[2] else {}), 'id': row[0], 'action': row[1], 'at': _iso(row[3])} for row in reversed(rows)]
            return {'events': [*legacy, *events][-200:]}
        except (ManagementDBError, json.JSONDecodeError) as error:
            raise StorageError('유지보수 이력을 읽을 수 없습니다.', 'history_unavailable') from error

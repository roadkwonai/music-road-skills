"""Selective compaction of audited reference/QA datasets; never automatic history deletion."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

from storage_manager import StorageError, _bounded_files, _id, _snapshot, MAX_JSON
from storage_verification import VerificationMaintenance, _digest, _json, _allocated

RESEARCH = 'Output/kpop-mainstream-mv-research-20261016'
HIGHRES = 'Output/kpop-mainstream-mv-highres-20261016'
HARNESS = 'Output/mv-harness-reference-20261016'
SIMPLE = 'Output/reference-frame-research-20261015'
CASES = ('blackpink-whistle', 'blackpink-shut-down', 'rescene-pinball', 'rescene-glow-up', 'itzy-wannabe', 'itzy-loco')
FRAME_ROOTS = tuple(f'{RESEARCH}/{case}/frames-v2' for case in CASES) + tuple(f'{HARNESS}/{case}' for case in ('armageddon-frames', 'armageddon-frames-v2', 'manchild-frames-v2'))
QA = 'Output/showreel-tomorrow-full-rebuild-20261018/project/qa'
BEFORE_ROOTS = ('Output/showreel-tomorrow-full-rebuild-20261018/before', 'Output/showreel-playlist-rebuild-20261018/before')
ARCHIVE = 'Output/skills-release-review-20261018/final-dist/MusicRoad-Skills-0.1.1.zip'
BINARY = {'.mp4', '.jpg', '.png', '.woff2', '.ttf'}
MARKERS = {'studio-project.json', 'production.json', 'native-production.json', 'playlist.json', 'input.json', 'timeline.json', 'media.json', 'composition.json'}


class ArtifactMaintenance(VerificationMaintenance):
    def __init__(self, root, manager, *, active_check=None):
        self.manager = manager
        super().__init__(root, active_check=active_check)
        self.digests = {}
        self.archive_members = None
        self.references = None

    def _active(self, path):
        if super()._active(path): return True
        data = self.manager._read()
        for project_id, project in data.get('projects', {}).items():
            parent = Path(project['path']).resolve(strict=False)
            if (path == parent or parent in path.parents or path in parent.parents) and self.manager._busy(data, project_id): return True
        return False

    def _proof_file(self, path, digest=None):
        path = self._path(str(Path(path).relative_to(self.root)))
        before = _snapshot(path)
        key = (str(path), before['inode'], before['bytes'], before['mtimeNs'])
        actual = self.digests.get(key)
        if actual is None:
            actual = _digest(path); self.digests[key] = actual
        if before != _snapshot(path) or digest is not None and actual != digest:
            raise StorageError('보존 원본/납품/검수 근거의 해시가 다릅니다.', 'changed_proof')
        return {'path': str(path.relative_to(self.root)), 'sha256': actual}

    def _production_references(self):
        if self.references is not None: return self.references
        self.references = []
        excluded = [self.root / p for p in (RESEARCH, HIGHRES, HARNESS, SIMPLE, *BEFORE_ROOTS)]
        search = [self.root / 'Output', self.root / '.harness']
        data = self.manager._read()
        for value in data.get('projects', {}).values():
            path = Path(value['path'])
            if path != self.root and self.root not in path.parents: search.append(path)
        total = count = 0
        for root in search:
            if not root.exists(): continue
            for base, dirs, names in os.walk(root, followlinks=False):
                dirs[:] = [name for name in dirs if name not in {'node_modules', '.git', 'engines', 'models', '.roadmusic'} and not (Path(base) / name).is_symlink() and Path(base) / name not in excluded]
                if Path(base) in excluded: dirs[:] = []; continue
                for name in sorted(set(names) & MARKERS):
                    path = Path(base) / name
                    if path.is_symlink(): raise StorageError('제작 참조가 symlink여서 보호합니다.', 'unsafe_reference')
                    count += 1; total += path.stat().st_size
                    if count > 5000 or path.stat().st_size > MAX_JSON or total > 64 * 1024 * 1024: raise StorageError('제작 참조 조회 한도를 초과해 보호합니다.', 'reference_limit')
                    value = _json(path)
                    def strings(item):
                        if isinstance(item, str) and not item.startswith(('https://', 'http://')) and Path(item).suffix.casefold() in (BINARY | {'.webm', '.mkv', '.wav', '.mp3'}):
                            for raw in (Path(item), path.parent / item, self.root / item):
                                if raw.is_absolute(): self.references.append(raw.resolve(strict=False))
                        elif isinstance(item, dict):
                            for child in item.values(): strings(child)
                        elif isinstance(item, list):
                            for child in item: strings(child)
                    strings(value)
        return self.references

    def _unused(self, path):
        if any(value == path or path in value.parents for value in self._production_references()):
            raise StorageError('현재 제작 입력/타임라인이 참조하는 자료는 보존합니다.', 'production_reference')
        if self.active_check(path): raise StorageError('열린 파일/진행 중인 제작은 보존합니다.', 'active_or_unsafe')

    def _candidate(self, path, files, kind, description, proof, preserved):
        self._unused(path)
        snapshots = []
        for file in sorted(files):
            value = _snapshot(file)
            if value['nlink'] != 1: raise StorageError('다른 파일과 hardlink를 공유해 보호합니다.', 'shared_hardlink')
            value.pop('path'); value['relativePath'] = str(file.relative_to(self.root)); snapshots.append(value)
        if not snapshots: return None
        evidence = {'preserved': preserved, 'proof': proof, 'policy': description}
        value = {'id': _id('artifacts\0' + str(path)), 'scope': 'artifacts', 'path': str(path.relative_to(self.root)), 'absolutePath': str(path), 'kind': kind,
                 'description': description, 'fileCount': len(files), 'bytes': sum(x['bytes'] for x in snapshots), 'allocatedBytes': sum(_allocated(x) for x in files),
                 'evidence': evidence, 'files': snapshots}
        value['fingerprint'] = _id(json.dumps({'files': snapshots, 'evidence': evidence}, sort_keys=True, ensure_ascii=False))
        return value

    def _frames(self, relative, simple=False):
        parent = self._path(relative); path = self._path(relative + '/frames')
        if not path.exists(): return None
        files = sorted(_bounded_files(path))
        pattern = r'f[0-9]{5}\.jpg' if simple else r'frame-[0-9]{8}\.jpg'
        if any(not re.fullmatch(pattern, file.name) or file.parent != path for file in files): raise StorageError('알 수 없는 분석 프레임 파일을 보호합니다.', 'unknown_file')
        if len(files) <= 3: return None
        manifest = parent / ('frame-verification.json' if simple else 'manifest.json'); record = _json(manifest)
        if simple:
            if record.get('contiguousFrameIndices') is not True or record.get('count') != len(files): raise StorageError('프레임 연속성/수량 근거가 다릅니다.', 'missing_proof')
            source = parent / 'reference-original-video.mp4'; expected = None
        else:
            source_record = record.get('source', {})
            if record.get('extraction_complete') is not True or record.get('extracted_frames') != len(files) or not re.fullmatch(r'[0-9a-f]{64}', str(source_record.get('sha256', ''))): raise StorageError('완료된 추출 manifest가 필요합니다.', 'missing_proof')
            source = Path(source_record['path']); expected = source_record['sha256']
        proof = [self._proof_file(manifest), self._proof_file(source, expected)]
        sheets = _bounded_files(parent / 'sheets')
        if not sheets: raise StorageError('보존할 전체 contact sheet가 없습니다.', 'missing_proof')
        proof.extend(self._proof_file(file) for file in sheets)
        for name in ('frame-index.jsonl', 'sheet-index.json', 'frame-metrics.json', 'frame-timestamps.json', 'source-capture.json'):
            if (parent / name).exists(): proof.append(self._proof_file(parent / name))
        if not simple:
            index = parent / 'frame-index.jsonl'
            if index.stat().st_size > MAX_JSON: raise StorageError('프레임 색인이 너무 큽니다.', 'reference_limit')
            rows = [json.loads(line) for line in index.read_text().splitlines()]
            if len(rows) != len(files): raise StorageError('프레임 색인 수량이 다릅니다.', 'changed_proof')
            for i, (row, file) in enumerate(zip(rows, files)):
                if row.get('frame_index') != i or row.get('thumbnail') != 'frames/' + file.name: raise StorageError('프레임 색인/파일 경로가 다릅니다.', 'changed_proof')
                if 'thumbnail_sha256' in row: self._proof_file(file, row['thumbnail_sha256'])
            integrity = record.get('integrity', {})
            for key, name in [('frame_index_sha256', 'frame-index.jsonl'), ('sheet_index_sha256', 'sheet-index.json'), ('index_html_sha256', 'index.html')]:
                if key in integrity: self._proof_file(parent / name, integrity[key])
        keep = {files[0], files[len(files) // 2], files[-1]}
        return self._candidate(path, [file for file in files if file not in keep], 'analysis-frames', '원본·추출 지표·전체 시트·처음/중간/끝 프레임 보존; 나머지는 원본에서 다시 추출 가능', proof, [str(p.relative_to(self.root)) for p in sorted(keep)] + [str(source.relative_to(self.root)), str((parent / 'sheets').relative_to(self.root))])

    def _qa(self, relative):
        path = self._path(relative); files = sorted(_bounded_files(path))
        if any(file.parent != path or file.suffix != '.png' for file in files): raise StorageError('알 수 없는 검수 자료를 보호합니다.', 'unknown_file')
        if len(files) <= 3: return None
        project = self.root / QA; report = project / 'tomorrow-full-final-render.json'; record = _json(report)
        if record.get('schemaVersion') != 1 or record.get('draft') is not False or not isinstance(record.get('outputs'), dict) or not record['outputs'] or not record.get('qaReports'): raise StorageError('완성 납품 해시/검수 기록이 필요합니다.', 'missing_proof')
        proof = [self._proof_file(report)]
        for rel, digest in {**record['outputs'], **record['qaReports']}.items():
            if not isinstance(rel, str) or Path(rel).is_absolute() or '..' in Path(rel).parts or not rel.startswith(('out/', 'qa/')) or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest): raise StorageError('납품 증거 경로가 안전하지 않습니다.', 'unsafe_path')
            proof.append(self._proof_file(project.parent / rel, digest))
        keep = {files[0], files[len(files) // 2], files[-1]}
        return self._candidate(path, [file for file in files if file not in keep], 'qa-detail-frames', '최종 납품 해시·보고서·전체 요약 시트·구간별 대표 프레임 보존', proof, [str(p.relative_to(self.root)) for p in sorted(keep)] + [str(report.relative_to(self.root)), 'qa 루트 요약 시트·final-boundaries·encoded proof 보존'])

    def _archive(self):
        if self.archive_members is not None: return self.archive_members
        archive = self._path(ARCHIVE); proof = self._proof_file(archive); members = {}
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            if len(infos) > 2000 or sum(x.file_size for x in infos) > 1024 ** 3: raise StorageError('배포 ZIP 조회 한도를 초과했습니다.', 'archive_limit')
            manifest = json.loads(z.read('MusicRoad-Skills-0.1.1/manifest.json'))
            if manifest.get('name') != 'music-road-skills' or manifest.get('version') != '0.1.1': raise StorageError('보존 ZIP의 제품/버전 표지가 다릅니다.', 'missing_proof')
            for info in infos:
                if Path(info.filename).suffix not in BINARY or info.is_dir(): continue
                digest = hashlib.sha256()
                with z.open(info) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
                members[(info.file_size, digest.hexdigest())] = info.filename
        self.archive_members = (proof, members)
        return self.archive_members

    def _before(self, relative):
        path = self._path(relative); files = _bounded_files(path)
        proof, members = self._archive(); selected = []; recovery = []
        for file in files:
            if file.suffix not in BINARY: continue
            digest = self._proof_file(file)['sha256']; member = members.get((file.stat().st_size, digest))
            if member:
                selected.append(file); recovery.append({'path': str(file.relative_to(self.root)), 'sha256': digest, 'archiveMember': member})
        candidate = self._candidate(path, selected, 'history-binary-copy', '버전별 코드·문서·설정·고유 파일 보존; 보관 ZIP과 바이트가 같은 binary 복제본만 정리', [proof], ['모든 코드·문서·설정·고유 파일', ARCHIVE]) if selected else None
        if candidate:
            candidate['evidence']['recovery'] = recovery
            candidate['fingerprint'] = _id(candidate['fingerprint'] + json.dumps(recovery, sort_keys=True))
        return candidate

    def _stream_hash(self, path, *, capture=False):
        result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0', '-c', 'copy', '-f', 'streamhash', '-hash', 'sha256', 'pipe:1'], capture_output=True, text=True, timeout=45, check=False)
        # MediaSource captures may lack a container footer; equal packet hashes still prove every stream is preserved.
        warning = result.stderr.strip()
        expected_end = re.fullmatch(r'\[in#0/matroska,webm @ 0x?[0-9a-f]+\] File ended prematurely at pos\. ([0-9]+) \(0x[0-9a-f]+\)', warning) if capture else None
        known_footer = expected_end is not None and int(expected_end.group(1)) == path.stat().st_size
        if result.returncode or warning and not known_footer or not result.stdout.strip(): raise StorageError('모든 영상/음성 스트림의 동일성을 확인하지 못했습니다.', 'media_mismatch')
        return result.stdout.strip()

    def _remux(self, case):
        parent = self._path(f'{HIGHRES}/{case}'); file = parent / 'captured-video.webm'; source = parent / 'source.mkv'
        catalog = self.root / HIGHRES / 'catalog.json'; record = _json(catalog)
        item = next((x for x in record.get('cases', []) if x.get('id') == case), {})
        if item.get('source') != str(source) or not item.get('source_page', '').startswith('https://') or not re.fullmatch(r'[0-9a-f]{64}', str(item.get('source_sha256', ''))): raise StorageError('고해상도 원본 출처를 확인하지 못했습니다.', 'missing_proof')
        proof = [self._proof_file(catalog), self._proof_file(source, item.get('source_sha256'))]
        if self._stream_hash(file, capture=True) != self._stream_hash(source): raise StorageError('보존 원본과 다른 미디어 스트림은 보호합니다.', 'media_mismatch')
        return self._candidate(file, [file], 'reference-remux-copy', '출처·원본·전체 스트림 동일성 검증; source.mkv와 고해상도 검수 기록 보존', proof, [str(source.relative_to(self.root))])

    def inspect(self):
        # Caches are scoped to one fresh inspection, never reused across a plan or execution.
        self.digests = {}; self.archive_members = None; self.references = None
        candidates, blocked = [], []
        profiles = [(relative + '/frames', lambda p=relative: self._frames(p)) for relative in FRAME_ROOTS]
        profiles += [(SIMPLE + '/frames', lambda: self._frames(SIMPLE, simple=True))]
        profiles += [(f'{QA}/{prefix}-v{i}', lambda p=f'{QA}/{prefix}-v{i}': self._qa(p)) for prefix, versions in [('runtime', range(2, 8)), ('style', range(1, 8))] for i in versions]
        profiles += [(relative, lambda p=relative: self._before(p)) for relative in BEFORE_ROOTS]
        profiles += [(f'{HIGHRES}/{case}/captured-video.webm', lambda p=case: self._remux(p)) for case in ('blackpink-shut-down', 'itzy-loco', 'itzy-wannabe')]
        for relative, build in profiles:
            if not (self.root / relative).exists() and not (self.root / relative).is_symlink(): continue
            try:
                value = build()
                if value: candidates.append(value)
            except (StorageError, OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.TimeoutExpired) as error:
                blocked.append({'scope': 'artifacts', 'path': relative, 'reason': str(error), 'code': getattr(error, 'code', 'unsafe_proof')})
        return {'candidates': candidates, 'blocked': blocked}

    def cleanup(self, candidates):
        # Keep producer lease acquisition serialized with the preflight and unlink pass.
        with self.manager._write_lock():
            return super().cleanup(candidates)

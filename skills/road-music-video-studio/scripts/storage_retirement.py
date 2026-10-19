"""Explicit delivery-preserving retirement of proven intermediates and old packages."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import zipfile

from storage_manager import StorageError, _id, _snapshot, _json_read, MAX_JSON
from storage_verification import VerificationMaintenance, _digest, _json, _allocated
from storage_legacy import _probe, producer_profile
from storage_artifacts import ARCHIVE, RESEARCH, HIGHRES, HARNESS, SIMPLE
from storage_archive_history import ArchiveHistory

AUDIO = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.aiff'}
VIDEO = {'.mp4', '.mkv', '.webm', '.mov', '.m4v', '.fmp4'}
IMAGE = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
WEIGHTS = {'.safetensors', '.gguf', '.ggml', '.ckpt', '.pt', '.pth', '.bin', '.onnx', '.h5', '.tflite', '.pkl', '.pickle'}
REFERENCES = (RESEARCH, HIGHRES, HARNESS, SIMPLE, 'Output/kpop-mv-directing-research-20261016')
COPY_MARKERS = ('/runtime-upgrade-target/', '/docs/installer-target/', '/cli-install/', '/verified-kit/', '/repo/skills/', '/runtime/ace/')
AUX = re.compile(r'(?:draft|proof|preview|picture|override|chunk|segment|seg_[0-9])', re.I)
LABELS = ('음악·오디오', '영상', '이미지·프레임', '압축·설치 파일', '프로그램·문서·기타', '모델', 'Git')


def category(path, size=0):
    if path.parts and path.parts[0] == '.git': return 'Git'
    suffix = path.suffix.lower()
    if suffix in WEIGHTS and not (suffix == '.pth' and 'site-packages' in path.parts): return '모델'
    if suffix in AUDIO: return '음악·오디오'
    if suffix in VIDEO: return '영상'
    if suffix in IMAGE: return '이미지·프레임'
    if suffix in {'.zip', '.dmg', '.download', '.gz', '.tgz', '.tar'}: return '압축·설치 파일'
    return '프로그램·문서·기타'


class RetirementMaintenance(VerificationMaintenance):
    def __init__(self, root, manager, *, active_check=None, probe=None):
        self.manager = manager
        super().__init__(root, active_check=active_check)
        self.probe = probe or _probe
        self.archive_history = ArchiveHistory(self.root)

    def _files(self):
        result = []
        for base, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(name for name in dirs if not (Path(base) / name).is_symlink())
            for name in sorted(names):
                path = Path(base) / name
                try: info = path.lstat()
                except FileNotFoundError: continue  # A live, excluded producer may replace its own temporary file.
                if stat.S_ISREG(info.st_mode): result.append(path)
                if len(result) > 250000: raise StorageError('전체 파일 검토 한도를 초과했습니다.', 'snapshot_limit')
        return result

    def _proof(self, path, expected=None):
        path = Path(path)
        if path.is_symlink() or not path.is_file(): raise StorageError('보존 근거가 일반 파일이 아닙니다.', 'unsafe_proof')
        for parent in path.parents:
            if parent.is_symlink(): raise StorageError('보존 근거의 symlink는 보호합니다.', 'unsafe_proof')
        before = _snapshot(path); key = (str(path), before['dev'], before['inode'], before['bytes'], before['mtimeNs'])
        digest = self.hashes.get(key)
        if digest is None: digest = _digest(path); self.hashes[key] = digest
        if before != _snapshot(path) or expected is not None and digest != expected: raise StorageError('원음·최종본·복구 근거가 변경됐습니다.', 'changed_proof')
        return {'path': str(path), 'sha256': digest}

    def _active(self, path):
        relative = str(path.relative_to(self.root))
        if any(str(path) in command or relative + '/' in command for command in self.commands): return True
        if super()._active(path): return True
        for project_id, project in self.registry.get('projects', {}).items():
            parent = Path(project['path']).resolve(strict=False)
            if (path == parent or path in parent.parents or parent in path.parents) and self.manager._busy(self.registry, project_id): return True
        return False

    def _idle(self, path):
        key = str(path)
        if key not in self.activity: self.activity[key] = not self.active_check(path)
        if not self.activity[key]: raise StorageError('진행 중인 작업·열린 파일·현재 설치 참조를 보호합니다.', 'active_or_unsafe')

    def _safe_json(self, path):
        self._path(str(path.relative_to(self.root)))
        return _json(path)

    def _context(self, files):
        self.protected = {self.root / ARCHIVE}; self.originals = set(); self.current_assets = set(); self.missing_roots = set(); library_state = []
        self.active_roots = [Path(p['path']).resolve(strict=False) for key, p in self.registry.get('projects', {}).items() if self.manager._busy(self.registry, key)]
        try:
            library = self.manager.management_db.read_document('work-library', self.manager.data_dir / 'video-studio-library.json', {'schemaVersion': 1, 'groups': {}})
        except ValueError as error:
            raise StorageError('최종 보관함을 확인할 수 없습니다.', 'unsafe_library') from error
        if not isinstance(library, dict) or library.get('schemaVersion') != 1 or not isinstance(library.get('groups'), dict): raise StorageError('최종 보관함을 확인할 수 없습니다.', 'unsafe_library')
        for group in library['groups'].values():
            if not isinstance(group, dict): raise StorageError('최종 보관함 형식이 다릅니다.', 'unsafe_library')
            for item in [group.get('source', {}), *group.get('files', []), *group.get('artifacts', [])]:
                if isinstance(item, dict) and isinstance(item.get('path'), str):
                    protected = Path(item['path']).resolve(strict=False); self.protected.add(protected)
                    library_state.append({'path':str(protected),'sha256':item.get('sha256'),'exists':protected.exists()})
                    if not protected.exists() and self.root / 'Output' in protected.parents: self.missing_roots.add(self._owner(protected))
                    if protected.is_file():
                        digest = item.get('sha256')
                        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest): raise StorageError('등록 결과/제작 자료의 해시가 없습니다.', 'unsafe_library')
                        self._proof(protected, digest)
        self.library_state = _id(json.dumps(library_state, sort_keys=True))
        for project in self.registry.get('projects', {}).values():
            root = Path(project['path'])
            for item in project.get('entries', {}).values():
                if item.get('pinned') is True: self.pinned.append(root / item['relativePath'])
        for path in files:
            rel = path.relative_to(self.root); suffix = path.suffix.lower()
            if rel.parts[0] != 'Output': self.protected.add(path); continue
            if category(rel, path.stat().st_size) == '모델' or any(p.casefold() in {'songs', 'masters', 'exports', 'models', 'engines', 'node_modules', '.venv', 'venv'} for p in rel.parts): self.protected.add(path)
            if suffix in AUDIO and suffix != '.wav': self.protected.add(path)
            if path.name == 'studio-project.json':
                value = self._safe_json(path)
                for item in value.get('media', []):
                    if isinstance(item, dict) and isinstance(item.get('path'), str): self.protected.add((path.parent / item['path']).resolve(strict=False))
        self.producers = []
        for path in files:
            if path.name != 'production.json' or 'Output' != path.relative_to(self.root).parts[0]: continue
            try:
                value = self._safe_json(path); source = value.get('source', {}); source_proofs = []
                if isinstance(source, dict) and isinstance(source.get('path'), str) and re.fullmatch('[0-9a-f]{64}', str(source.get('sha256', ''))):
                    source_path = Path(source['path'])
                    if source_path.suffix.lower() not in AUDIO or not source_path.is_absolute(): continue
                    source_proofs.append(self._proof(source_path, source['sha256']))
                elif value.get('mode') == 'native-composition':
                    playlist_path = path.parent / 'playlist.json'; playlist = self._safe_json(playlist_path)
                    tracks = playlist.get('tracks')
                    if not isinstance(tracks, list) or not tracks: continue
                    for track in tracks:
                        record = track.get('source', {})
                        if not isinstance(record.get('path'), str) or not re.fullmatch('[0-9a-f]{64}', str(record.get('sha256', ''))): raise StorageError('제작 입력 근거가 없습니다.', 'unsafe_proof')
                        source_path = (path.parent / record['path']).resolve(strict=False)
                        if source_path.suffix.lower() not in AUDIO: raise StorageError('제작 음원 형식이 다릅니다.', 'unsafe_proof')
                        source_proofs.append(self._proof(source_path, record['sha256']))
                        if isinstance(record.get('originalPath'), str): self.protected.add(Path(record['originalPath']).resolve(strict=False))
                    source_proofs.append(self._proof(playlist_path))
                else: continue
                source_proof = {'path': str(path), 'sha256': _id(json.dumps(source_proofs, sort_keys=True))}
                if producer_profile(path.parent) is None: continue
                duration = value.get('durationSeconds', value.get('renderDurationSeconds'))
                if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0: continue
                for checked in source_proofs:
                    self.originals.add(Path(checked['path']).resolve()); self.protected.add(Path(checked['path']).resolve())
                audio = value.get('audio', {})
                if isinstance(audio, dict) and isinstance(audio.get('path'), str): self.protected.add((path.parent / audio['path']).resolve(strict=False))
                for asset in (value.get('assets') or {}).values():
                    if isinstance(asset, dict) and isinstance(asset.get('source'), str): self.current_assets.add((path.parent / asset['source']).resolve(strict=False))
                self.producers.append({'root': path.parent, 'source': source_proof, 'sources': source_proofs, 'duration': duration, 'proof': self._proof(path)})
            except (StorageError, OSError, ValueError): continue
        self.protected.update(self.current_assets)
        self.protected_dirs = [p for p in self.protected if p.is_dir()]
        self.deliveries = defaultdict(list)
        for item in self.producers:
            for path in sorted((item['root'] / 'out').glob('*.mp4')):
                if path.is_symlink() or AUX.search(path.name): continue
                info = self.probe(path)
                if info.get('video') and info.get('audio') and abs(info.get('duration', 0) - item['duration']) <= 1:
                    proof = self._proof(path); self.protected.add(path)
                    self.deliveries[(self._owner(item['root']), item['source']['sha256'])].append(proof)

    def _owner(self, path):
        rel = path.relative_to(self.root)
        return self.root / Path(*rel.parts[:2])

    def _is_protected(self, path):
        rel = path.relative_to(self.root)
        if path in self.protected or path.suffix.lower() in WEIGHTS or any(p in path.parents for p in self.protected_dirs) or any(path == p or p in path.parents for p in self.pinned): return True
        if rel.parts[0] != 'Output' or any(p == path or p in path.parents for p in self.missing_roots): return True
        if any(parent == path or parent in path.parents for parent in self.active_roots): return True
        return False

    def _add(self, bucket, path, kind, owner, proof, reason, recovery=None):
        self._path(str(path.relative_to(self.root)))
        if self._is_protected(path) or path in self.selected: return
        before = _snapshot(path)
        if before['nlink'] != 1: return
        key = (str(owner), kind)
        group = bucket.setdefault(key, {'path': owner, 'kind': kind, 'files': [], 'proof': {}, 'reason': reason, 'recovery': []})
        group['files'].append(path); self.selected.add(path)
        for item in proof: group['proof'][item['path']] = item
        if recovery: group['recovery'].append(recovery)

    def _render_material(self, files, bucket):
        by_project = defaultdict(list); roots = {p['root'] for p in self.producers}
        for path in files:
            for parent in path.parents:
                if parent in roots: by_project[parent].append(path)
                if parent == self.root: break
        for item in self.producers:
            project = item['root']; finals = self.deliveries.get((self._owner(project), item['source']['sha256']), [])
            if not finals: continue
            proof = [item['proof'], *item['sources'], *finals]
            qa = defaultdict(list)
            for candidate in by_project[project]:
                if candidate.suffix.lower() in IMAGE and candidate.relative_to(project).parts[0] == 'qa' and not self._is_protected(candidate) and not re.search(r'(?:sheet|storyboard|contact|final|poster|summary)', candidate.name, re.I): qa[candidate.parent].append(candidate)
            representatives = set()
            for values in qa.values():
                values.sort(); representatives.update([values[0],values[len(values)//2],values[-1]])
            for path in by_project[project]:
                rel = path.relative_to(project); suffix = path.suffix.lower()
                if suffix == '.wav' and path.name in {'mix.wav', 'mix_bed.wav', 'mix_premaster.wav', 'mix_vo.wav'} and rel.parts[0] == 'audio':
                    self._add(bucket, path, 'retired-audio-mix', project, proof, '원음·입력 WAV·최종 영상을 보존하고 다시 생성 가능한 믹스 WAV를 폐기합니다.')
                elif suffix in VIDEO and (any(p.endswith('.parts') for p in rel.parts) or rel.parts[0] in {'qa', 'draft', 'proof'} or AUX.search(path.name)) and not any(p in {'assets', 'inputs', 'reel'} for p in rel.parts):
                    self._add(bucket, path, 'retired-render', project, proof, '원음·최종 납품·제작 코드·JSON 판정을 보존하고 이전 초안/렌더 조각을 폐기합니다.')
                elif suffix in IMAGE and rel.parts[0] == 'qa' and path not in representatives and not re.search(r'(?:sheet|storyboard|contact|final|poster|summary)', path.name, re.I):
                    self._add(bucket, path, 'retired-qa-image', project, proof, '최종 납품·검수 JSON/문서와 등록된 스토리보드를 보존하고 세부 검수 이미지를 폐기합니다.')

    def _references(self, files, bucket):
        retained, retention_proofs = {}, []
        baseline = self.root / 'outputs/storage-artifact-cleanup-20261019/protected-before.json'
        result = baseline.with_name('preservation-result.json')
        if baseline.is_file() and result.is_file() and self._safe_json(result).get('pass') is True:
            retention_proofs = [self._proof(baseline),self._proof(result)]
            retained = {Path(x['path']).resolve(strict=False):x['sha256'] for x in self._safe_json(baseline).get('files',[]) if isinstance(x,dict) and isinstance(x.get('path'),str) and re.fullmatch('[0-9a-f]{64}',str(x.get('sha256','')))}
        def url(value):
            if not isinstance(value,dict): return None
            return next((value[k] for k in ('source_page','official_page','page','sourceUrl') if isinstance(value.get(k),str) and value[k].startswith('https://')),None)
        for relative in REFERENCES:
            root = self.root / relative
            if not root.is_dir() or root.is_symlink(): continue
            local = [p for p in files if root in p.parents]
            bindings = {}
            def bind(source,digest,page,region,proof):
                if not isinstance(source,str) or not re.fullmatch('[0-9a-f]{64}',str(digest)) or not isinstance(page,str) or not page.startswith('https://'): return
                source_path = Path(source).resolve(strict=False)
                if source_path.name not in {'source.mp4','source.mkv','reference-original-video.mp4'} and not source_path.name.endswith('-official-video-only.mp4'): return
                if not any(self.root / p in source_path.parents for p in REFERENCES): return
                key=(source_path,str(region)); bindings[key]={'source':source_path,'digest':digest,'url':page,'region':region,'proof':proof}
            catalog = root / 'catalog.json'
            if catalog.is_file():
                for row in self._safe_json(catalog).get('cases',[]):
                    if isinstance(row,dict) and isinstance(row.get('source'),str): bind(row['source'],row.get('source_sha256'),url(row),Path(row['source']).parent,[self._proof(catalog)])
            provenance = root / 'provenance.json'; global_prov = self._safe_json(provenance) if provenance.is_file() else {}
            for manifest in [p for p in local if p.name=='manifest.json']:
                value = self._safe_json(manifest); source = value.get('source',{}); case = manifest.parent.parent
                if not isinstance(source,dict) or not isinstance(source.get('path'),str): continue
                case_prov = case / 'provenance.json'; page = None; proof=[self._proof(manifest)]
                if case_prov.is_file() and case_prov != provenance:
                    record=self._safe_json(case_prov); page=url(record);proof.append(self._proof(case_prov))
                if not page:
                    row=next((x for x in global_prov.get('sources',[]) if isinstance(x,dict) and x.get('path')==source['path'] and x.get('sha256')==source.get('sha256')),None)
                    page=url(row)
                    if page: proof.append(self._proof(provenance))
                bind(source['path'],source.get('sha256'),page,manifest.parent,proof)
            capture=root/'source-capture.json'; source=root/'reference-original-video.mp4'
            if capture.is_file() and source in retained:
                bind(str(source),retained[source],url(self._safe_json(capture)),root,[self._proof(capture),*retention_proofs])
            for binding in bindings.values():
                source,region=binding['source'],binding['region']
                if not source.is_file(): continue
                source_proof=self._proof(source,binding['digest']); expected={}; proofs=[*binding['proof'],source_proof]
                relevant=[p for p in local if region==p.parent or region in p.parents]
                for index in [p for p in relevant if p.name in {'frame-index.jsonl','sheet-index.json','index.json'}]:
                    if index.stat().st_size>MAX_JSON: raise StorageError('참조 색인 한도 초과','reference_limit')
                    proofs.append(self._proof(index))
                    rows=[json.loads(line) for line in index.read_text().splitlines()] if index.suffix=='.jsonl' else self._safe_json(index)
                    if not isinstance(rows,list): continue
                    for row in rows:
                        if not isinstance(row,dict): continue
                        for key,digest_key in [('path','sha256'),('thumbnail','thumbnail_sha256'),('sheet','sha256')]:
                            name,digest=row.get(key),row.get(digest_key)
                            if isinstance(name,str) and re.fullmatch('[0-9a-f]{64}',str(digest)): expected[(index.parent/name).resolve(strict=False)]=digest
                media=[p for p in relevant if p.suffix.lower() in IMAGE]
                keep=set(); sheets=defaultdict(list)
                for path in media:
                    if path.parent.name in {'sheets','original-details'}: sheets[path.parent].append(path)
                for values in sheets.values():
                    values.sort();keep.update([values[0],values[len(values)//2],values[-1]])
                # No verified visual evidence: preserve the source and its case rather than borrow another case's sheets.
                if not keep: continue
                evidence=[]
                for path in sorted(keep):
                    digest=expected.get(path,retained.get(path))
                    if not digest: evidence=[];break
                    evidence.append(self._proof(path,digest))
                if not evidence: continue
                proofs.extend(evidence)
                if any(p in retained and p not in expected for p in keep): proofs.extend(retention_proofs)
                self._add(bucket,source,'retired-reference-media',root,proofs,'같은 사례의 출처 URL·원본 해시·검증된 대표 시트·분석 기록을 보존합니다. 참조 원본 재검토에는 재확보가 필요합니다.')
                for path in media:
                    if path in keep or path not in expected: continue
                    if path.parent.name not in {'frames','sheets','original-details'} or not re.fullmatch(r'(?:frame-|sheet-|f|intro-|extra-|change-)[0-9]+\.(?:jpg|png)',path.name): continue
                    checked=self._proof(path,expected[path])
                    self._add(bucket,path,'retired-reference-media',root,[*proofs,checked],'같은 사례의 원본 해시·출처·프레임 색인·검증된 대표 시트를 보존하고 분석 중간 이미지를 폐기합니다.')

    def _jizura_versions(self, files, bucket):
        relative = 'Output/jizura-belluna-20261017'; root = self.root / relative
        if not root.is_dir() or root.is_symlink(): return
        current = root / '벨루나-오늘도-수고했어-JIZURA-1080p.mp4'
        assembly, provenance, command = root / 'final-assembly.json', root / 'source-provenance.json', root / 'final-render-command.json'
        if any(not item.is_file() or item.is_symlink() for item in (current, assembly, provenance, command)): return
        final = self._safe_json(assembly); source = self._safe_json(provenance); args = self._safe_json(command)
        user_audio = Path(source.get('userAudio', '')); source_sha = source.get('sha256')
        if not user_audio.is_absolute() or not re.fullmatch('[0-9a-f]{64}', str(source_sha)) or source.get('byteIdentical') is not True:
            return
        source_proof = self._proof(user_audio, source_sha)
        if final.get('output') != str(current) or not isinstance(final.get('sourceDuration'), (int, float)) or not isinstance(final.get('chapters'), list) or len(final['chapters']) != 1:
            return
        chapter = final['chapters'][0]
        if not isinstance(chapter, dict) or chapter.get('audio') != str(user_audio) or chapter.get('sha256') != source_sha:
            return
        current_info = self.probe(current)
        if not current_info.get('video') or not current_info.get('audio') or abs(current_info.get('duration', 0) - final['sourceDuration']) > 1:
            return
        project = root / 'production-project-v3/project.jizura.json'
        expected_command = ['--project', str(project), '--audio', str(user_audio), '--out', str(root / 'full-render-v3')]
        if not project.is_file() or project.is_symlink() or not isinstance(args, list) or any(value not in args for value in expected_command): return
        proofs = [source_proof, self._proof(current), self._proof(assembly), self._proof(provenance), self._proof(command), self._proof(project)]
        versions = []
        for version in ('v2', 'v3'):
            video, result = root / f'full-render-{version}/jizura.mp4', root / f'full-render-{version}/result.json'
            if not video.is_file() or video.is_symlink() or not result.is_file() or result.is_symlink(): return
            record = self._safe_json(result)
            if record.get('ok') is not True or record.get('output') != str(video) or record.get('bytes') != video.stat().st_size or not isinstance(record.get('duration'), (int, float)) or not isinstance(record.get('sourceDuration'), (int, float)):
                return
            info = self.probe(video)
            if not info.get('video') or not info.get('audio') or abs(info.get('duration', 0) - record['duration']) > 1 or abs(record['sourceDuration'] - final['sourceDuration']) > 1:
                return
            versions.append((video, result))
        if chapter.get('video') != str(versions[1][0]): return
        for video, result in versions:
            proof = [*proofs, self._proof(result)]
            self._add(bucket, video, 'retired-jizura-render', root, proof, '원음·현재 JIZURA 최종본·최종 조립 기록·v3 제작 프로젝트를 보존하고, 현재 최종본으로 대체된 이전 full render를 폐기합니다.', {'path': str(video.relative_to(self.root)), 'currentFinal': str(current.relative_to(self.root)), 'sourceSha256': source_sha})

    def _packages(self, files, bucket):
        for path in files:
            if path.suffix.lower() != '.zip' or path.relative_to(self.root).parts[0] != 'Output' or path == self.root / ARCHIVE: continue
            if not re.fullmatch(r'(?:MusicRoad-Skills-[0-9.]+|RoadMusic(?:-CLI)?-[0-9.]+(?:-cli|-source)?)\.zip', path.name): continue
            if self._is_protected(path): continue
            try:
                recovery = self.archive_history.plan(path)
            except StorageError as error:
                if error.code in {'protected', 'unsafe_archive', 'archive_limit'}:
                    continue
                raise
            product = recovery.get('product', {})
            if product.get('name') not in {'road-music', 'road-music-cli', 'music-road-skills'} or not isinstance(product.get('version'), str): continue
            proof = self._proof(path)
            owner = self._owner(path); key = (str(owner), 'retired-distribution'); was_selected = path in self.selected
            self._add(bucket, path, 'retired-distribution', owner, [proof], '제품/버전·ZIP 무결성을 확인한 과거 배포·검증용 압축 파일입니다. 현재 실행 코드·모델·before 복구용 보관 ZIP은 유지합니다.')
            if path in self.selected and not was_selected:
                bucket[key].setdefault('archiveRecovery', []).append(recovery)

    def _copy_canonical(self, path):
        text = '/' + str(path.relative_to(self.root))
        if not any(marker in text for marker in COPY_MARKERS): return None
        parts = path.relative_to(self.root).parts
        for i, part in enumerate(parts):
            if part.startswith('road-music-') and i + 1 < len(parts):
                candidate = self.root / '.agents/skills' / part / Path(*parts[i+1:])
                if candidate.is_file() and candidate.resolve() != path and self.root / 'Output' not in candidate.resolve().parents: return candidate.resolve()
            if part == 'road-music' and i + 1 < len(parts):
                candidate = self.root / Path(*parts[i+1:])
                if candidate.is_file() and candidate.resolve() != path and self.root / 'Output' not in candidate.resolve().parents: return candidate.resolve()
        return None

    def _copies(self, files, bucket):
        for path in files:
            if path.relative_to(self.root).parts[0] != 'Output' or self._is_protected(path) or path.suffix.lower() in WEIGHTS: continue
            canonical = self._copy_canonical(path)
            if canonical is None or canonical.stat().st_size != path.stat().st_size: continue
            actual = self._proof(path); kept = self._proof(canonical)
            if actual['sha256'] != kept['sha256']: continue
            self._add(bucket, path, 'retired-install-copy', self._owner(path), [kept], '현재 canonical 소스/스킬 자산과 바이트가 같은 과거 설치 검증 복제 파일입니다. 고유 코드·현재 스킬·모델은 보존합니다.', {'path': str(path), 'source': str(canonical), 'sha256': kept['sha256']})

    def inspect(self):
        self.registry = self.manager._read(); self.hashes = {}; self.activity = {}; self.pinned = []; self.selected = set()
        process = subprocess.run(['ps', '-axo', 'command='], capture_output=True, text=True, timeout=10, check=False)
        if process.returncode: raise StorageError('실행 중인 프로그램을 확인할 수 없습니다.', 'active_unknown')
        self.commands = process.stdout.splitlines()
        files = self._files(); self._context(files); bucket = {}; blocked = []
        for builder in (self._render_material, self._references, self._jizura_versions, self._packages, self._copies):
            try: builder(files, bucket)
            except (StorageError, OSError, ValueError, zipfile.BadZipFile) as error:
                raise StorageError('최종본 외 자료 검증을 완료하지 못했습니다: ' + str(error), 'retirement_incomplete') from error
        candidates = []
        for (relative, kind), group in sorted(bucket.items()):
            try:
                self._idle(group['path'])
                entries = []
                for path in sorted(set(group['files'])):
                    value = _snapshot(path); value.pop('path'); value['relativePath'] = str(path.relative_to(self.root)); value['sha256'] = self._proof(path)['sha256']; entries.append(value)
                if len(entries) > 10000: raise StorageError('정리 그룹 파일 수 한도를 초과했습니다.', 'snapshot_limit')
                evidence = {'libraryState': self.library_state, 'policy': group['reason'], 'proof': sorted(group['proof'].values(), key=lambda x:x['path']), 'preserved': ['현재 프로그램·모델·원음·등록 최종본·제작 입력/자산·JSON/문서 판정', str(self.root / ARCHIVE)], 'recovery': group['recovery'], 'archiveRecovery': group.get('archiveRecovery', [])}
                value = {'id': _id('retirement\0' + kind + '\0' + relative), 'scope': 'retirement', 'path': str(group['path'].relative_to(self.root)), 'absolutePath': str(group['path']), 'kind': kind, 'description': group['reason'], 'fileCount': len(entries), 'bytes': sum(x['bytes'] for x in entries), 'allocatedBytes': sum(_allocated(self.root / x['relativePath']) for x in entries), 'files': entries, 'evidence': evidence}
                value['fingerprint'] = _id(json.dumps({'files': entries, 'evidence': evidence}, sort_keys=True, ensure_ascii=False)); candidates.append(value)
            except (StorageError, OSError) as error: blocked.append({'scope': 'retirement', 'path': str(group['path'].relative_to(self.root)), 'reason': str(error)})
        eligible = {x['relativePath'] for c in candidates for x in c['files']}; review = {label: {'label': label, 'fileCount':0, 'allocatedBytes':0, 'eligibleFiles':0, 'eligibleAllocatedBytes':0, 'protectedFiles':0, 'protectedAllocatedBytes':0, 'reason':'확인된 원본·최종본·현재 운영 파일·필요 이력과 근거 없는 자료는 보호합니다.'} for label in LABELS}; seen = set()
        for path in files:
            try: info = path.stat()
            except FileNotFoundError: continue
            key = (info.st_dev,info.st_ino)
            if key in seen: continue
            seen.add(key); rel = path.relative_to(self.root); row = review[category(rel,info.st_size)]; size = info.st_blocks*512
            row['fileCount']+=1;row['allocatedBytes']+=size
            if str(rel) in eligible: row['eligibleFiles']+=1;row['eligibleAllocatedBytes']+=size
            else: row['protectedFiles']+=1;row['protectedAllocatedBytes']+=size
        return {'candidates': candidates, 'blocked': blocked, 'review': list(review.values())}

    def cleanup(self, candidates):
        with self.manager._write_lock():
            if not isinstance(candidates, list) or not candidates:
                raise StorageError('검증된 정리 후보가 필요합니다')
            current = {item['id']: item for item in self.inspect()['candidates']}
            selected = []
            for requested in candidates:
                if not isinstance(requested, dict) or requested.get('id') not in current:
                    raise StorageError('검증되지 않은 정리 후보입니다', 'invalid_plan')
                candidate = current[requested['id']]
                if requested.get('fingerprint') != candidate['fingerprint']:
                    raise StorageError('정리 계획 뒤 후보가 변경되었습니다', 'invalid_plan')
                selected.append(candidate)
            specs = [spec for candidate in selected for spec in candidate.get('evidence', {}).get('archiveRecovery', [])]
            prepared = self.archive_history.prepare(specs) if specs else {'manifests': [], 'storedBytes': 0, 'storedAllocatedBytes': 0}
            result = super().cleanup(candidates)
            try:
                for manifest in prepared['manifests']:
                    self.archive_history.verify(manifest)
            except StorageError as error:
                raise StorageError('배포 ZIP 삭제 뒤 보관 이력 검증에 실패했습니다: ' + str(error), 'postverify_failed') from error
            result['audit']['action'] = 'retirement-cleanup'
            result['retainedHistoryAllocatedBytes'] = prepared['storedAllocatedBytes']
            result['allocationDeltaBytes'] = result['freedAllocatedBytes'] - prepared['storedAllocatedBytes']
            result['manifests'] = prepared['manifests']
            result['audit']['archiveHistory'] = {'manifests': prepared['manifests'], 'storedBytes': prepared['storedBytes'], 'storedAllocatedBytes': prepared['storedAllocatedBytes'], 'allocationDeltaBytes': result['allocationDeltaBytes']}
            return result

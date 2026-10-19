"""Explicit migration of legacy experiments into final-only deliveries and a work area."""
from __future__ import annotations

import gzip
from contextlib import closing, nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

from storage_manager import StorageError, _atomic_json, _json_read, _id, _snapshot
from storage_packaging import TRUSTED_ROOT, is_workspace
from storage_maintenance import StorageMaintenance
from storage_scan import WorkspaceScan


class StorageRestructure:
    def __init__(self, manager, root=None):
        self.manager=manager; self.root=Path(root) if root is not None else TRUSTED_ROOT
        if self.root is None or not is_workspace(self.root): raise StorageError('현재 Road Music 작업 폴더에서만 구조 정리를 실행합니다.', 'unsafe_root')
        canonical=(Path.home()/'Library/Application Support/Road Music'if sys.platform=='darwin'else Path(os.environ.get('APPDATA',Path.home()/'AppData/Roaming'))/'Road Music'if sys.platform=='win32'else Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'Road Music')
        if self.root==TRUSTED_ROOT and manager.data_dir!=canonical.resolve():raise StorageError('구조 정리는 기본 앱 프로필에서만 실행합니다. 임시 프로필로 실제 작업 폴더를 정리할 수 없습니다.','unsafe_profile')
        self.control=self.root/'.roadmusic';self.plans=manager.data_dir/'storage-restructure-plans'
        self.marker=self.control/'structure.json';self.library=manager.data_dir/'video-studio-library.json'
        from work_library import WorkLibrary
        self.work_library=WorkLibrary(self.library)
        for path in (self.control,self.plans,self.library):
            if any(p.is_symlink()for p in (path,*path.parents)):raise StorageError('구조 관리 경로의 symlink는 허용하지 않습니다.','unsafe_path')

    def status(self, params):
        if params: raise StorageError('구조 조회에는 입력값이 없습니다.')
        marker=_json_read(self.marker,{})
        database=self.control/'history.sqlite3';versions=0
        if database.is_file()and not database.is_symlink():
            with closing(sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True))as connection:versions=connection.execute('SELECT count(*) FROM delivery_versions').fetchone()[0]
        return {'structured':marker.get('schemaVersion')==1 and marker.get('phase','completed')=='completed','versionCount':versions,'outputRoot':str(self.root/'Output'),'workingRoot':str(self.control/'work'),'dbPath':str(database),**marker}

    def _delivery_paths(self):
        database=self.control/'history.sqlite3'
        if not database.exists():return set()
        if database.is_symlink():raise StorageError('버전 DB symlink는 허용하지 않습니다.','unsafe_path')
        with closing(sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True))as connection:
            return {Path(x[0])for x in connection.execute('SELECT path FROM delivery_files')if Path(x[0]).is_relative_to(self.root/'Output')}

    def _roots(self):
        marker=_json_read(self.marker,{})
        deliveries=self._delivery_paths();known=set(marker.get('deliveryRoots',[])); roots=[]
        known.update('Output/'+p.relative_to(self.root/'Output').parts[0]for p in deliveries)
        output=self.root/'Output'
        if output.is_symlink():raise StorageError('Output symlink는 구조 정리할 수 없습니다.','unsafe_path')
        if output.is_dir():
            for p in sorted(output.iterdir()):
                if str(p.relative_to(self.root)) not in known:roots.append(p)
                elif p.is_dir()and not p.is_symlink():
                    roots.extend(item for item in p.rglob('*')if(item.is_file()or item.is_symlink())and item not in deliveries)
        for name in ('outputs','dist'):
            path=self.root/name
            if path.exists() or path.is_symlink():roots.append(path)
        return roots

    def _obsolete_registrations(self, registry):
        temporary=Path(tempfile.gettempdir()).resolve();rows={}
        for key,row in registry['projects'].items():
            path=Path(row.get('path',''))
            if not path.is_absolute()or '..'in path.parts or not path.is_relative_to(temporary)or row.get('entries')or self.manager._busy(registry,key):continue
            relative=path.relative_to(temporary)
            if not relative.parts or not relative.parts[0].startswith(('tmp','cd-playlist-input-')):continue
            try:path.lstat()
            except FileNotFoundError:rows[key]=row
            except OSError:continue
        return rows

    def _prune_registrations(self, planned):
        if not planned:return 0
        with self.manager._write_lock():
            registry=self.manager._read();current=self._obsolete_registrations(registry);removed=[]
            for key,row in planned.items():
                if current.get(key)==row:
                    registry['projects'].pop(key,None);registry['leases'].pop(key,None);removed.append(key)
            if removed:self.manager._save(registry)
        if removed:self.manager._audit(self.root,'obsolete-temporary-registrations',{'projectIds':removed,'fileDeletes':0})
        return len(removed)

    def _inventory(self, roots):
        files=[]
        for root in roots:
            paths=[root] if not root.is_dir() or root.is_symlink() else None
            if paths is None:
                paths=[]
                for base,dirs,names in os.walk(root,followlinks=False):
                    for name in list(dirs):
                        path=Path(base)/name
                        if path.is_symlink():paths.append(path);dirs.remove(name)
                    paths.extend(Path(base)/name for name in names)
            for p in paths:
                st=p.lstat()
                if not(stat.S_ISREG(st.st_mode)or stat.S_ISLNK(st.st_mode)):raise StorageError('알 수 없는 특수 파일을 보호합니다.','unsafe_path')
                rel=str(p.relative_to(self.root));row={'relativePath':rel,'dev':st.st_dev,'inode':st.st_ino,'bytes':st.st_size,'mtimeNs':st.st_mtime_ns,'allocatedBytes':st.st_blocks*512,'symlink':p.is_symlink()}
                if row['symlink']:row['target']=os.readlink(p)
                files.append(row)
                if len(files)>250000:raise StorageError('파일 수 검증 한도를 초과했습니다.','snapshot_limit')
        return sorted(files,key=lambda x:x['relativePath'])

    @staticmethod
    def _fingerprint(files):return _id(json.dumps(files,sort_keys=True,separators=(',',':')))

    @staticmethod
    def _delivery_events(group):
        files=[x for x in group.get('files',[])if Path(x.get('path','')).is_file()]
        fallback={};events={}
        for item in files:
            origins=item.get('origins')or[{}];byproject={}
            for origin in origins:byproject.setdefault(origin.get('project')or str(Path(group['source']['path']).parent),[]).append(origin)
            for project,rows in byproject.items():
                timed=[row for row in rows if row.get('registeredAt')]
                if timed:
                    for row in timed:events.setdefault((project,row['registeredAt']),{})[item['path']]=item
                else:fallback.setdefault(project,{})[item['path']]=item
        for project,items in fallback.items():
            timed=[key for key in events if key[0]==project]
            if timed:
                for item in items.values():events[max(timed,key=lambda x:x[1])][item['path']]=item
            else:
                timestamp=max((x.get('createdAt','')for x in items.values()),default='')or None
                events[(project,timestamp)]=items
        if not events:events[(str(Path(group['source']['path']).parent),None)]={}
        return {key:list(items.values())for key,items in events.items()}

    def _idle(self, roots):
        registry=self.manager._read()
        for key,project in registry['projects'].items():
            p=Path(project['path'])
            if any(p==r or r in p.parents for r in roots) and self.manager._busy(registry,key):raise StorageError('진행 중인 프로젝트를 먼저 완료해야 합니다: '+str(p),'busy')
        if not roots:return
        try:
            process=subprocess.run(['ps','-axo','pid=,command='],capture_output=True,text=True,timeout=10,check=True)
            relative_pids=[]
            for row in process.stdout.splitlines():
                pid,_,command=row.strip().partition(' ')
                if pid.isdigit()and int(pid)!=os.getpid():
                    if any(str(root)in command for root in roots):raise StorageError('정리 폴더를 실행 중인 프로그램을 먼저 종료해야 합니다.','busy')
                    if any(re.search(r'(?:^|\s)(?:\./)?'+re.escape(str(root.relative_to(self.root)))+r'(?:/|\s|$)',command)for root in roots):relative_pids.append(pid)
            opened=subprocess.run(['lsof','-nP','-Fpfn'],capture_output=True,text=True,timeout=20,check=False)
            if opened.returncode not in (0,1):raise StorageError('열린 파일을 확인할 수 없습니다.','busy')
            pid=fd=None
            for line in opened.stdout.splitlines():
                if line.startswith('p'):pid=line[1:]
                elif line.startswith('f'):fd=line[1:]
                elif line.startswith('n/')and pid!=str(os.getpid()):
                    p=Path(line[1:])
                    if any(p==root or root in p.parents for root in roots):raise StorageError('정리 폴더에 열린 파일이 있습니다.','busy')
                    if fd=='cwd'and p==self.root and pid in relative_pids:raise StorageError('작업 폴더의 상대 경로를 실행 중입니다.','busy')
        except (OSError,subprocess.SubprocessError)as error:raise StorageError('실행 중인 작업을 확인하지 못했습니다.','busy')from error

    def _runtime_probe(self, rescue):
        if not(rescue.get('mappings')or rescue.get('preservedModels')):return
        python=self.manager.data_dir/'engines/yue-mlx/venv/bin/python'
        try:
            result=subprocess.run([str(python),'-c','import json,sqlite3,numpy,soundfile,mlx.core; print(json.dumps({"sqlite":sqlite3.sqlite_version,"mlx":True}))'],capture_output=True,text=True,timeout=30,check=True)
            return json.loads(result.stdout)
        except (OSError,ValueError,subprocess.SubprocessError)as error:raise StorageError('이전한 음악 실행 환경을 검증하지 못했습니다. 기존 자료는 유지합니다.','runtime_probe_failed')from error

    def preview(self, params):
        if params:raise StorageError('구조 정리에는 임의 경로를 지정할 수 없습니다.')
        from storage_runtime_rescue import RuntimeRescue
        scan=WorkspaceScan(self.root,self.manager.data_dir).scan()
        if not scan.get('complete'):raise StorageError('전체 스캔이 완료되지 않았습니다.','scan_required')
        roots=self._roots();self._idle(roots);files=self._inventory(roots)
        runtime=RuntimeRescue(self.root,self.manager.data_dir).plan()
        obsolete=self._obsolete_registrations(self.manager._read())
        library=self.work_library._read()
        if library.get('schemaVersion')!=1 or not isinstance(library.get('groups'),dict):raise StorageError('작업물 보관함을 확인할 수 없습니다.','unsafe_library')
        missing=[];count=0
        for group in library['groups'].values():
            for item in [group.get('source',{}),*group.get('files',[]),*group.get('artifacts',[])]:
                if not isinstance(item,dict)or not isinstance(item.get('path'),str):continue
                p=Path(item['path'])
                if not p.is_file():missing.append(item['path']);continue
                if p.is_symlink():raise StorageError('등록 최종본 symlink를 보호합니다.','unsafe_path')
                with p.open('rb')as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
                if digest!=item.get('sha256'):raise StorageError('등록 최종본이 변경됐습니다: '+str(p),'changed_proof')
                if item.get('kind')!='artifact':count+=1
        if any(not isinstance(key,str)or not re.fullmatch('[0-9a-f]{64}',key)or value.get('sourceSha256')!=key for key,value in library['groups'].items()):raise StorageError('음악 그룹 식별자가 올바르지 않습니다.','unsafe_library')
        planid=secrets.token_hex(24);self.plans.mkdir(parents=True,exist_ok=True)
        for old in self.plans.glob('*.json'):
            previous=_json_read(old,{})
            if previous.get('expiresAt',0)<time.time()or previous.get('state')=='used':
                old.unlink();old.with_name(old.stem+'.files.jsonl.gz').unlink(missing_ok=True)
        inventory=self.plans/(planid+'.files.jsonl.gz')
        with gzip.open(inventory,'wt')as f:
            for row in files:f.write(json.dumps(row,separators=(',',':'))+'\n')
        seen=set();allocated=0
        for row in files:
            key=(row['dev'],row['inode'])
            if key not in seen:allocated+=row['allocatedBytes'];seen.add(key)
        summaries=[]
        for root in roots:
            rel=str(root.relative_to(self.root));values=[x for x in files if x['relativePath']==rel or x['relativePath'].startswith(rel+'/')]
            summaries.append({'path':rel,'fileCount':len(values),'allocatedBytes':sum(x['allocatedBytes']for x in values)})
        plan={'schemaVersion':1,'planId':planid,'state':'ready','expiresAt':time.time()+1800,'workspace':str(self.root),'roots':[str(x.relative_to(self.root))for x in roots],'inventory':str(inventory),'fingerprint':self._fingerprint(files),'libraryHash':_id(json.dumps(library,sort_keys=True)),'runtime':runtime,'obsoleteRegistrations':obsolete,'scanId':scan.get('scanId'),'beforeAllocatedBytes':scan['totals']['allocatedBytes']}
        _atomic_json(self.plans/(planid+'.json'),plan)
        return {'planId':planid,'expiresAt':plan['expiresAt'],'summary':{'legacyRoots':len(roots),'legacyFileCount':len(files),'legacyAllocatedBytes':allocated,'deliveryGroups':len(library['groups']),'deliveryFiles':count,'modelMoves':len(runtime.get('moves',runtime.get('mappings',[]))),'obsoleteRegistrations':len(obsolete)},'obsoleteRegistrations':[{'projectId':key,'path':row['path'],'name':row.get('name','')}for key,row in obsolete.items()],'legacyRoots':summaries,'preserved':['현재 프로그램·모델·VAE','등록 원음·완성본과 SQLite 버전·변경 기록'],'warnings':['기존 Output/outputs/dist의 테스트·작업 자료를 전부 폐기합니다. 검증된 완성본만 새 Output으로 옮기며 진행 자료는 .roadmusic/work에서 관리합니다.','현재 테스트 폴더의 모델·실행 환경을 앱 데이터로 먼저 보존합니다. 폴더 감소량과 실제 디스크 확보량은 다릅니다.'], 'preexistingMissing':missing,'blocked':[]}

    def _import_deliveries(self, _already_locked=False):
        from delivery_store import DeliveryStore
        try:original=self.work_library._read()
        except ValueError as error:raise StorageError('최종 보관함을 확인할 수 없습니다.','unsafe_library')from error
        original_hash=_id(json.dumps(original,sort_keys=True))
        store=DeliveryStore(self.root);versions=[];mapping={};work_roots={}
        for groupid,group in original['groups'].items():
            source=group.get('source',{});source_path=Path(source.get('path',''))
            if not source_path.is_file():raise StorageError('현재 원음이 없습니다.','missing_source')
            events=self._delivery_events(group)
            for (old_project,stamp),items in sorted(events.items(),key=lambda x:str(x[0])):
                candidate=Path(old_project);previous={}
                if candidate.is_relative_to(self.control/'work'):
                    if '..'in candidate.parts or candidate.resolve(strict=True)!=candidate or any(p.is_symlink()for p in(candidate,*candidate.parents)):raise StorageError('작업 영역 밖으로 벗어나는 이전 경로입니다.','unsafe_project')
                    previous=_json_read(candidate/'studio-project.json',{})
                    if previous.get('musicSha256')!=groupid or not re.fullmatch('[0-9a-f]{64}',str(previous.get('projectId',''))):raise StorageError('이전 작업 영역의 음악·프로젝트 연결이 올바르지 않습니다.','unsafe_project')
                projectid=previous.get('projectId')or _id(groupid+'\0'+old_project)
                if not re.fullmatch('[0-9a-f]{64}',str(projectid)):raise StorageError('이전 프로젝트 식별자가 올바르지 않습니다.','unsafe_project')
                project_name=previous.get('projectName')or Path(old_project).name
                label=re.sub(r'[^\w.-]+','-',project_name).strip('.-')or'project';work=Path(old_project)if previous else self.control/'work'/groupid[:12]/(label[:48]+'--'+projectid[:12]);work.mkdir(parents=True,exist_ok=True)
                if any(p.is_symlink()for p in (work,*work.parents)):raise StorageError('작업 영역 symlink는 허용하지 않습니다.','unsafe_path')
                media=[{'id':'music','kind':'music','path':str(source_path),'sha256':source['sha256'],'label':source.get('name',source_path.name)}]
                seen={('music',source['sha256'])}
                for item in items:
                    key=(item['kind'],item['sha256'])
                    if key in seen:continue
                    seen.add(key);media.append({'id':'file-'+_id(item['kind']+'\0'+item['sha256'])[:16],'kind':item['kind'],'path':item['path'],'sha256':item['sha256'],'label':item.get('name',Path(item['path']).name)})
                data={'schemaVersion':1,'name':group['title'],'projectName':project_name,'projectId':projectid,'music':str(source_path),'musicSha256':groupid,'media':media,'host':'codex','mode':next((x.get('mode')for item in items for x in item.get('origins',[])if x.get('mode')),'showreel-motion')}
                _atomic_json(work/'studio-project.json',data)
                historical=next((origin for item in items for origin in item.get('origins',[])if origin.get('project')==old_project and origin.get('registeredAt')==stamp),{})
                for name,key in [('selection.json','selection'),('feedback.json','feedback')]:_atomic_json(work/name,historical.get(key,{}))
                version=store.publish(work,media,source_sha256=groupid,title=group['title'],reason='과거 등록 시각으로 가져온 완료본 · 수정 사유 미기록',created_at=stamp,project_id=projectid,_allow_source_only=any(item.get('kind')=='music'and item.get('sha256')==groupid for item in items))
                versions.append(version);work_roots[old_project]=str(work)
                returned=version.get('files',[])
                byhash={(x['kind'],x['sha256']):x for x in returned}
                for item in [source,*items]:
                    key=('music'if item.get('kind')=='source'else item.get('kind'),item.get('sha256'))
                    if key in byhash:mapping[item['path']]=byhash[key]['path']
                for item in data['media']:
                    if item['path']in mapping:item['path']=mapping[item['path']]
                data['music']=mapping.get(str(source_path),str(source_path));_atomic_json(work/'studio-project.json',data)
                for name in ('production.json','playlist.json'):
                    (work/name).unlink(missing_ok=True) # Their snapshots are in SQLite; discarded test inputs cannot be resumed.
        required={x['path']for group in original['groups'].values()for x in[group.get('source',{}),*group.get('files',[])]if isinstance(x.get('path'),str)and Path(x['path']).is_file()}
        if required-set(mapping):raise StorageError('일부 완성본을 새 구조에서 확인할 수 없습니다. 원본을 유지합니다.','incomplete_delivery')
        # Update the compatibility library only after every completed file has a verified destination.
        for group in original['groups'].values():
            for item in [group.get('source',{}),*group.get('files',[])]:
                old=item.get('path')
                if old in mapping:
                    item['path']=mapping[old];p=Path(item['path']);st=p.stat();item.update({'name':p.name,'size':st.st_size,'statSize':st.st_size,'statMtimeNs':st.st_mtime_ns})
                if item.get('project')in work_roots:item['project']=work_roots[item['project']]
                for origin in item.get('origins',[]):
                    if origin.get('project')in work_roots:origin['project']=work_roots[origin['project']]
            group['files']=[x for x in group.get('files',[])if x.get('path')in mapping.values()]
            group['artifacts']=[]
        from work_library import WorkLibrary
        with(nullcontext()if _already_locked else self.work_library._write_lock()):
            current=self.work_library._read()
            if _id(json.dumps(current,sort_keys=True))!=original_hash:raise StorageError('이전 중 보관함에 새 결과가 등록됐습니다. 기존 자료를 유지합니다.','stale_plan')
            self.work_library._save(original)
        return versions,mapping,work_roots

    def cleanup(self, params):
        if not isinstance(params,dict)or set(params)-{'planId','confirm'}or params.get('confirm')is not True:raise StorageError('같은 계획과 명시 확인이 필요합니다.','confirm_required')
        planid=params.get('planId')
        if not isinstance(planid,str)or not re.fullmatch('[0-9a-f]{48}',planid):raise StorageError('정리 계획이 올바르지 않습니다.')
        from work_library import WorkLibrary
        with StorageMaintenance(self.manager,self.root)._lock(),self.work_library._write_lock():
            path=self.plans/(planid+'.json');plan=_json_read(path,{})
            if plan.get('state')!='ready'or plan.get('expiresAt',0)<time.time()or plan.get('workspace')!=str(self.root):raise StorageError('만료되거나 사용한 계획입니다.','stale_plan')
            roots=[]
            for relative in plan.get('roots',[]):
                if not isinstance(relative,str):raise StorageError('계획의 정리 경로가 올바르지 않습니다.','unsafe_plan')
                parts=Path(relative).parts
                if Path(relative).is_absolute()or '..'in parts or not(parts in [('outputs',),('dist',)]or len(parts)>=2 and parts[0]=='Output'):raise StorageError('계획의 정리 경로가 올바르지 않습니다.','unsafe_plan')
                roots.append(self.root/relative)
            if any(p==r or r in p.parents for p in self._delivery_paths()for r in roots):raise StorageError('이미 등록한 새 구조 완성본은 삭제하지 않습니다.','protected')
            self._idle(roots)
            files=self._inventory(roots)
            if self._fingerprint(files)!=plan['fingerprint']:raise StorageError('계획 뒤 파일이 바뀌었습니다. 새로 스캔하세요.','stale_plan')
            library=self.work_library._read()
            if _id(json.dumps(library,sort_keys=True))!=plan['libraryHash']:raise StorageError('계획 뒤 최종 보관함이 바뀌었습니다.','stale_plan')
            plan['state']='used';_atomic_json(path,plan)
            existing=_json_read(self.marker,{})
            if not roots and existing.get('phase')=='completed':
                return {'prunedRegistrations':self._prune_registrations(plan.get('obsoleteRegistrations',{})),'removedFiles':0,'freedAllocatedBytes':0,'diskFreeDeltaBytes':0,'workspaceBeforeAllocatedBytes':plan['beforeAllocatedBytes'],'workspaceAfterAllocatedBytes':plan['beforeAllocatedBytes'],'deliveryVersions':self.status({})['versionCount'],'alreadyStructured':True,'legacyRootsRemaining':[]}
            initial_roots=sorted({'Output/'+p.relative_to(self.root/'Output').parts[0]for p in self._delivery_paths()})
            marker={'schemaVersion':1,'phase':'preparing','deliveryRoots':initial_roots,'policy':'final-only','workspace':str(self.root),'owner':'road-music','planId':planid}
            settings=self.manager.data_dir/'settings.json';value=_json_read(settings,{})
            value['deliveryRoot']=str(self.root);_atomic_json(settings,value)
            _atomic_json(self.marker,marker)
            from storage_runtime_rescue import RuntimeRescue
            before=shutil.disk_usage(self.root).free
            rescue=RuntimeRescue(self.root,self.manager.data_dir).apply(plan['runtime'])
            runtime_check=self._runtime_probe(rescue)
            versions,mapping,work_roots=self._import_deliveries(_already_locked=True)
            if self._fingerprint(self._inventory(roots))!=plan['fingerprint']:raise StorageError('이전 준비 중 기존 작업 자료가 변경됐습니다. 원본을 유지합니다.','stale_plan')
            # No legacy unlink occurs until both the runtime and every delivery have verified destinations.
            audit=self.control/'maintenance'/(planid+'-restructure.json');audit.parent.mkdir(parents=True,exist_ok=True)
            _atomic_json(audit,{'status':'intent','planId':planid,'legacyRoots':plan['roots'],'runtime':rescue,'deliveryVersions':[x.get('id')for x in versions],'preservedFiles':mapping})
            delivery_roots=sorted({'Output/'+p.relative_to(self.root/'Output').parts[0]for p in self._delivery_paths()})
            marker={'schemaVersion':1,'phase':'prepared','deliveryRoots':delivery_roots,'policy':'final-only','workspace':str(self.root),'owner':'road-music','planId':planid}
            _atomic_json(self.marker,marker)
            removed=allocated=0
            for item in files:
                p=self.root/item['relativePath']
                st=p.lstat();expected=(item['dev'],item['inode'],item['bytes'],item['mtimeNs'])
                if (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)!=expected:raise StorageError('삭제 직전 파일이 변경됐습니다: '+str(p),'changed_file')
                self.manager._unlink_verified(self.root,item['relativePath'],expected);removed+=1
                if st.st_nlink==1:allocated+=item['allocatedBytes']
            for root in roots:
                if root.is_dir():
                    for base,_,_ in os.walk(root,topdown=False,followlinks=False):
                        if not os.listdir(base):os.rmdir(base)
            with self.manager._write_lock():
                registry=self.manager._read()
                registry['projects']={k:v for k,v in registry['projects'].items()if not any(Path(v['path'])==r or r in Path(v['path']).parents for r in roots)}
                registry['leases']={k:v for k,v in registry['leases'].items()if k in registry['projects']}
                self.manager._save(registry)
            for work in sorted(set(work_roots.values())):self.manager.register({'project':work})
            settings=self.manager.data_dir/'settings.json';value=_json_read(settings,{})
            value['deliveryRoot']=str(self.root);value['exportDir']=str(self.root/'Output');_atomic_json(settings,value)
            after=WorkspaceScan(self.root,self.manager.data_dir).scan()
            rescue_summary={key:rescue[key]for key in ('preservedModels','movedAllocatedBytes')if key in rescue};rescue_summary.update({'mappedFiles':len(rescue.get('mappings',[])),'runtimeCheck':runtime_check})
            result={'prunedRegistrations':self._prune_registrations(plan.get('obsoleteRegistrations',{})),'removedFiles':removed,'freedAllocatedBytes':allocated,'diskFreeDeltaBytes':shutil.disk_usage(self.root).free-before,'workspaceBeforeAllocatedBytes':plan['beforeAllocatedBytes'],'workspaceAfterAllocatedBytes':after['totals']['allocatedBytes'],'deliveryVersions':len(versions),'modelRescue':rescue_summary,'preservedFiles':len(mapping),'legacyRootsRemaining':[str(x)for x in roots if x.exists()or x.is_symlink()],'dbPath':str(self.control/'history.sqlite3'),'auditPath':str(audit)}
            _atomic_json(audit,{'status':'completed','planId':planid,'result':result})
            self.manager._audit(self.root,'structure-cleanup',{'planId':planid,**{k:result[k]for k in ('removedFiles','freedAllocatedBytes','diskFreeDeltaBytes','deliveryVersions')}})
            _atomic_json(self.marker,{**marker,'phase':'completed','completedAt':int(time.time())})
            return result

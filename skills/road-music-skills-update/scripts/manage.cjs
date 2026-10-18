#!/usr/bin/env node
'use strict'

// The installer deliberately owns only the six paths declared by manifest.json.
const fs = require('node:fs')
const fsp = require('node:fs/promises')
const path = require('node:path')
const os = require('node:os')
const crypto = require('node:crypto')
const { spawn } = require('node:child_process')

const REPOSITORY = 'roadkwonai/music-road-skills'
const API = `https://api.github.com/repos/${REPOSITORY}/releases`
const MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
const MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
const MAX_ZIP_ENTRIES = 10_000
const MAX_TEXT_BYTES = 1024 * 1024
const REQUEST_MS = 30_000
const DOWNLOAD_MS = 20 * 60_000
const MAX_WATCH_MS = 24 * 60 * 60 * 1000
const MANAGED_SKILLS = Object.freeze([
  'road-music-showreel-cd',
  'road-music-showreel-mv',
  'road-music-jizura-playlist',
  'road-music-showreel-playlist',
  'road-music-video-studio',
  'road-music-skills-update'
])
const root = path.resolve(__dirname, '..', '..', '..')
const responseControls = new WeakMap()

class SkillsError extends Error {
  constructor (code, message) { super(message); this.code = code }
}
function fail (code, message) { throw new SkillsError(code, message) }
function stable (version) { return typeof version === 'string' && /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version) }
function versionParts (version) { return stable(version) ? version.split('.').map(Number) : null }
function compareVersion (left, right) { const a = versionParts(left); const b = versionParts(right); return a[0] - b[0] || a[1] - b[1] || a[2] - b[2] }
function defaultTarget (host = 'codex') {
  if (host === 'claude') return path.join(process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude'), 'skills')
  if (host === 'antigravity') return path.join(os.homedir(), '.gemini', 'config', 'skills')
  if (host === 'antigravity-cli') return path.join(os.homedir(), '.gemini', 'antigravity-cli', 'skills')
  return path.join(process.env.CODEX_HOME || path.join(os.homedir(), '.codex'), 'skills')
}
function resolveTarget (params) {
  if (params.target) return path.resolve(params.target)
  return path.resolve(defaultTarget(params.host || 'codex'))
}
function isInside (parent, child) { const relative = path.relative(parent, child); return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative)) }
function stateDirectory (target) { return path.join(target, '.music-road-skills') }
function statePath (target) { return path.join(stateDirectory(target), 'managed.json') }
function randomName () { return `${process.pid}-${crypto.randomBytes(6).toString('hex')}` }
function event (params, name, value = {}) { try { if (typeof params.onEvent === 'function') params.onEvent({ event: name, ...value }) } catch {} }

function assertParams (params, allowed) {
  if (!params || typeof params !== 'object' || Array.isArray(params)) fail('INVALID_ARGUMENT', 'params는 객체여야 합니다.')
  for (const key of Object.keys(params)) if (![...allowed, 'onEvent'].includes(key)) fail('INVALID_ARGUMENT', `지원하지 않는 입력값입니다: ${key}`)
  if (params.target !== undefined && (typeof params.target !== 'string' || params.target.includes('\0') || !path.isAbsolute(params.target))) fail('INVALID_ARGUMENT', 'target은 NUL 문자가 없는 절대 경로여야 합니다.')
  if (params.source !== undefined && (typeof params.source !== 'string' || params.source.includes('\0') || !path.isAbsolute(params.source))) fail('INVALID_ARGUMENT', 'source는 NUL 문자가 없는 절대 경로여야 합니다.')
  if (params.host !== undefined && !['codex', 'claude', 'antigravity', 'antigravity-cli'].includes(params.host)) fail('INVALID_ARGUMENT', 'host는 codex, claude, antigravity 또는 antigravity-cli여야 합니다.')
  if (params.onEvent !== undefined && typeof params.onEvent !== 'function') fail('INVALID_ARGUMENT', 'onEvent는 함수여야 합니다.')
  if (params.timeoutMs !== undefined && (!Number.isSafeInteger(params.timeoutMs) || params.timeoutMs < 0 || params.timeoutMs > MAX_WATCH_MS)) fail('INVALID_ARGUMENT', `timeoutMs은 0부터 ${MAX_WATCH_MS}까지의 정수여야 합니다.`)
  if (params.intervalMs !== undefined && (!Number.isSafeInteger(params.intervalMs) || params.intervalMs < 1000 || params.intervalMs > MAX_WATCH_MS)) fail('INVALID_ARGUMENT', `intervalMs은 1000부터 ${MAX_WATCH_MS}까지의 정수여야 합니다.`)
  return params
}

async function readJson (file, code, message) {
  try { return JSON.parse(await fsp.readFile(file, 'utf8')) } catch { fail(code, message) }
}
async function noSymlinks (directory) {
  const info = await fsp.lstat(directory).catch(() => null)
  if (!info || info.isSymbolicLink()) fail('UPDATE_VERIFY', '심볼릭 링크가 포함된 스킬 묶음은 설치할 수 없습니다.')
  if (!info.isDirectory()) return
  for (const name of await fsp.readdir(directory)) await noSymlinks(path.join(directory, name))
}
async function sha256 (file) {
  const hash = crypto.createHash('sha256')
  await new Promise((resolve, reject) => {
    const stream = fs.createReadStream(file)
    stream.on('data', chunk => hash.update(chunk)).on('error', reject).on('end', resolve)
  })
  return hash.digest('hex')
}
function runtimeCache (relative) {
  const parts = relative.split(path.sep)
  return parts.includes('__pycache__') || parts.at(-1) === '.DS_Store' || parts.at(-1).endsWith('.pyc')
}
async function tree (directory, relative = '') {
  const result = {}
  const names = await fsp.readdir(directory)
  for (const name of names.sort()) {
    const absolute = path.join(directory, name); const rel = path.join(relative, name); const info = await fsp.lstat(absolute)
    if (runtimeCache(rel)) continue
    if (info.isSymbolicLink()) fail('UPDATE_VERIFY', '심볼릭 링크가 포함된 스킬은 설치할 수 없습니다.')
    if (info.isDirectory()) Object.assign(result, await tree(absolute, rel))
    else if (info.isFile()) result[rel] = await sha256(absolute)
    else fail('UPDATE_VERIFY', '일반 파일과 폴더 외의 항목은 설치할 수 없습니다.')
  }
  return result
}
function sameTree (left, right) { const a = Object.keys(left).sort(); const b = Object.keys(right).sort(); return a.length === b.length && a.every((key, index) => key === b[index] && left[key] === right[key]) }
async function copyDirectory (source, target, relative = '') {
  await fsp.mkdir(target, { recursive: true, mode: 0o700 })
  for (const name of await fsp.readdir(source)) {
    const from = path.join(source, name); const to = path.join(target, name); const rel = path.join(relative, name); const info = await fsp.lstat(from)
    if (runtimeCache(rel)) continue
    if (info.isSymbolicLink()) fail('UPDATE_VERIFY', '심볼릭 링크가 포함된 스킬은 설치할 수 없습니다.')
    if (info.isDirectory()) await copyDirectory(from, to, rel)
    else if (info.isFile()) await fsp.copyFile(from, to)
    else fail('UPDATE_VERIFY', '일반 파일과 폴더 외의 항목은 설치할 수 없습니다.')
  }
}
async function bundle (source = root) {
  const rootInfo = await fsp.lstat(source).catch(() => null)
  if (!rootInfo || !rootInfo.isDirectory() || rootInfo.isSymbolicLink()) fail('UPDATE_VERIFY', '스킬 묶음 경로가 올바르지 않습니다.')
  const manifest = await readJson(path.join(source, 'manifest.json'), 'UPDATE_VERIFY', 'manifest.json을 읽을 수 없습니다.')
  const bundleVersion = await fsp.readFile(path.join(source, 'VERSION'), 'utf8').then(value => value.trim()).catch(() => '')
  if (manifest?.schemaVersion !== 1 || manifest?.name !== 'music-road-skills' || !stable(manifest?.version) || manifest.version !== bundleVersion || !Array.isArray(manifest.skills) || manifest.skills.length !== MANAGED_SKILLS.length) fail('UPDATE_VERIFY', '스킬 묶음 manifest 또는 VERSION이 올바르지 않습니다.')
  const ids = new Set(); const skills = []
  for (const item of manifest.skills) {
    if (!item || typeof item.id !== 'string' || !/^[a-z0-9-]+$/.test(item.id) || ids.has(item.id) || item.path !== `skills/${item.id}`) fail('UPDATE_VERIFY', 'manifest의 스킬 경로가 올바르지 않습니다.')
    ids.add(item.id)
    const directory = path.resolve(source, item.path)
    if (!isInside(source, directory) || !fs.existsSync(path.join(directory, 'SKILL.md'))) fail('UPDATE_VERIFY', `스킬 ${item.id}에 SKILL.md가 없습니다.`)
    await noSymlinks(directory)
    const files = await tree(directory)
    if (!Object.keys(files).length) fail('UPDATE_VERIFY', `스킬 ${item.id}이 비어 있습니다.`)
    skills.push({ id: item.id, directory, files })
  }
  if (MANAGED_SKILLS.some(id => !ids.has(id))) fail('UPDATE_VERIFY', 'manifest는 Road Music 관리 스킬 6개를 모두 등록해야 합니다.')
  return { source, version: manifest.version, manifest, skills }
}
async function localBundleVersion (source = root) {
  const manifest = await readJson(path.join(source, 'manifest.json'), 'UPDATE_VERIFY', 'manifest.json을 읽을 수 없습니다.')
  const version = await fsp.readFile(path.join(source, 'VERSION'), 'utf8').then(value => value.trim()).catch(() => '')
  if (manifest?.schemaVersion !== 1 || manifest?.name !== 'music-road-skills' || !stable(manifest?.version) || manifest.version !== version || !Array.isArray(manifest.skills) || manifest.skills.length !== MANAGED_SKILLS.length || MANAGED_SKILLS.some(id => !manifest.skills.some(item => item?.id === id && item.path === `skills/${id}`))) fail('UPDATE_VERIFY', '스킬 묶음 manifest 또는 VERSION이 올바르지 않습니다.')
  return version
}
async function loadState (target) {
  if (!fs.existsSync(statePath(target))) return null
  if ((await fsp.lstat(statePath(target))).isSymbolicLink()) fail('UPDATE_VERIFY', '업데이트 상태 파일은 심볼릭 링크일 수 없습니다.')
  const state = await readJson(statePath(target), 'UPDATE_VERIFY', '기존 업데이트 상태 파일이 손상되었습니다.')
  if (state?.schemaVersion !== 1 || !stable(state?.version) || !state?.skills || Array.isArray(state.skills) || typeof state.skills !== 'object') fail('UPDATE_VERIFY', '기존 업데이트 상태 파일이 올바르지 않습니다.')
  for (const [id, item] of Object.entries(state.skills)) {
    if (!/^[a-z0-9-]+$/.test(id) || !item || item.path !== id || !item.files || Array.isArray(item.files) || typeof item.files !== 'object') fail('UPDATE_VERIFY', '기존 업데이트 상태의 스킬 경로가 올바르지 않습니다.')
    for (const [name, hash] of Object.entries(item.files)) if (!name || path.isAbsolute(name) || name.includes('\\') || name.split(path.sep).some(part => part === '..') || !/^[a-f0-9]{64}$/.test(hash)) fail('UPDATE_VERIFY', '기존 업데이트 상태의 파일 해시가 올바르지 않습니다.')
  }
  return state
}
async function writeState (target, value) {
  await fsp.mkdir(stateDirectory(target), { recursive: true, mode: 0o700 })
  const temporary = `${statePath(target)}.${randomName()}.tmp`
  try { await fsp.writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600, flag: 'wx' }); await fsp.rename(temporary, statePath(target)) } finally { await fsp.rm(temporary, { force: true }).catch(() => {}) }
}
async function installedStatus (target) {
  const state = await loadState(target)
  if (!state) return { installed: false, target, version: null, locallyModified: [] }
  const locallyModified = []
  for (const [id, recorded] of Object.entries(state.skills)) {
    const directory = path.join(target, id)
    if (!fs.existsSync(directory)) { locallyModified.push(id); continue }
    try { if (!sameTree(await tree(directory), recorded.files)) locallyModified.push(id) } catch { locallyModified.push(id) }
  }
  return { installed: true, target, version: state.version, installedAt: state.installedAt, locallyModified }
}
async function assertTarget (target) {
  const info = await fsp.lstat(target).catch(error => error.code === 'ENOENT' ? null : Promise.reject(error))
  if (info?.isSymbolicLink()) fail('UPDATE_VERIFY', '스킬 대상 경로는 심볼릭 링크일 수 없습니다.')
  const stateInfo = await fsp.lstat(stateDirectory(target)).catch(error => error.code === 'ENOENT' ? null : Promise.reject(error))
  if (stateInfo?.isSymbolicLink()) fail('UPDATE_VERIFY', '업데이트 관리 경로는 심볼릭 링크일 수 없습니다.')
}
async function lockTarget (target) {
  await assertTarget(target); await fsp.mkdir(target, { recursive: true, mode: 0o700 }); await fsp.mkdir(stateDirectory(target), { recursive: true, mode: 0o700 }); await assertTarget(target)
  const lock = path.join(stateDirectory(target), '.lock')
  try {
    const handle = await fsp.open(lock, 'wx', 0o600)
    try { await handle.writeFile(`${JSON.stringify({ pid: process.pid, hostname: os.hostname(), startedAt: new Date().toISOString() })}\n`) } catch (error) { await handle.close(); await fsp.rm(lock, { force: true }).catch(() => {}); throw error }
    return async () => { await handle.close(); await fsp.rm(lock, { force: true }) }
  } catch (error) {
    if (error?.code !== 'EEXIST') throw error
    const owner = await fsp.readFile(lock, 'utf8').then(value => JSON.parse(value)).catch(() => null)
    const details = owner?.hostname && Number.isSafeInteger(owner?.pid) ? ` 잠금 소유자: ${owner.hostname} pid ${owner.pid}, 시작 ${owner.startedAt || '알 수 없음'}.` : ''
    fail('TARGET_BUSY', `같은 스킬 대상에 설치 또는 업데이트가 진행 중이거나 이전 작업 잠금이 남아 있습니다.${details} 실행 중인 작업이 없음을 확인한 뒤 ${lock}만 삭제하고 다시 시도하세요.`)
  }
}
async function validateExisting (target, candidate, previous) {
  const priorSkills = previous?.skills || {}
  for (const oldId of Object.keys(priorSkills)) {
    const directory = path.join(target, oldId)
    if (!fs.existsSync(directory) || !sameTree(await tree(directory), priorSkills[oldId].files)) fail('LOCAL_MODIFIED', `로컬에서 바뀐 스킬을 보존했습니다: ${oldId}`)
  }
  for (const item of candidate.skills) {
    const destination = path.join(target, item.id)
    if (!fs.existsSync(destination)) continue
    const actual = await tree(destination)
    if (priorSkills[item.id]) continue
    if (!sameTree(actual, item.files)) fail('TARGET_CONFLICT', `관리되지 않는 기존 스킬과 충돌합니다: ${item.id}`)
  }
}

function githubReleaseUrl (version) { return `https://github.com/${REPOSITORY}/releases/tag/v${version}` }
function githubAssetUrl (version, name) { return `https://github.com/${REPOSITORY}/releases/download/v${version}/${name}` }
function strictUrl (value, expected) { return value === expected }
function safeRedirect (value) {
  try {
    const url = new URL(value)
    if (url.protocol !== 'https:' || url.username || url.password || url.port) return false
    if (/^(github-releases|release-assets|objects)\.githubusercontent\.com$/.test(url.hostname)) return true
    return url.hostname === 'github.com' && new RegExp(`^/${REPOSITORY}/releases/download/v\\d+\\.\\d+\\.\\d+/(MusicRoad-Skills-\\d+\\.\\d+\\.\\d+\\.zip|SHA256SUMS\\.txt)$`).test(url.pathname)
  } catch { return false }
}
async function request (url, { timeoutMs = REQUEST_MS, redirect = 0 } = {}) {
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const headers = { Accept: 'application/vnd.github+json', 'User-Agent': 'music-road-skills-updater' }
    if (new URL(url).hostname === 'api.github.com' && process.env.GH_TOKEN) headers.Authorization = `Bearer ${process.env.GH_TOKEN}`
    const response = await fetch(url, { headers, signal: controller.signal, redirect: 'manual' })
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const next = response.headers.get('location')
      if (redirect >= 4 || !next || !safeRedirect(next)) fail('UPDATE_VERIFY', '허용되지 않은 Release 다운로드 주소입니다.')
      clearTimeout(timer); return request(next, { timeoutMs, redirect: redirect + 1 })
    }
    responseControls.set(response, { controller, timer })
    return response
  } catch (error) { clearTimeout(timer); if (error instanceof SkillsError) throw error; fail('UPDATE_NETWORK', `GitHub Release 조회에 실패했습니다: ${String(error.message || error)}`) }
}
function finishResponse (response) { const control = responseControls.get(response); if (control) { clearTimeout(control.timer); responseControls.delete(response) } }
async function discardResponse (response) { try { await response.body?.cancel() } catch {} finally { finishResponse(response) } }
async function responseText (response) {
  if (!response.body) { finishResponse(response); return '' }
  const reader = response.body.getReader(); const chunks = []; let size = 0; const control = responseControls.get(response)
  try {
    while (true) { const part = await reader.read(); if (part.done) break; size += part.value.byteLength; if (size > MAX_TEXT_BYTES) { await reader.cancel().catch(() => {}); fail('UPDATE_VERIFY', 'Release 응답이 너무 큽니다.') } chunks.push(part.value) }
    return Buffer.concat(chunks).toString('utf8')
  } catch (error) { if (control?.controller.signal.aborted) fail('UPDATE_NETWORK', 'Release 응답 수신 시간이 초과되었습니다.'); throw error
  } finally { reader.releaseLock(); finishResponse(response) }
}
function normalizeRelease (release) {
  const match = /^v(\d+\.\d+\.\d+)$/.exec(String(release?.tag_name || '')); if (!match || release?.draft || release?.prerelease || !stable(match[1])) return null
  const version = match[1]; const name = `MusicRoad-Skills-${version}.zip`; const assets = Array.isArray(release.assets) ? release.assets : []
  const asset = assets.find(row => row?.name === name && Number.isSafeInteger(row.size) && row.size > 0 && row.size <= MAX_ARCHIVE_BYTES && strictUrl(row.browser_download_url, githubAssetUrl(version, name)))
  const sums = assets.find(row => row?.name === 'SHA256SUMS.txt' && Number.isSafeInteger(row.size) && row.size > 0 && row.size <= MAX_TEXT_BYTES && strictUrl(row.browser_download_url, githubAssetUrl(version, 'SHA256SUMS.txt')))
  if (!asset || !sums || !strictUrl(release.html_url, githubReleaseUrl(version))) return null
  return { version, releaseUrl: release.html_url, notes: String(release.body || ''), asset: { name, size: asset.size, url: asset.browser_download_url, sumsUrl: sums.browser_download_url } }
}
async function latestRelease () {
  const response = await request(`${API}?per_page=100`); if (!response.ok) { const status = response.status; await discardResponse(response); fail('UPDATE_NETWORK', `Release 목록을 조회할 수 없습니다(HTTP ${status}).`) }
  const body = await responseText(response); let value; try { value = JSON.parse(body) } catch { fail('UPDATE_VERIFY', 'Release 목록 형식이 올바르지 않습니다.') }
  if (!Array.isArray(value)) fail('UPDATE_VERIFY', 'Release 목록 형식이 올바르지 않습니다.')
  return value.map(normalizeRelease).filter(Boolean).sort((a, b) => compareVersion(b.version, a.version))[0] || null
}
async function check (params = {}) {
  assertParams(params, ['target', 'host'])
  const target = resolveTarget(params); const local = await installedStatus(target); const currentVersion = local.version || await localBundleVersion(); const release = await latestRelease()
  return { ...local, currentVersion, repository: REPOSITORY, available: !!release && compareVersion(release.version, currentVersion) > 0, latest: release ? { version: release.version, releaseUrl: release.releaseUrl, notes: release.notes, asset: release.asset.name } : null }
}
function checksumFor (text, name) { for (const line of text.split(/\r?\n/)) { const match = /^([a-fA-F0-9]{64})\s+\*?(.+)$/.exec(line); if (match && match[2] === name) return match[1].toLowerCase() } return null }
async function run (command, args, maxOutput = 8 * 1024 * 1024) { return await new Promise((resolve, reject) => { const child = spawn(command, args, { stdio: ['ignore', 'pipe', 'pipe'] }); let out = ''; let err = ''; let overflow = false; const append = (kind, value) => { if (overflow) return; const next = kind === 'out' ? out.length + value.length : err.length + value.length; if (next > maxOutput) { overflow = true; child.kill(); return } if (kind === 'out') out += value; else err += value }; child.stdout.on('data', value => append('out', value)); child.stderr.on('data', value => append('err', value)); child.on('error', reject); child.on('close', code => overflow ? reject(new Error(`${command} 출력 한도를 넘었습니다.`)) : code === 0 ? resolve({ out, err }) : reject(new Error(err || `${command} 종료 코드 ${code}`))) }) }
function unsafeZipPath (name) { return !name || name.includes('\\') || name.startsWith('/') || name.split('/').some(part => part === '..') }
async function inspectZip (archive, version) {
  if (process.platform === 'win32') fail('UNSUPPORTED', 'Windows에서는 안전한 ZIP 설치를 지원하지 않습니다.')
  let names; let listing
  try { names = (await run('/usr/bin/unzip', ['-Z1', archive])).out; listing = (await run('/usr/bin/zipinfo', ['-l', archive])).out } catch { fail('UPDATE_VERIFY', '안전한 ZIP 검증 도구(unzip/zipinfo)를 실행할 수 없습니다.') }
  const prefix = `MusicRoad-Skills-${version}`; const entries = names.split(/\r?\n/).filter(Boolean)
  const exact = new Set(); const folded = new Set()
  if (!entries.length || entries.length > MAX_ZIP_ENTRIES || entries.some(name => { const canonical = name.normalize('NFC').toLowerCase(); return unsafeZipPath(name) || exact.has(name) || (exact.add(name), false) || folded.has(canonical) || (folded.add(canonical), false) }) || entries.some(name => name !== prefix && !name.startsWith(`${prefix}/`))) fail('UPDATE_VERIFY', 'ZIP 경로, 항목 수, 중복 항목 또는 최상위 폴더가 안전하지 않습니다.')
  if (listing.split(/\r?\n/).some(line => /^l/.test(line))) fail('UPDATE_VERIFY', '심볼릭 링크가 포함된 ZIP은 설치할 수 없습니다.')
  let expanded = 0
  for (const line of listing.split(/\r?\n/)) {
    if (!/^[?d-]/.test(line)) continue
    const columns = line.trim().split(/\s+/); const size = Number(columns[3])
    if (!Number.isSafeInteger(size) || size < 0) fail('UPDATE_VERIFY', 'ZIP 크기 정보를 검증할 수 없습니다.')
    expanded += size; if (expanded > MAX_EXPANDED_BYTES) fail('UPDATE_VERIFY', 'ZIP 압축 해제 크기가 허용 한도를 넘습니다.')
  }
}
async function downloadRelease (release, stage) {
  const sums = await request(release.asset.sumsUrl); if (!sums.ok) { const status = sums.status; await discardResponse(sums); fail('UPDATE_NETWORK', `체크섬을 받을 수 없습니다(HTTP ${status}).`) }
  const expected = checksumFor(await responseText(sums), release.asset.name); if (!expected) fail('UPDATE_VERIFY', 'SHA256SUMS.txt에 스킬 ZIP 체크섬이 없습니다.')
  const response = await request(release.asset.url, { timeoutMs: DOWNLOAD_MS }); if (!response.ok || !response.body) { const status = response.status; await discardResponse(response); fail('UPDATE_NETWORK', `스킬 ZIP을 받을 수 없습니다(HTTP ${status}).`) }
  const size = Number(response.headers.get('content-length') || 0); if (size && size !== release.asset.size) { await discardResponse(response); fail('UPDATE_VERIFY', 'Release 자산 크기가 메타데이터와 다릅니다.') }
  const destination = path.join(stage, release.asset.name); const handle = await fsp.open(destination, 'wx', 0o600); const hash = crypto.createHash('sha256'); let bytes = 0; const control = responseControls.get(response)
  try {
    for await (const chunk of response.body) { bytes += chunk.length; if (bytes > release.asset.size || bytes > MAX_ARCHIVE_BYTES) fail('UPDATE_VERIFY', '스킬 ZIP이 예상보다 큽니다.'); hash.update(chunk); await handle.write(chunk) }
    if (bytes !== release.asset.size || hash.digest('hex') !== expected) fail('UPDATE_VERIFY', '스킬 ZIP 체크섬 검증에 실패했습니다.')
  } catch (error) { await fsp.rm(destination, { force: true }).catch(() => {}); if (control?.controller.signal.aborted) fail('UPDATE_NETWORK', '스킬 ZIP 수신 시간이 초과되었습니다.'); throw error } finally { await handle.close(); finishResponse(response) }
  await inspectZip(destination, release.version)
  try { await run('/usr/bin/unzip', ['-q', destination, '-d', stage]) } catch { fail('UPDATE_VERIFY', '스킬 ZIP 압축 해제에 실패했습니다.') }
  return path.join(stage, `MusicRoad-Skills-${release.version}`)
}

async function installBundle (source, target, params) {
  const unlock = await lockTarget(target)
  let staging; let backup; const moved = []; const replaced = []
  try {
    const candidate = await bundle(source); const previous = await loadState(target)
    if (previous?.version && compareVersion(candidate.version, previous.version) < 0) fail('UPDATE_DOWNGRADE', '낮은 버전으로 설치할 수 없습니다.')
    await validateExisting(target, candidate, previous)
    staging = await fsp.mkdtemp(path.join(stateDirectory(target), '.stage-')); backup = path.join(stateDirectory(target), 'backups', `${new Date().toISOString().replace(/[:.]/g, '-')}-${randomName()}`)
    event(params, 'stage', { version: candidate.version })
    for (const item of candidate.skills) { const staged = path.join(staging, item.id); await copyDirectory(item.directory, staged); if (!sameTree(await tree(staged), item.files)) fail('UPDATE_VERIFY', `스테이지 파일 해시가 원본과 다릅니다: ${item.id}`) }
    await validateExisting(target, candidate, await loadState(target))
    for (const item of candidate.skills) {
      const destination = path.join(target, item.id)
      if (fs.existsSync(destination)) { await fsp.mkdir(backup, { recursive: true, mode: 0o700 }); await fsp.rename(destination, path.join(backup, item.id)); moved.push(item.id) }
      await fsp.rename(path.join(staging, item.id), destination); replaced.push(item.id)
    }
    const next = { schemaVersion: 1, repository: REPOSITORY, version: candidate.version, installedAt: new Date().toISOString(), source: path.resolve(source), skills: Object.fromEntries(candidate.skills.map(item => [item.id, { path: item.id, files: item.files }])) }
    await writeState(target, next)
    event(params, 'installed', { version: candidate.version })
    return { installed: true, target, version: candidate.version, skills: candidate.skills.map(item => item.id), backup: moved.length ? backup : null }
  } catch (error) {
    const recovery = []
    for (const id of replaced.reverse()) { try { await fsp.rm(path.join(target, id), { recursive: true, force: true }) } catch (rollbackError) { recovery.push(`${id}: 새 파일 제거 실패 (${rollbackError.code || rollbackError.message})`) } }
    for (const id of moved.reverse()) { const destination = path.join(target, id); const archived = path.join(backup, id); try { if (fs.existsSync(destination)) await fsp.rm(destination, { recursive: true, force: true }); await fsp.rename(archived, destination) } catch (rollbackError) { recovery.push(`${id}: 백업 복원 실패 (${rollbackError.code || rollbackError.message})`) } }
    event(params, 'rollback', { reason: error.code || 'INSTALL_FAILED', backup: backup || null, recovered: recovery.length === 0 })
    if (recovery.length) throw new SkillsError('ROLLBACK_FAILED', `${error.message}; 복구가 완전하지 않습니다. 백업: ${backup}; ${recovery.join('; ')}`)
    throw error
  } finally { if (staging) await fsp.rm(staging, { recursive: true, force: true }).catch(() => {}); await unlock().catch(() => {}) }
}
async function install (params = {}) {
  assertParams(params, ['target', 'source', 'host']); const target = resolveTarget(params)
  if (params.source) {
    const source = path.resolve(params.source); const local = await installedStatus(target); const candidate = await bundle(source)
    if (local.version && compareVersion(candidate.version, local.version) < 0) fail('UPDATE_DOWNGRADE', '낮은 버전으로 설치할 수 없습니다.')
    return installBundle(source, target, params)
  }
  const release = await latestRelease(); if (!release) fail('UPDATE_NOT_FOUND', '설치 가능한 정식 Release를 찾지 못했습니다.')
  const stageParent = await fsp.mkdtemp(path.join(os.tmpdir(), 'music-road-skills-'))
  try { event(params, 'download', { version: release.version }); return await installBundle(await downloadRelease(release, stageParent), target, params) } finally { await fsp.rm(stageParent, { recursive: true, force: true }).catch(() => {}) }
}
async function update (params = {}) {
  assertParams(params, ['target', 'source', 'host']); const target = resolveTarget(params); const local = await installedStatus(target)
  if (!local.installed && !params.source) fail('NOT_INSTALLED', '먼저 install로 스킬 묶음을 설치하세요.')
  if (params.source) {
    const source = path.resolve(params.source); const candidate = await bundle(source)
    if (local.version && compareVersion(candidate.version, local.version) < 0) fail('UPDATE_DOWNGRADE', '낮은 버전으로 자동 업데이트할 수 없습니다.')
    if (local.version === candidate.version) return { updated: false, target, version: local.version, reason: 'UP_TO_DATE' }
    return { ...(await installBundle(source, target, params)), updated: true }
  }
  const release = await latestRelease(); if (!release || !local.version || compareVersion(release.version, local.version) <= 0) return { updated: false, target, version: local.version, reason: 'UP_TO_DATE' }
  const stageParent = await fsp.mkdtemp(path.join(os.tmpdir(), 'music-road-skills-'))
  try { event(params, 'download', { version: release.version }); const result = await installBundle(await downloadRelease(release, stageParent), target, params); return { ...result, updated: true } } finally { await fsp.rm(stageParent, { recursive: true, force: true }).catch(() => {}) }
}
async function watch (params = {}) {
  assertParams(params, ['target', 'host', 'timeoutMs', 'intervalMs']); const timeoutMs = params.timeoutMs === undefined ? 60_000 : params.timeoutMs; const intervalMs = params.intervalMs === undefined ? 15_000 : params.intervalMs
  const started = Date.now(); const initial = await check({ target: params.target, host: params.host }); let latest = initial.latest?.version || null; event(params, 'watching', { latest })
  if (initial.available) { event(params, 'available', { latest }); return { ...initial, changed: true, initialAvailable: true } }
  while (Date.now() - started < timeoutMs) {
    await new Promise(resolve => setTimeout(resolve, Math.min(intervalMs, timeoutMs - (Date.now() - started))))
    const current = await check({ target: params.target, host: params.host }); const next = current.latest?.version || null
    if (next !== latest) { event(params, 'changed', { previous: latest, latest: next }); return { ...current, changed: true, previous: latest } }
    latest = next
  }
  event(params, 'timeout', { latest }); return { ...initial, changed: false, timedOut: true }
}
async function execute (action, params = {}) {
  if (!['status', 'check', 'install', 'update', 'watch'].includes(action)) fail('INVALID_ACTION', 'action은 status, check, install, update, watch 중 하나여야 합니다.')
  if (action === 'status') { assertParams(params, ['target', 'host']); return installedStatus(resolveTarget(params)) }
  if (action === 'check') return check(params)
  if (action === 'install') return install(params)
  if (action === 'update') return update(params)
  return watch(params)
}
function cliParams (args) {
  const result = {}; for (let index = 0; index < args.length; index += 2) { const flag = args[index]; const value = args[index + 1]; if (!flag?.startsWith('--') || value === undefined) fail('INVALID_ARGUMENT', '사용법: manage.cjs status|check|install|update|watch [--host codex|claude|antigravity|antigravity-cli] [--target 절대경로] [--source 절대경로] [--timeout-ms 숫자] [--interval-ms 숫자]'); const key = flag.slice(2); const mapped = { host: 'host', target: 'target', source: 'source', 'timeout-ms': 'timeoutMs', 'interval-ms': 'intervalMs' }[key]; if (!mapped || Object.hasOwn(result, mapped)) fail('INVALID_ARGUMENT', `지원하지 않는 옵션입니다: ${flag}`); result[mapped] = mapped.endsWith('Ms') ? Number(value) : value }
  return result
}
if (require.main === module) {
  const [action, ...args] = process.argv.slice(2)
  try {
    const params = cliParams(args); params.onEvent = value => process.stderr.write(`${JSON.stringify(value)}\n`)
    execute(action, params).then(value => process.stdout.write(`${JSON.stringify({ ok: true, result: value })}\n`)).catch(error => { process.stderr.write(`${JSON.stringify({ event: 'error', code: error.code || 'ERROR', message: error.message })}\n`); process.stdout.write(`${JSON.stringify({ ok: false, error: { code: error.code || 'ERROR', message: error.message } })}\n`); process.exitCode = 1 })
  } catch (error) { process.stderr.write(`${JSON.stringify({ event: 'error', code: error.code || 'ERROR', message: error.message })}\n`); process.stdout.write(`${JSON.stringify({ ok: false, error: { code: error.code || 'ERROR', message: error.message } })}\n`); process.exitCode = 1 }
}
module.exports = { execute, SkillsError, _private: { bundle, inspectZip, latestRelease, localBundleVersion, normalizeRelease, sameTree, tree } }

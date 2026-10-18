'use strict'
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const os = require('node:os')
const { test } = require('node:test')
const { execute, _private } = require('../skills/road-music-skills-update/scripts/manage.cjs')

const ids = ['road-music-showreel-cd', 'road-music-showreel-mv', 'road-music-jizura-playlist', 'road-music-showreel-playlist', 'road-music-video-studio', 'road-music-skills-update']
async function fixture (parent, version, marker = version) {
  const root = path.join(parent, `bundle-${version}`); await fs.mkdir(path.join(root, 'skills'), { recursive: true })
  const skills = []
  for (const id of ids) {
    const directory = path.join(root, 'skills', id)
    await fs.mkdir(directory, { recursive: true })
    await fs.writeFile(path.join(directory, 'SKILL.md'), `---\nname: ${id}\ndescription: test\n---\n${marker}\n`)
    if (id === 'road-music-video-studio') {
      await fs.mkdir(path.join(directory, 'assets', 'design', 'fonts'), { recursive: true })
      await fs.writeFile(path.join(directory, 'assets', 'design', 'DESIGN.md'), '# shared design\n')
      await fs.writeFile(path.join(directory, 'assets', 'design', 'fonts', 'Paperlogy-7Bold.ttf'), 'font fixture\n')
    }
    skills.push({ id, path: `skills/${id}` })
  }
  await fs.writeFile(path.join(root, 'manifest.json'), JSON.stringify({ schemaVersion: 1, name: 'music-road-skills', version, skills }))
  await fs.writeFile(path.join(root, 'VERSION'), `${version}\n`)
  return root
}
async function temporary (callback) { const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'road-music-skills-test-')); try { return await callback(directory) } finally { await fs.rm(directory, { recursive: true, force: true }) } }

test('Claude installs into its config skills directory and explicit targets still win', async () => temporary(async base => {
  const previous = process.env.CLAUDE_CONFIG_DIR
  const config = path.join(base, 'Claude configuration')
  process.env.CLAUDE_CONFIG_DIR = config
  try {
    const source = await fixture(base, '0.1.0')
    const installed = await execute('install', { source, host: 'claude' })
    assert.equal(installed.target, path.join(config, 'skills'))
    assert.deepEqual(installed.skills, ids)
    assert.equal((await execute('status', { host: 'claude' })).version, '0.1.0')
    const target = path.join(base, 'project', '.claude', 'skills')
    assert.equal((await execute('install', { source, host: 'claude', target })).target, target)
    assert.equal((await execute('status', { host: 'claude', target })).locallyModified.length, 0)
    await assert.rejects(execute('status', { host: 'claude-web' }), error => error.code === 'INVALID_ARGUMENT')
  } finally {
    if (previous === undefined) delete process.env.CLAUDE_CONFIG_DIR
    else process.env.CLAUDE_CONFIG_DIR = previous
  }
}))

test('local bundle installs, adopts exact existing files, and reports status', async () => temporary(async base => {
  const source = await fixture(base, '0.1.0'); const target = path.join(base, 'target')
  const installed = await execute('install', { source, target })
  assert.deepEqual(installed.skills, ids); assert.equal((await execute('status', { target })).version, '0.1.0')
  const adopted = path.join(base, 'adopted'); await fs.mkdir(adopted); for (const id of ids) await fs.cp(path.join(source, 'skills', id), path.join(adopted, id), { recursive: true })
  assert.equal((await execute('install', { source, target: adopted })).version, '0.1.0')
}))

test('installs all six managed skills and shared design/font assets as one bundle', async () => temporary(async base => {
  const source = await fixture(base, '0.1.0'); const target = path.join(base, 'target')
  const installed = await execute('install', { source, target })
  assert.deepEqual(installed.skills, ids)
  assert.equal(await fs.readFile(path.join(target, 'road-music-video-studio', 'assets', 'design', 'DESIGN.md'), 'utf8'), '# shared design\n')
  assert.equal(await fs.readFile(path.join(target, 'road-music-video-studio', 'assets', 'design', 'fonts', 'Paperlogy-7Bold.ttf'), 'utf8'), 'font fixture\n')
  assert.equal((await execute('status', { target })).locallyModified.length, 0)
}))

test('rejects a bundle that omits one of the six managed skills', async () => temporary(async base => {
  const source = await fixture(base, '0.1.0')
  const manifest = JSON.parse(await fs.readFile(path.join(source, 'manifest.json'), 'utf8'))
  manifest.skills = manifest.skills.filter(item => item.id !== 'road-music-skills-update')
  await fs.writeFile(path.join(source, 'manifest.json'), JSON.stringify(manifest))
  await assert.rejects(execute('install', { source, target: path.join(base, 'target') }), error => error.code === 'UPDATE_VERIFY')
}))

test('update preserves a versioned backup and rejects local modifications', async () => temporary(async base => {
  const first = await fixture(base, '0.1.0', 'old'); const second = await fixture(base, '0.1.1', 'new'); const third = await fixture(base, '0.1.2', 'later'); const target = path.join(base, 'target')
  await execute('install', { source: first, target }); const updated = await execute('update', { source: second, target })
  assert.equal(updated.updated, true); assert.ok(updated.backup); assert.match(await fs.readFile(path.join(target, ids[0], 'SKILL.md'), 'utf8'), /new/)
  await fs.appendFile(path.join(target, ids[0], 'SKILL.md'), 'local edit\n')
  await assert.rejects(execute('update', { source: third, target }), error => error.code === 'LOCAL_MODIFIED')
  const downgradeTarget = path.join(base, 'downgrade'); await execute('install', { source: second, target: downgradeTarget })
  await assert.rejects(execute('install', { source: first, target: downgradeTarget }), error => error.code === 'UPDATE_DOWNGRADE')
  await assert.rejects(execute('update', { source: first, target: downgradeTarget }), error => error.code === 'UPDATE_DOWNGRADE')
}))

test('failed replacement rolls back every moved skill', async () => temporary(async base => {
  const first = await fixture(base, '0.1.0', 'old'); const second = await fixture(base, '0.1.1', 'new'); const target = path.join(base, 'target')
  await execute('install', { source: first, target })
  const nativeRename = fs.rename; let moves = 0
  fs.rename = async (from, to) => { if (from.includes('.stage-') && ids.some(id => to.endsWith(path.sep + id)) && ++moves === 2) throw Object.assign(new Error('simulated failure'), { code: 'EIO' }); return nativeRename(from, to) }
  try { await assert.rejects(execute('update', { source: second, target })) } finally { fs.rename = nativeRename }
  for (const id of ids) assert.match(await fs.readFile(path.join(target, id, 'SKILL.md'), 'utf8'), /old/)
  assert.equal((await execute('status', { target })).version, '0.1.0')
}))

test('malicious ZIP paths are rejected before extraction', async () => temporary(async base => {
  const archive = path.join(base, 'evil.zip')
  const { spawnSync } = require('node:child_process')
  const code = "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1],'w'); z.writestr('../escape.txt','no'); z.close()"
  assert.equal(spawnSync('python3', ['-c', code, archive]).status, 0)
  await assert.rejects(_private.inspectZip(archive, '0.1.0'), error => error.code === 'UPDATE_VERIFY')
}))

test('lock, state symlink and zero watch interval are rejected before mutation', async () => temporary(async base => {
  const source = await fixture(base, '0.1.0'); const target = path.join(base, 'target'); await fs.mkdir(path.join(target, '.music-road-skills'), { recursive: true }); await fs.writeFile(path.join(target, '.music-road-skills', '.lock'), 'busy')
  await assert.rejects(execute('install', { source, target }), error => error.code === 'TARGET_BUSY')
  await fs.rm(path.join(target, '.music-road-skills', '.lock')); await fs.rm(target, { recursive: true }); await fs.symlink(path.join(base, 'elsewhere'), target, 'dir')
  await assert.rejects(execute('install', { source, target }), error => error.code === 'UPDATE_VERIFY')
  await assert.rejects(execute('watch', { target: path.join(base, 'fresh'), intervalMs: 0 }), error => error.code === 'INVALID_ARGUMENT')
}))

test('event sink failures cannot roll back a committed install', async () => temporary(async base => {
  const source = await fixture(base, '0.1.0'); const target = path.join(base, 'target')
  const result = await execute('install', { source, target, onEvent: () => { throw new Error('observer failed') } })
  assert.equal(result.version, '0.1.0'); assert.equal((await execute('status', { target })).locallyModified.length, 0)
}))

test('target edits during staging are retained instead of being overwritten', async () => temporary(async base => {
  const first = await fixture(base, '0.1.0', 'old'); const second = await fixture(base, '0.1.1', 'new'); const target = path.join(base, 'target'); await execute('install', { source: first, target })
  const nativeCopy = fs.copyFile; let changed = false
  fs.copyFile = async (...args) => { await nativeCopy(...args); if (!changed) { changed = true; await fs.appendFile(path.join(target, ids[0], 'SKILL.md'), 'manual edit\n') } }
  try { await assert.rejects(execute('update', { source: second, target }), error => error.code === 'LOCAL_MODIFIED') } finally { fs.copyFile = nativeCopy }
  assert.match(await fs.readFile(path.join(target, ids[0], 'SKILL.md'), 'utf8'), /old[\s\S]*manual edit/)
}))

test('a source changed between preflight and lock cannot downgrade installed skills', async () => temporary(async base => {
  const installed = await fixture(base, '0.1.1', 'installed'); const source = await fixture(base, '0.1.2', 'candidate'); const target = path.join(base, 'target'); await execute('install', { source: installed, target })
  const nativeRead = fs.readFile; const versionFile = path.join(source, 'VERSION'); let reads = 0
  fs.readFile = async (...args) => { const value = await nativeRead(...args); if (args[0] === versionFile && ++reads === 1) { await fs.writeFile(path.join(source, 'manifest.json'), JSON.stringify({ schemaVersion: 1, name: 'music-road-skills', version: '0.1.0', skills: ids.map(id => ({ id, path: `skills/${id}` })) })); await fs.writeFile(versionFile, '0.1.0\n') } return value }
  try { await assert.rejects(execute('install', { source, target }), error => error.code === 'UPDATE_DOWNGRADE') } finally { fs.readFile = nativeRead }
  assert.equal((await execute('status', { target })).version, '0.1.1')
}))

test('runtime Python caches do not block updates but source edits still do', async () => temporary(async base => {
  const first = await fixture(base, '0.1.0', 'old'); const second = await fixture(base, '0.1.1', 'new'); const third = await fixture(base, '0.1.2', 'later'); const target = path.join(base, 'target'); await execute('install', { source: first, target })
  const skill = path.join(target, ids[3]); await fs.mkdir(path.join(skill, 'scripts', '__pycache__'), { recursive: true }); await fs.writeFile(path.join(skill, 'scripts', '__pycache__', 'helper.cpython-313.pyc'), 'cache'); await fs.writeFile(path.join(skill, '.DS_Store'), 'cache')
  assert.deepEqual((await execute('status', { target })).locallyModified, [])
  assert.equal((await execute('update', { source: second, target })).version, '0.1.1')
  await fs.appendFile(path.join(target, ids[3], 'SKILL.md'), 'actual edit\n')
  await assert.rejects(execute('update', { source: third, target }), error => error.code === 'LOCAL_MODIFIED')
}))

test('oversized release response keeps its verification error instead of becoming JSON error', async () => {
  const nativeFetch = global.fetch
  let cancelled = false
  const body = new ReadableStream({ start (controller) { controller.enqueue(new TextEncoder().encode('x'.repeat(1024 * 1024 + 1))) }, cancel () { cancelled = true } })
  global.fetch = async () => new Response(body, { status: 200 })
  try { await assert.rejects(_private.latestRelease(), error => error.code === 'UPDATE_VERIFY' && /너무 큽니다/.test(error.message)); assert.equal(cancelled, true) } finally { global.fetch = nativeFetch }
})

test('an unmanaged source checkout compares its manifest version before reporting an update', async () => temporary(async base => {
  const nativeFetch = global.fetch; const target = path.join(base, 'unmanaged-skills'); const version = require('../manifest.json').version; const asset = `MusicRoad-Skills-${version}.zip`
  global.fetch = async () => new Response(JSON.stringify([{ tag_name: `v${version}`, draft: false, prerelease: false, html_url: `https://github.com/roadkwonai/music-road-skills/releases/tag/v${version}`, assets: [{ name: asset, size: 1, browser_download_url: `https://github.com/roadkwonai/music-road-skills/releases/download/v${version}/${asset}` }, { name: 'SHA256SUMS.txt', size: 1, browser_download_url: `https://github.com/roadkwonai/music-road-skills/releases/download/v${version}/SHA256SUMS.txt` }] }]), { status: 200 })
  try { const result = await execute('check', { target }); assert.equal(result.installed, false); assert.equal(result.currentVersion, version); assert.equal(result.available, false) } finally { global.fetch = nativeFetch }
}))

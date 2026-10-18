'use strict'
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const os = require('node:os')
const { test } = require('node:test')
const { spawnSync } = require('node:child_process')
const { verifyReleaseVersion } = require('../scripts/release-version.cjs')

async function fixture () {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'road-music-release-test-'))
  await fs.mkdir(path.join(root, 'release')); await fs.writeFile(path.join(root, 'VERSION'), '0.1.0\n'); await fs.writeFile(path.join(root, 'manifest.json'), JSON.stringify({ name: 'music-road-skills', version: '0.1.0', releaseNotes: 'release/2026-10-18-first-release.md' }))
  await fs.writeFile(path.join(root, 'release', '2026-10-18-first-release.md'), '---\nversion: 0.1.0\ntitle: First release\n---\n\nnotes\n')
  return root
}
test('release version accepts the first version and rejects duplicate tags', async () => {
  const root = await fixture()
  try {
    const result = await verifyReleaseVersion(root, { tag: 'v0.1.0', releases: [] }); assert.equal(result.title, 'First release')
    await assert.rejects(verifyReleaseVersion(root, { tag: 'v0.1.0', releases: [{ tag_name: 'v0.1.0' }] }), /이미 존재/)
  } finally { await fs.rm(root, { recursive: true, force: true }) }
})

test('release builder packs only the allow-listed bundle tree', async () => {
  const root = await fixture()
  try {
    await fs.mkdir(path.join(root, 'skills', 'road-music-showreel-cd'), { recursive: true })
    const manifest = { schemaVersion: 1, name: 'music-road-skills', version: '0.1.0', skills: [{ id: 'road-music-showreel-cd', path: 'skills/road-music-showreel-cd' }] }
    await fs.writeFile(path.join(root, 'manifest.json'), JSON.stringify(manifest)); await fs.writeFile(path.join(root, 'skills', 'road-music-showreel-cd', 'SKILL.md'), '---\nname: test\ndescription: test\n---\n')
    for (const name of ['README.md', 'LICENSE', 'AGENTS.md', 'DESIGN.md']) await fs.writeFile(path.join(root, name), name)
    await fs.mkdir(path.join(root, 'scripts', '__pycache__'), { recursive: true }); await fs.writeFile(path.join(root, 'scripts', '__pycache__', 'ignored.pyc'), 'cache')
    const script = path.resolve(__dirname, '..', 'scripts', 'build-release.py'); const output = path.join(root, 'out')
    const built = spawnSync('python3', [script, '--root', root, '--out', output], { encoding: 'utf8' })
    assert.equal(built.status, 0, built.stderr)
    const archive = path.join(output, 'MusicRoad-Skills-0.1.0.zip'); assert.ok((await fs.stat(archive)).size > 0)
    const names = spawnSync('/usr/bin/unzip', ['-Z1', archive], { encoding: 'utf8' }).stdout
    assert.match(names, /MusicRoad-Skills-0.1.0\/README.md/); assert.match(names, /MusicRoad-Skills-0.1.0\/skills\/road-music-showreel-cd\/SKILL.md/); assert.match(names, /MusicRoad-Skills-0.1.0\/DESIGN.md/); assert.doesNotMatch(names, /__pycache__/)
  } finally { await fs.rm(root, { recursive: true, force: true }) }
})

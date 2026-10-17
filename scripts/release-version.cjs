#!/usr/bin/env node
'use strict'
const fs = require('node:fs/promises')
const path = require('node:path')

function valid (version) { return typeof version === 'string' && /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version) }
function parts (version) { return valid(version) ? version.split('.').map(Number) : null }
function compare (left, right) { const a = parts(left); const b = parts(right); return a[0] - b[0] || a[1] - b[1] || a[2] - b[2] }
async function metadata (root) {
  const manifest = JSON.parse(await fs.readFile(path.join(root, 'manifest.json'), 'utf8')); const version = (await fs.readFile(path.join(root, 'VERSION'), 'utf8')).trim()
  if (manifest?.name !== 'music-road-skills' || manifest.version !== version || !valid(version)) throw new Error('manifest.json과 VERSION의 정식 버전이 일치하지 않습니다.')
  return { version, manifest }
}
async function releaseNote (root, version) {
  const directory = path.join(root, 'release'); const names = await fs.readdir(directory); const found = []
  for (const name of names) {
    if (!/^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$/.test(name)) continue
    const file = path.join(directory, name); const body = await fs.readFile(file, 'utf8'); const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/.exec(body)
    if (!match) continue
    const values = Object.fromEntries(match[1].split(/\r?\n/).map(line => line.match(/^([a-zA-Z][\w-]*):\s*(.+)\s*$/)).filter(Boolean).map(item => [item[1], item[2].replace(/^['"]|['"]$/g, '')]))
    if (values.version === version) found.push({ path: file, title: values.title || `Music Road Skills v${version}`, body })
  }
  if (found.length !== 1) throw new Error(`release/에는 v${version}을 가리키는 YYYY-MM-DD-title.md가 정확히 하나 있어야 합니다.`)
  return found[0]
}
async function verifyReleaseVersion (root, { tag, releases }) {
  const { version, manifest } = await metadata(root); if (tag !== `v${version}`) throw new Error('태그와 VERSION이 일치하지 않습니다.')
  if (!Array.isArray(releases)) throw new Error('Release 목록은 배열이어야 합니다.')
  if (releases.some(row => row?.tag_name === tag)) throw new Error('이미 존재하는 Release 버전은 다시 게시할 수 없습니다.')
  const notes = await releaseNote(root, version)
  if (manifest.releaseNotes !== path.relative(root, notes.path).split(path.sep).join('/')) throw new Error('manifest.releaseNotes는 현재 버전의 release 노트를 가리켜야 합니다.')
  const history = releases.filter(row => !row?.draft && !row?.prerelease && /^v\d+\.\d+\.\d+$/.test(row?.tag_name || '')).map(row => row.tag_name.slice(1)).sort((a, b) => compare(b, a))
  const previousVersion = history[0] || null
  if (previousVersion) { const [major, minor, patch] = parts(previousVersion); if (![`${major}.${minor}.${patch + 1}`, `${major}.${minor + 1}.0`, `${major + 1}.0.0`].includes(version)) throw new Error(`버전은 ${previousVersion}에서 한 단계만 올릴 수 있습니다.`) } else if (version !== '0.1.0') throw new Error('첫 정식 버전은 0.1.0이어야 합니다.')
  return { version, tag, previousVersion, notePath: notes.path, title: notes.title }
}
async function main () {
  const [tag, file] = process.argv.slice(2); if (!tag || !file || process.argv.length !== 4) throw new Error('사용법: release-version.cjs vX.Y.Z releases.json')
  const pages = JSON.parse(await fs.readFile(file, 'utf8')); const releases = Array.isArray(pages) ? pages.flat() : null
  console.log(JSON.stringify(await verifyReleaseVersion(path.resolve(__dirname, '..'), { tag, releases })))
}
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1 })
module.exports = { verifyReleaseVersion, releaseNote }

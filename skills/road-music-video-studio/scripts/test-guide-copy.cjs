'use strict'
const assert = require('node:assert/strict')
const { test } = require('node:test')
const { spawnSync } = require('node:child_process')
const vm = require('node:vm')

const rendered = spawnSync(process.env.SHOWREEL_PYTHON || 'python3', ['-c', 'from guide_content import render_guide; print(render_guide("cli"))'], { cwd: __dirname, encoding: 'utf8' })
assert.equal(rendered.status, 0, rendered.stderr)
const script = rendered.stdout.match(/<script>([\s\S]*?)<\/script>/)[1]

function fixture () {
  const element = () => ({ textContent: '', value: '', hidden: true, disabled: false, events: {}, addEventListener (name, fn) { this.events[name] = fn }, focus () { this.focused = true }, select () { this.selected = true } })
  const nodes = Object.fromEntries(['guide-topics', 'guide-on-page', 'guide-markdown', 'copy-markdown', 'copy-status', 'copy-fallback', 'guide-example-1', 'guide-example-2'].map(id => [id, element()]))
  nodes['guide-markdown'].textContent = JSON.stringify('# 문서 전체\n\n명령과 <원문>')
  nodes['guide-example-1'].textContent = 'python3 "$STUDIO_SKILL/scripts/studio.py" init \\\n  --out "$PROJECT_DIR"'
  nodes['guide-example-2'].textContent = '원가사 <유지> & "줄바꿈"\n추정 싱크는 구분해 주세요.'
  const examples = [1, 2].map(number => {
    const button = element(); const status = element(); const box = element()
    button.dataset = { copyExample: `guide-example-${number}` }
    button.closest = () => ({ querySelector: selector => selector === 'textarea' ? box : status })
    return { button, status, box }
  })
  const copied = []
  const navigator = { clipboard: { writeText: async value => { copied.push(value) } } }
  vm.runInNewContext(script, { navigator, matchMedia: () => ({ matches: false }), addEventListener () {}, innerHeight: 900, document: { getElementById: id => nodes[id], querySelectorAll: selector => selector === '[data-copy-example]' ? examples.map(item => item.button) : [] } })
  return { nodes, examples, copied, navigator }
}

test('each guide copy button copies only the exact block; whole Markdown stays separate', async () => {
  const { nodes, examples, copied } = fixture()
  for (const [index, item] of examples.entries()) {
    item.button.events.click()
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(copied[index], nodes[`guide-example-${index + 1}`].textContent)
    assert.equal(item.status.textContent, '복사했습니다.')
    assert.equal(item.box.hidden, true)
    assert.equal(item.button.disabled, false)
  }
  await nodes['copy-markdown'].events.click({ currentTarget: nodes['copy-markdown'] })
  assert.equal(copied.at(-1), JSON.parse(nodes['guide-markdown'].textContent))
})

test('clipboard denial reveals selected read-only fallback and retry clears it', async () => {
  const { nodes, examples, navigator } = fixture()
  navigator.clipboard.writeText = async () => { throw new Error('blocked') }
  const item = examples[1]
  item.button.events.click()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(item.box.hidden, false)
  assert.equal(item.box.value, nodes['guide-example-2'].textContent)
  assert.equal(item.box.focused && item.box.selected, true)
  assert.match(item.status.textContent, /Ctrl\+C/)
  assert.equal(item.button.disabled, false)
  assert.equal(examples[0].box.hidden, true)
  navigator.clipboard.writeText = async () => {}
  item.button.events.click()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(item.box.hidden, true)
  assert.equal(item.box.value, '')
})

#!/usr/bin/env node
import assert from 'node:assert/strict';
import { validateDirecting } from './directing.mjs';

const context = { sourceSha256: 'a'.repeat(64), sourceDuration: 4, fps: 24, fxIds: ['shake', 'flash'], schemeCount: 2 };
const valid = {
  schemaVersion: 1, sourceSha256: 'A'.repeat(64),
  accents: [{ time: 1, type: 'shake', amp: 1, dur: 1 / 24 }],
  schemes: [{ start: 0, end: 2, index: 0 }, { start: 2, end: 4, index: 1 }],
  motifs: [{ lines: [0, 2] }],
};
assert.deepEqual(validateDirecting(valid, context).schemes.map(s => s.index), [0, 1]);
for (const [key, value] of [
  ['NaN', { ...valid, accents: [{ ...valid.accents[0], time: NaN }] }],
  ['unknown-id', { ...valid, accents: [{ ...valid.accents[0], type: 'missing' }] }],
  ['out-of-time', { ...valid, accents: [{ ...valid.accents[0], time: 4.01 }] }],
  ['overlap', { ...valid, schemes: [{ start: 0, end: 3, index: 0 }, { start: 2, end: 4, index: 1 }] }],
]) assert.throws(() => validateDirecting(value, context), Error, key);
console.log(JSON.stringify({ ok: true, cases: 5 }));

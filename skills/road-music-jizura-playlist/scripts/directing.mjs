const fail = message => { throw new Error(message); };
const finite = (value, name) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(`${name}: 유한한 숫자가 필요합니다`);
  return value;
};

/** Validate the portable directing score before it is baked by JIZURA itself. */
export function validateDirecting(value, context) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail('directing은 객체여야 합니다');
  const { sourceSha256, sourceDuration, fps, fxIds, schemeCount } = context;
  if (value.schemaVersion !== 1) fail('directing.schemaVersion은 1이어야 합니다');
  if (typeof value.sourceSha256 !== 'string' || value.sourceSha256.toLowerCase() !== String(sourceSha256).toLowerCase()) fail('directing.sourceSha256과 실제 원음 해시가 다릅니다');
  const duration = finite(sourceDuration, 'sourceDuration');
  const frame = 1 / finite(fps, 'fps');
  if (duration <= 0 || frame <= 0) fail('원음 길이와 FPS가 필요합니다');
  if (!Array.isArray(value.accents)) fail('directing.accents는 배열이어야 합니다');
  const accents = value.accents.map((accent, index) => {
    if (!accent || typeof accent !== 'object' || Array.isArray(accent)) fail(`accents[${index}]는 객체여야 합니다`);
    const time = finite(accent.time, `accents[${index}].time`);
    const amp = finite(accent.amp, `accents[${index}].amp`);
    const dur = finite(accent.dur, `accents[${index}].dur`);
    if (time < 0 || time > duration) fail(`accents[${index}].time이 원음 범위를 벗어납니다`);
    if (amp < 0 || amp > 2) fail(`accents[${index}].amp는 0..2여야 합니다`);
    if (dur < frame || dur > .5) fail(`accents[${index}].dur는 1프레임..0.5초여야 합니다`);
    if (typeof accent.type !== 'string' || !fxIds.includes(accent.type)) fail(`accents[${index}].type은 JIZURA 등록 FX여야 합니다`);
    return { time, type: accent.type, amp, dur };
  });
  const schemes = value.schemes == null ? [] : value.schemes;
  if (!Array.isArray(schemes)) fail('directing.schemes는 배열이어야 합니다');
  const normalizedSchemes = schemes.map((scheme, index) => {
    if (!scheme || typeof scheme !== 'object' || Array.isArray(scheme)) fail(`schemes[${index}]는 객체여야 합니다`);
    const start = finite(scheme.start, `schemes[${index}].start`), end = finite(scheme.end, `schemes[${index}].end`);
    if (start < 0 || end > duration || end <= start) fail(`schemes[${index}] 구간이 원음 범위를 벗어납니다`);
    if (!Number.isInteger(scheme.index) || scheme.index < 0 || scheme.index >= schemeCount) fail(`schemes[${index}].index가 스타일 색면 범위를 벗어납니다`);
    return { start, end, index: scheme.index };
  }).sort((a, b) => a.start - b.start || a.end - b.end);
  for (let index = 1; index < normalizedSchemes.length; index++) if (normalizedSchemes[index].start < normalizedSchemes[index - 1].end) fail('directing.schemes 구간은 겹칠 수 없습니다');
  const motifs = value.motifs == null ? [] : value.motifs;
  if (!Array.isArray(motifs)) fail('directing.motifs는 배열이어야 합니다');
  const normalizedMotifs = motifs.map((motif, index) => {
    if (!motif || typeof motif !== 'object' || Array.isArray(motif) || !Array.isArray(motif.lines) || motif.lines.length < 2) fail(`motifs[${index}].lines는 2개 이상의 행이어야 합니다`);
    const lines = motif.lines.map(line => {
      if (!Number.isInteger(line) || line < 0) fail(`motifs[${index}].lines는 0 이상의 정수여야 합니다`);
      return line;
    });
    if (new Set(lines).size !== lines.length) fail(`motifs[${index}].lines에 중복 행이 있습니다`);
    return { lines };
  });
  return { schemaVersion: 1, sourceSha256: value.sourceSha256.toLowerCase(), accents, schemes: normalizedSchemes, motifs: normalizedMotifs };
}

/**
 * The returned source only calls public JIZURA objects. It snapshots native cuts,
 * stores the snapshots in overrides, then asks the normal UI replanner to restore them.
 */
export function browserBakeExpression(directing, sourceSha256, sourceDuration = null) {
  return `(() => {
    const score = ${JSON.stringify(directing)};
    const fail = message => { throw new Error(message); };
    const finite = (v, n) => { if (typeof v !== 'number' || !Number.isFinite(v)) fail(n + ': 유한한 숫자가 필요합니다'); return v; };
    const sourceDuration = finite(${JSON.stringify(sourceDuration)} || (J.ui.audio && J.ui.audio.duration), '실제 원음 길이');
    const fps = finite(J.ui.plan && J.ui.plan.fps, 'JIZURA FPS');
    const fxIds = Object.keys(J.FXE || {});
    const schemeCount = (J.resolveStyle(J.ui.project).schemes || []).length;
    if (!score || score.schemaVersion !== 1 || typeof score.sourceSha256 !== 'string' || score.sourceSha256.toLowerCase() !== ${JSON.stringify(String(sourceSha256).toLowerCase())}) fail('directing.sourceSha256과 실제 원음 해시가 다릅니다');
    if (!Array.isArray(score.accents)) fail('directing.accents는 배열이어야 합니다');
    const frame = 1 / fps;
    const accents = score.accents.map((a, i) => {
      if (!a || typeof a !== 'object') fail('accents[' + i + ']는 객체여야 합니다');
      const time = finite(a.time, 'accents[' + i + '].time'), amp = finite(a.amp, 'accents[' + i + '].amp'), dur = finite(a.dur, 'accents[' + i + '].dur');
      if (time < 0 || time > sourceDuration || amp < 0 || amp > 2 || dur < frame || dur > .5 || typeof a.type !== 'string' || !fxIds.includes(a.type)) fail('directing accent 값이 JIZURA 범위를 벗어납니다: ' + i);
      return { time, type: a.type, amp, dur };
    });
    const schemes = score.schemes == null ? [] : score.schemes;
    if (!Array.isArray(schemes)) fail('directing.schemes는 배열이어야 합니다');
    const orderedSchemes = schemes.map((s, i) => {
      if (!s || typeof s !== 'object') fail('schemes[' + i + ']는 객체여야 합니다');
      const start = finite(s.start, 'schemes[' + i + '].start'), end = finite(s.end, 'schemes[' + i + '].end');
      if (start < 0 || end > sourceDuration || end <= start || !Number.isInteger(s.index) || s.index < 0 || s.index >= schemeCount) fail('directing scheme 값이 JIZURA 범위를 벗어납니다: ' + i + ' (index=' + s.index + ', schemeCount=' + schemeCount + ', duration=' + sourceDuration + ')');
      return { start, end, index: s.index };
    }).sort((a, b) => a.start - b.start || a.end - b.end);
    for (let i = 1; i < orderedSchemes.length; i++) if (orderedSchemes[i].start < orderedSchemes[i - 1].end) fail('directing.schemes 구간은 겹칠 수 없습니다');
    const motifs = score.motifs == null ? [] : score.motifs;
    if (!Array.isArray(motifs)) fail('directing.motifs는 배열이어야 합니다');
    const snapByLine = new Map();
    const need = new Set();
    const lyricCuts = J.ui.plan.cuts.filter(c => c && c.line >= 0 && typeof c.utext === 'string');
    const assigned = [];
    const unassigned = [];
    for (const accent of accents) {
      const cut = lyricCuts.find(c => accent.time >= c.start && accent.time < c.end);
      if (!cut) { unassigned.push({ ...accent, reason: 'active-lyric-cut 없음' }); continue; }
      assigned.push({ ...accent, line: cut.line, cutStart: cut.start, dt: +(accent.time - cut.start).toFixed(4) }); need.add(cut.line);
    }
    if (unassigned.length) return { ok: false, matched: assigned.length, unassigned, count: accents.length, actualAppliedEvents: [], motifs: [], lockedLines: [] };
    for (const cut of lyricCuts) if (orderedSchemes.some(s => cut.start >= s.start && cut.start < s.end)) need.add(cut.line);
    const checkedMotifs = motifs.map((m, group) => {
      if (!m || !Array.isArray(m.lines) || m.lines.length < 2 || new Set(m.lines).size !== m.lines.length || m.lines.some(i => !Number.isInteger(i) || i < 0)) fail('motifs[' + group + '].lines가 올바르지 않습니다');
      for (const line of m.lines) need.add(line);
      return { lines: m.lines.slice() };
    });
    for (const line of need) {
      const snapshot = J.lineSnapshot(J.ui.plan, line);
      if (!snapshot) fail('directing 대상 행에 native lyric cut이 없습니다: ' + line);
      snapByLine.set(line, snapshot);
    }
    const appearance = ['layout', 'enter', 'exit', 'hold', 'inDur', 'outDur', 'params', 'decor', 'treat', 'treatP', 'bg', 'bgP', 'cam', 'camP', 'trans', 'transP', 'transDur', 'morph', 'weightGrow', 'kime', 'recap', 'twinParams', 'seed'];
    for (const motif of checkedMotifs) {
      const source = snapByLine.get(motif.lines[0]);
      for (const line of motif.lines.slice(1)) {
        const target = snapByLine.get(line);
        if (target.length !== source.length || target.some((cut, index) => cut.utext !== source[index].utext)) fail('motifs 행은 같은 utext cut 구성이어야 합니다: ' + motif.lines.join(','));
        target.forEach((cut, index) => {
          const sourceCut = source[index];
          for (const key of appearance) cut[key] = JSON.parse(JSON.stringify(sourceCut[key]));
        });
      }
    }
    for (const [line, snapshot] of snapByLine) for (let index = 0; index < snapshot.length; index++) {
      const live = lyricCuts.filter(c => c.line === line)[index];
      const scheme = orderedSchemes.find(s => live && live.start >= s.start && live.start < s.end);
      if (scheme) snapshot[index].scheme = scheme.index;
    }
    const round = number => +number.toFixed(4);
    for (const hit of assigned) {
      const snapshot = snapByLine.get(hit.line);
      const cut = lyricCuts.filter(c => c.line === hit.line).find(c => hit.time >= c.start && hit.time < c.end);
      const index = lyricCuts.filter(c => c.line === hit.line).indexOf(cut);
      const events = Array.isArray(snapshot[index].events) ? snapshot[index].events.slice() : [];
      events.push({ dt: hit.dt, type: hit.type, amp: hit.amp, dur: hit.dur });
      const latest = new Map();
      for (const event of events) {
        const key = round(event.dt) + '|' + event.type;
        latest.set(key, event);
      }
      snapshot[index].events = [...latest.values()].sort((a, b) => a.dt - b.dt || a.type.localeCompare(b.type));
    }
    J.ui.project.overrides = J.ui.project.overrides || {};
    for (const [line, snapshot] of snapByLine) J.ui.project.overrides[line] = Object.assign({}, J.ui.project.overrides[line] || {}, { lock: true, lockedCuts: snapshot });
    J.ui.project.directingProvenance = JSON.parse(JSON.stringify(score));
    delete J.ui.project.directing;
    J.uiApi.replan();
    const actualCuts = J.ui.plan.cuts.filter(c => c && c.line >= 0 && typeof c.utext === 'string');
    const latestAssigned = new Map();
    for (const hit of assigned) latestAssigned.set(hit.line + '|' + round(hit.dt) + '|' + hit.type, hit);
    const actualAppliedEvents = [...latestAssigned.values()].map(hit => {
      const cut = actualCuts.find(c => c.line === hit.line && hit.time >= c.start && hit.time < c.end);
      const expectedTime = cut ? cut.start + hit.dt : NaN;
      const event = J.ui.plan.events.find(e => cut && e.type === hit.type && Math.abs(e.t - expectedTime) < .00011 && e.amp === hit.amp && e.dur === hit.dur);
      if (!event) fail('directing accent이 재계획에서 보존되지 않았습니다: ' + hit.type + '@' + hit.time);
      return { time: event.t, type: event.type, amp: event.amp, dur: event.dur, line: hit.line, dt: hit.dt };
    });
    return { ok: true, matched: assigned.length, unassigned, count: accents.length, actualAppliedEvents, motifs: checkedMotifs.map(m => ({ lines: m.lines, applied: true })), lockedLines: [...snapByLine.keys()].sort((a, b) => a - b) };
  })()`;
}

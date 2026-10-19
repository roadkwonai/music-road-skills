"""Responsive, semantic guide diagrams using the existing Paperlogy tokens."""
import html
from ui_icons import icon as heroicon


_ICON_NAMES = {
    'music': 'musical-note', 'settings': 'adjustments-horizontal', 'film': 'film',
    'files': 'document-duplicate', 'check': 'check-circle',
    'text': 'document-text', 'image': 'photo',
}


def _icon(name):
    return '<span class="rm-diagram-icon" aria-hidden="true">' + heroicon(_ICON_NAMES[name]) + '</span>'


def _steps(items):
    return '<ol class="rm-diagram-flow">' + ''.join(
        '<li>' + _icon(icon) + '<div><span class="rm-diagram-index" aria-hidden="true">' + str(index) + '</span><strong>' + html.escape(title) + '</strong><p>' + html.escape(description) + '</p></div></li>'
        for index, (icon, title, description) in enumerate(items, 1)
    ) + '</ol>'


def render_diagram(name):
    if name == 'production-flow.svg':
        return '<div class="rm-diagram">' + _steps([
            ('music', '원음 확인', '음악과 승인된 원가사를 확인합니다.'),
            ('settings', '제작 방향', '방식·스타일·화면 표시를 저장합니다.'),
            ('film', '스킬로 제작', '가사 싱크와 비트에 맞춰 렌더합니다.'),
            ('files', '결과 등록', '실제 완성 파일을 같은 음악에 모읍니다.'),
            ('check', '검수·보완', '재생하며 확인하고 필요하면 수정합니다.'),
        ]) + '<p class="rm-diagram-note">설정 저장 → 담당 스킬의 실제 제작 → 완성 파일 확인. 각 단계는 별도 작업입니다.</p></div>'
    if name == 'work-map.svg':
        items = [
            ('files', '요약', '원음과 전체 파일 상태'), ('film', '영상·스타일', '스타일별 완성본 비교'),
            ('music', '음원', '사용 원음과 완성 음원'), ('text', '가사·자막', '원문과 시간 자막'),
            ('image', '스토리보드', '장면 구성과 검수 이미지'), ('check', '검수·제작 기록', '프로젝트별 의견과 근거'),
        ]
        return ('<div class="rm-diagram"><div class="rm-diagram-root">' + _icon('music') + '<div><strong>내 작업물 목록 → 음악별 상세</strong><p>같은 원음으로 만든 스타일과 버전을 한곳에서 확인합니다.</p></div></div>'
                '<ul class="rm-diagram-map">' + ''.join('<li>' + _icon(icon) + '<strong>' + title + '</strong><p>' + description + '</p></li>' for icon, title, description in items) + '</ul>'
                '<p class="rm-diagram-note">음악 그룹 ZIP에는 사용한 원음과 등록된 완성 파일이 함께 담깁니다.</p></div>')
    if name == 'sync-review.svg':
        return ('<div class="rm-diagram"><div class="rm-diagram-root">' + _icon('text') + '<div><strong>원가사는 유지하고 원음·영상·자막을 대조</strong><p>가창 시작과 끝을 직접 확인할 근거가 충분한가요?</p></div></div>'
                '<dl class="rm-diagram-branches"><div><dt>확정 싱크</dt><dd>근거가 충분할 때</dd><dd>확인한 시각과 근거를 기록합니다.</dd></div>'
                '<div><dt>추정 싱크</dt><dd>근거가 부족할 때</dd><dd>추정 범위·사유를 남기고 다시 확인합니다.</dd></div></dl>'
                '<p class="rm-diagram-note"><strong>두 경우 모두 가독성 검수</strong><br>잘림·줄바꿈·잔상·배경 대비를 확인하고, 수정한 구간을 다시 재생합니다. 자동 판정 결과를 뜻하지 않습니다.</p></div>')
    if name == 'style-energy.svg':
        items = [
            ('verse', '벌스', 'Mint 중심', '절제 · 가사를 읽는 데 집중'),
            ('chorus', '후렴', 'Crimson + Acid', '강조 · 비트와 색 전환'),
            ('bridge', '브리지', 'Mint 중심', '호흡 · 다음 후렴과 대비'),
            ('final', '마지막 후렴', 'Acid + Crimson', '가장 강하게 · 가독성은 유지'),
        ]
        return ('<div class="rm-diagram"><ol class="rm-diagram-energy">' + ''.join(
            '<li><div><strong>' + title + '</strong><span>' + style + '</span></div><p>' + description + '</p><span class="rm-energy-track" aria-hidden="true"><span class="rm-energy-' + key + '"></span></span></li>'
            for key, title, style, description in items
        ) + '</ol><p class="rm-diagram-note">Crimson · Mint · Acid 조합의 연출 예시입니다. 막대는 상대적인 표현 강약이며 실제 설정값이 아닙니다.</p></div>')
    if name == 'display-choices.svg':
        return ('<div class="rm-diagram"><p class="rm-diagram-lead"><strong>예시: 이전 설정은 스펙트럼 표시</strong></p><ul class="rm-diagram-options">'
                '<li>' + _icon('settings') + '<strong>표시</strong><span class="rm-display-demo">화면에 스펙트럼</span><p>이번 설정을 표시로 지정합니다.</p></li>'
                '<li>' + _icon('image') + '<strong>표시 안 함</strong><span class="rm-display-demo rm-display-empty">스펙트럼 숨김</span><p>이번 설정을 숨김으로 지정합니다.</p></li>'
                '<li>' + _icon('files') + '<strong>SKIP</strong><span class="rm-display-demo">이전 표시 유지</span><p>저장돼 있던 값을 바꾸지 않습니다.</p></li></ul>'
                '<p class="rm-diagram-note">저장된 값이 없는 첫 SKIP은 미지정으로 전달됩니다. SKIP과 표시 안 함은 다른 선택입니다.</p></div>')
    if name == 'lyrics-vs-captions.svg':
        return ('<div class="rm-diagram"><div class="rm-diagram-text-files"><section><strong>원가사 · TXT</strong><p>승인된 문장과 줄바꿈</p>'
                '<pre>오늘도 나의 길을 걸어\n빛을 향해 한 걸음 더</pre></section><section><strong>시간 자막 · SRT</strong><p>같은 문장 + 표시 시작/끝 시각</p>'
                '<pre>1\n00:00:12,000 --&gt; 00:00:14,500\n오늘도 나의 길을 걸어\n\n2\n00:00:14,500 --&gt; 00:00:17,000\n빛을 향해 한 걸음 더</pre></section></div>'
                '<p class="rm-diagram-note">문장과 시각은 형식 설명을 위한 예시입니다. 시간 정보가 있어도 확정 싱크가 되는 것은 아니며, 실제 원음으로 확인해야 합니다.</p></div>')
    if name == 'delivery-map.svg':
        items = [('film', '완성 영상', 'MP4 · MOV · WebM'), ('music', '완성 음원', '제작 후 납품하는 음원'),
                 ('text', '원가사', '승인한 TXT · Markdown'), ('text', '시간 자막', 'SRT · LRC 등 실제 등록 파일'),
                 ('image', '스토리보드', '등록된 장면·검수 이미지')]
        return ('<div class="rm-diagram"><div class="rm-diagram-root">' + _icon('music') + '<div><strong>사용한 원음으로 음악 그룹 구분</strong><p>아래 항목은 실제 완성 파일이 등록된 경우에만 제공됩니다.</p></div></div>'
                '<ul class="rm-diagram-map">' + ''.join('<li>' + _icon(icon) + '<strong>' + title + '</strong><p>' + description + '</p></li>' for icon, title, description in items) + '</ul>'
                '<p class="rm-diagram-note"><strong>음악 그룹 ZIP</strong>사용한 원음과 위 등록 파일을 함께 받습니다. 프로젝트별 의견과 제작 기록은 상세의 검수·제작 기록 메뉴에서 별도로 확인합니다.</p></div>')
    raise ValueError('등록된 가이드 도식이 아닙니다')

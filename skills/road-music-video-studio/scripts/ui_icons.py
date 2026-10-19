"""Bundled Heroicons Solid helpers for regular Road Music HTML pages."""
from __future__ import annotations

import html
from pathlib import Path
import re


ASSET_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'design'
ICON_NAMES = frozenset({
    'adjustments-horizontal', 'arrow-down-tray', 'arrow-path', 'book-open',
    'check-circle', 'chevron-down', 'chevron-right', 'clipboard-document',
    'clipboard-document-check', 'document-duplicate', 'document-text',
    'exclamation-triangle', 'film', 'folder-open', 'information-circle',
    'heart', 'list-bullet', 'musical-note', 'photo', 'play', 'question-mark-circle',
    'squares-2x2', 'x-mark',
})
_CSS_CLASS = re.compile(r'[A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*)*\Z')


def icon(name, css_class='rm-icon'):
    """Return one decorative, allow-listed icon; labels stay in surrounding text."""
    if name not in ICON_NAMES or not isinstance(css_class, str) or not _CSS_CLASS.fullmatch(css_class):
        raise ValueError('등록된 아이콘 이름과 CSS 클래스가 필요합니다')
    return (f'<svg class="{html.escape(css_class, quote=True)}" aria-hidden="true" '
            f'focusable="false"><use href="#rm-icon-{name}"></use></svg>')


def inject_icon_library(page):
    """Inject the local SVG sprite once, only inside a regular HTML body."""
    if 'id="rm-icon-library"' in page:
        return page
    sprite = (ASSET_ROOT / 'heroicons.svg').read_text(encoding='utf-8')
    if not re.search(r'<svg\b[^>]*\bid="rm-icon-library"', sprite, re.I):
        raise ValueError('Heroicons 스프라이트가 올바르지 않습니다')
    return re.sub(r'(<body\b[^>]*>)', lambda match: match[1] + sprite, page, count=1, flags=re.I)

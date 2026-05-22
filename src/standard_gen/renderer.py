from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from markdown_it import MarkdownIt

from .models import StandardDocument, SubSection
from .resolver import Resolver, _slugify

logger = logging.getLogger(__name__)

_md = MarkdownIt().enable('table')

_REQUIREMENTS_MARKER = '<!-- requirements -->'

# Matches ATX headings in markdown (# ... through ###### ...)
_HEADING_LINE_RE = re.compile(r'^(#{1,6})[ \t]+(.+)', re.MULTILINE)
# Matches rendered heading tags without existing id attribute
_HEADING_TAG_RE = re.compile(r'<(h[1-6])>(.*?)</\1>', re.DOTALL)


def _render_markdown(text: str) -> str:
    if not text:
        return ''
    return _md.render(text)


def _normalize_headings(md_text: str, target_min: int = 3) -> str:
    """Shift all headings so the shallowest level maps to target_min."""
    levels = [len(m.group(1)) for m in _HEADING_LINE_RE.finditer(md_text)]
    if not levels:
        return md_text
    offset = target_min - min(levels)
    if offset == 0:
        return md_text

    def adjust(m: re.Match) -> str:
        new_level = max(1, min(6, len(m.group(1)) + offset))
        return '#' * new_level + ' ' + m.group(2)

    return _HEADING_LINE_RE.sub(adjust, md_text)


def _extract_headings(normalized_md: str) -> list[tuple[int, str, str]]:
    """Return [(level, title, slug), ...] from normalized markdown."""
    return [
        (len(m.group(1)), m.group(2).strip(), _slugify(m.group(2).strip()))
        for m in _HEADING_LINE_RE.finditer(normalized_md)
    ]


def _inject_heading_ids(html: str) -> str:
    """Add id attributes to <hN> tags that don't already have one."""
    def replacer(m: re.Match) -> str:
        tag, content = m.group(1), m.group(2)
        text = re.sub(r'<[^>]+>', '', content).strip()
        slug = _slugify(text)
        return f'<{tag} id="{slug}">{content}</{tag}>'
    return _HEADING_TAG_RE.sub(replacer, html)


def _split_intro(text: str) -> str:
    idx = text.find(_REQUIREMENTS_MARKER)
    return text[:idx].strip() if idx >= 0 else text


def _split_outro(text: str) -> str:
    idx = text.find(_REQUIREMENTS_MARKER)
    return text[idx + len(_REQUIREMENTS_MARKER):].strip() if idx >= 0 else ''


def _basename(url: str) -> str:
    return os.path.basename(url.rstrip('/'))


def navigate_schema(schema: dict, json_path: str) -> Optional[dict]:
    """
    Simplified data JSONPath → schema location navigation.
    Supports $.prop, $.prop[*], $.prop[*].sub patterns.
    Does not resolve $ref.
    """
    path = (json_path or '$').strip()
    if path in ('$', '$.', ''):
        return schema
    if path.startswith('$.'):
        path = path[2:]
    elif path.startswith('$'):
        path = path[1:]

    parts = re.split(r'\.|\[(?:\*|\d+)\]\.?', path)
    parts = [p for p in parts if p]

    node = schema
    for part in parts:
        if node is None:
            return None
        if '$ref' in node:
            return None  # ref resolution not supported in PoC
        if 'properties' in node and part in node['properties']:
            node = node['properties'][part]
        elif node.get('type') == 'array' and 'items' in node:
            node = node['items']
            if 'properties' in node and part in node['properties']:
                node = node['properties'][part]
        else:
            return None
    return node


class Renderer:
    def __init__(self, resolver: Resolver, templates_dir: Path):
        self._resolver = resolver
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False,
        )
        self._env.filters['slugify'] = _slugify
        self._env.filters['basename'] = _basename
        self._env.filters['split_intro'] = _split_intro
        self._env.filters['split_outro'] = _split_outro

        self._env.globals['render_markdown'] = self._render_and_resolve
        self._env.globals['get_viewer_url'] = resolver.get_bblock_viewer_url
        self._env.globals['get_property_table'] = self._get_property_table

    def _render_and_resolve(self, text: str) -> str:
        normalized = _normalize_headings(text)
        html = _render_markdown(normalized)
        html = _inject_heading_ids(html)
        return self._resolver.resolve_bblocks_links_in_html(html)

    def _get_property_table(self, applies_to) -> Optional[dict]:
        """Return {properties: [{name, type, format, ref, description}], required: set} or None."""
        if not applies_to or not applies_to.bblock:
            return None
        json_path = applies_to.json_path or '$'
        schema = self._resolver.get_bblock_schema(applies_to.bblock)
        if not schema:
            return None
        node = navigate_schema(schema, json_path)
        if not node or 'properties' not in node:
            return None

        required = set(node.get('required', []))
        props = []
        for name, prop in node['properties'].items():
            # Detect $ref at property level or inside items (for arrays)
            ref = prop.get('$ref')
            items = prop.get('items', {})
            items_ref = items.get('$ref') if isinstance(items, dict) else None
            type_str = prop.get('type', '—')
            props.append({
                'name': name,
                'type': type_str,
                'format': prop.get('format'),
                'ref': ref or items_ref,
                'description': prop.get('description', ''),
                'required': name in required,
            })
        return {'properties': props}

    def _populate_subsections(self, doc: StandardDocument) -> None:
        """Extract top-level subheadings from clause markdown for ToC nesting."""
        from .models import ReqClass
        for section in doc.sections:
            content = section.content
            md = getattr(content, 'description_md', '')
            normalized = _normalize_headings(md) if md else ''
            headings = _extract_headings(normalized) if normalized else []
            subsections = [
                SubSection(title=title, anchor=slug, level=level)
                for level, title, slug in headings
                if level == 3
            ]
            # Auto-inject "Requirements" subsection for req classes that have requirements
            if isinstance(content, ReqClass) and content.requirements:
                subsections.append(SubSection(
                    title='Requirements',
                    anchor=f'req-{section.anchor}-requirements',
                    level=3,
                ))
            section.subsections = subsections

    def render(self, doc: StandardDocument, build_dir: Path) -> None:
        self._populate_subsections(doc)

        build_dir.mkdir(parents=True, exist_ok=True)

        css_src = Path(__file__).parent.parent.parent / 'templates' / 'ogc-standard.css'
        shutil.copy(css_src, build_dir / 'ogc-standard.css')

        template = self._env.get_template('base.html.j2')
        html = template.render(doc=doc)

        out = build_dir / 'index.html'
        out.write_text(html, encoding='utf-8')
        logger.info("Written %s", out)

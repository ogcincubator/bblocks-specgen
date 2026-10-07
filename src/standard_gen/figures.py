from __future__ import annotations

import html
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.attrs import attrs_plugin

from .resolver import Resolver, _slugify

logger = logging.getLogger(__name__)

_SCHEME_RE = re.compile(r'^([a-zA-Z][a-zA-Z0-9+.-]*:|//)')
_IMAGE_EXT_RE = re.compile(r'\.(png|jpe?g|gif|svg|webp)$', re.IGNORECASE)

ASSETS_DIR = 'assets'


@dataclass
class Figure:
    id: str
    label: str      # "3" in the body, "A.1" in an annex
    caption: str


class FigureRegistry:
    """
    Numbers captioned figures, copies local images next to the generated
    document, and resolves cross-references to figures.

    Rendering is done in two passes over the same document (see
    Renderer.render): the first, with the registry unfrozen, discovers and
    numbers every figure in document order; the second, frozen, only looks
    figures up, so cross-references may point at figures that appear later.

    A figure is a captioned image standing alone in its paragraph. It is
    referenced from the text by a Markdown link to the same image path
    (`[](assets/x.png)` becomes "Figure N"; link text, if any, is kept), or
    to an explicit `{#id}` given on the image (`[](#id)`).
    """

    def __init__(self, resolver: Resolver, section_numbers: dict[str, str]):
        self._resolver = resolver
        self._section_numbers = section_numbers
        self._frozen = False
        self._figures: dict[tuple, Figure] = {}
        self._by_ref: dict[str, Figure] = {}
        self._counters: dict[str, int] = {}
        self._used_ids: set[str] = set()
        # source key -> (local path, destination relative to the output dir)
        self.assets: dict[str, tuple[Path, str]] = {}
        self._dest_taken: dict[str, str] = {}

    def freeze(self) -> None:
        self._frozen = True

    # -- image sources ---------------------------------------------------

    def resolve(self, src: str, bblock_id: Optional[str]) -> tuple[str, str]:
        """Return (key, href): a canonical key for the image and the URL to emit."""
        if _SCHEME_RE.match(src):
            return src, src
        bb = self._resolver.get_bblock(bblock_id) if bblock_id else None
        if not bb or not bb.get('sourceFiles'):
            return src, src
        url = urljoin(bb['sourceFiles'].rstrip('/') + '/', src)
        local = self._resolver.local_path(url)
        if local is None:
            return url, url
        path = local.resolve()
        key = str(path)
        if key not in self.assets:
            if not path.is_file():
                raise FileNotFoundError(
                    f"Image '{src}' referenced from {bblock_id} not found: {path}")
            self.assets[key] = (path, self._destination(bblock_id, path.name, key))
        return key, self.assets[key][1]

    def _destination(self, bblock_id: str, name: str, key: str) -> str:
        base = f'{ASSETS_DIR}/{_slugify(bblock_id)}'
        dest, n = f'{base}/{name}', 1
        while self._dest_taken.get(dest, key) != key:
            n += 1
            dest = f'{base}/{Path(name).stem}-{n}{Path(name).suffix}'
        self._dest_taken[dest] = key
        return dest

    def copy_assets(self, out_dir: Path) -> None:
        for path, dest in self.assets.values():
            target = out_dir / dest
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(path, target)

    # -- figures ---------------------------------------------------------

    def figure(self, bblock_id: Optional[str], key: str, caption: str,
               explicit_id: Optional[str]) -> Figure:
        identity = (bblock_id, key, caption, explicit_id)
        fig = self._figures.get(identity)
        if fig or self._frozen:
            if fig is None:
                raise RuntimeError(f"Figure {identity} was not found in the first pass")
            return fig

        number = self._section_numbers.get(bblock_id, '')
        scope = number if re.fullmatch(r'[A-Z]', number) else ''
        n = self._counters[scope] = self._counters.get(scope, 0) + 1
        label = f'{scope}.{n}' if scope else str(n)

        fig_id = explicit_id or 'fig-' + _slugify(Path(key.split('?')[0]).stem or label)
        base, i = fig_id, 1
        while fig_id in self._used_ids:
            i += 1
            fig_id = f'{base}-{i}'
        self._used_ids.add(fig_id)

        fig = Figure(id=fig_id, label=label, caption=caption)
        self._figures[identity] = fig
        self._by_ref.setdefault(key, fig)
        self._by_ref[f'#{fig_id}'] = fig
        return fig

    def lookup(self, href: str, bblock_id: Optional[str]) -> Optional[Figure]:
        if href.startswith('#'):
            return self._by_ref.get(href)
        return self._by_ref.get(self._key_only(href, bblock_id))

    def _key_only(self, href: str, bblock_id: Optional[str]) -> str:
        if _SCHEME_RE.match(href):
            return href
        bb = self._resolver.get_bblock(bblock_id) if bblock_id else None
        if not bb or not bb.get('sourceFiles'):
            return href
        url = urljoin(bb['sourceFiles'].rstrip('/') + '/', href)
        local = self._resolver.local_path(url)
        return str(local.resolve()) if local is not None else url

    @property
    def frozen(self) -> bool:
        return self._frozen


def _inline_text(tokens: list[Token]) -> str:
    return ''.join(t.content for t in tokens if t.type in ('text', 'code_inline'))


def _figures_rule(state) -> None:
    env = state.env
    reg: Optional[FigureRegistry] = env.get('figures')
    if reg is None:
        return
    bblock_id = env.get('bblock')
    tokens = state.tokens

    for i, tok in enumerate(tokens):
        if tok.type != 'inline' or not tok.children:
            continue
        children = tok.children

        for child in children:
            if child.type != 'image':
                continue
            key, href = reg.resolve(child.attrGet('src') or '', bblock_id)
            child.attrSet('src', href)
            alone = (len(children) == 1 and i > 0 and tokens[i - 1].type == 'paragraph_open'
                     and tokens[i + 1].type == 'paragraph_close')
            caption = _inline_text(child.children or []).strip()
            if alone and caption:
                child.meta = {'figure': reg.figure(
                    bblock_id, key, caption, child.attrGet('id'))}
                tokens[i - 1].hidden = tokens[i + 1].hidden = True

        for j, child in enumerate(children):
            if child.type != 'link_open':
                continue
            href = child.attrGet('href') or ''
            fig = reg.lookup(href, bblock_id)
            if fig:
                child.attrSet('href', f'#{fig.id}')
                child.attrSet('class', 'figure-ref')
                if j + 1 < len(children) and children[j + 1].type == 'link_close':
                    text = Token('text', '', 0)
                    text.content = f'Figure {fig.label}'
                    children.insert(j + 1, text)
            elif reg.frozen and _IMAGE_EXT_RE.search(href) and not _SCHEME_RE.match(href):
                logger.warning(
                    "%s: link to image '%s' does not match any figure "
                    "(figures need a caption and must stand alone in their paragraph)",
                    bblock_id, href)


def _render_image(self, tokens, idx, options, env) -> str:
    tok = tokens[idx]
    alt = html.escape(self.renderInlineAsText(tok.children or [], options, env), quote=True)
    img = f'<img src="{html.escape(tok.attrGet("src") or "", quote=True)}" alt="{alt}">'
    fig = (tok.meta or {}).get('figure')
    if not fig:
        return img
    caption = self.renderInline(tok.children, options, env)
    return (f'<figure id="{html.escape(fig.id, quote=True)}">{img}'
            f'<figcaption>Figure {fig.label} — {caption}</figcaption></figure>')


def make_markdown() -> MarkdownIt:
    md = MarkdownIt().enable('table').use(attrs_plugin, after=('image',), spans=False)
    md.core.ruler.push('figures', _figures_rule)
    md.add_render_rule('image', _render_image)
    return md

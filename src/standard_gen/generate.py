from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Optional, Sequence

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .assembler import Assembler
from .loader import Loader
from .models import StandardMetadata
from .renderer import Renderer

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / 'templates'

DEFAULT_STANDARDS_FILE = 'standards.yaml'
DEFAULT_BUILD_DIR = 'standards'

# Written into every <build-dir>/<id>/ folder we generate, so that stale
# folders (e.g. after an id rename) can be cleaned up without ever touching
# anything we didn't create.
_MARKER = '.specgen'

_ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')


def load_standards(path: Path) -> list[dict]:
    """
    Read and validate standards.yaml: a list of standards, or a mapping with
    a top-level 'standards' list. Each entry needs a unique, directory-safe
    'id', plus 'prefix', 'title' and 'base-uri'.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Standards file not found: {path}")

    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if isinstance(data, dict):
        data = data.get('standards')
    if not isinstance(data, list) or not data:
        raise ValueError(
            f"{path}: expected a non-empty list of standards "
            "(or a mapping with a 'standards' list)"
        )

    seen: set[str] = set()
    for i, std in enumerate(data):
        where = f"{path}: standards[{i}]"
        if not isinstance(std, dict):
            raise ValueError(f"{where}: expected a mapping")
        std_id = std.get('id')
        if not std_id:
            raise ValueError(f"{where} (prefix {std.get('prefix')!r}): missing required 'id'")
        if not isinstance(std_id, str) or not _ID_RE.match(std_id):
            raise ValueError(
                f"{where}: invalid id {std_id!r} (letters, digits, '_' and '-' only)"
            )
        if std_id in seen:
            raise ValueError(f"{path}: duplicate standard id {std_id!r}")
        seen.add(std_id)
        for key in ('prefix', 'title', 'base-uri'):
            if not std.get(key):
                raise ValueError(f"{where} (id {std_id!r}): missing required '{key}'")

        if (class_prefix := std.get('class-id-prefix')) is not None:
            prefix = std['prefix'].rstrip('.') + '.'
            if not isinstance(class_prefix, str) or not (class_prefix.rstrip('.') + '.').startswith(prefix):
                raise ValueError(
                    f"{where} (id {std_id!r}): 'class-id-prefix' must be a string starting "
                    f"with the standard's prefix {std['prefix']!r}, got {class_prefix!r}"
                )

    prefixes = [(s['id'], s['prefix']) for s in data]
    for id_a, prefix_a in prefixes:
        for id_b, prefix_b in prefixes:
            if id_a != id_b and prefix_b.startswith(prefix_a):
                logger.warning(
                    "Standard %r (prefix %r) also matches the blocks of %r (prefix %r)",
                    id_a, prefix_a, id_b, prefix_b,
                )
    return data


def _check_build_dir(build_dir: Path, source_dir: Path) -> None:
    build_dir, source_dir = build_dir.resolve(), source_dir.resolve()
    if build_dir == source_dir or build_dir in source_dir.parents:
        raise ValueError(
            f"Refusing to use {build_dir} as build directory: it contains the "
            "repository root"
        )


def _subtitle(metadata: StandardMetadata) -> str:
    parts = [metadata.doc_number, metadata.doc_type, metadata.status, metadata.version]
    return ' · '.join(str(p) for p in parts if p)


def _render_index(entries: list[dict], build_dir: Path, templates_dir: Path) -> None:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(['html', 'j2']),
    )
    html = env.get_template('index.html.j2').render(standards=entries)
    shutil.copy(templates_dir / 'ogc-standard.css', build_dir / 'ogc-standard.css')
    (build_dir / 'index.html').write_text(html, encoding='utf-8')


def _remove_stale(build_dir: Path, current_ids: set[str]) -> None:
    for child in build_dir.iterdir():
        if child.is_dir() and child.name not in current_ids and (child / _MARKER).is_file():
            logger.info("Removing stale standard output %s", child)
            shutil.rmtree(child)


def generate(
    register: dict,
    standards: list[dict],
    *,
    source_dir: Path,
    build_dir: Path,
    only: Optional[Sequence[str]] = None,
    extra_registers: Sequence[dict] = (),
    templates_dir: Path = _TEMPLATES_DIR,
) -> Path:
    """
    Render OGC standards documents from an already-parsed compiled register
    and the (validated, see load_standards()) standards definitions.

    This is the one entry point shared by the standalone CLI (`cli.py`, which
    reads register.json off disk and calls this) and the build-plugin
    (`plugin.py`, which gets the register dict handed to it by the
    bblocks-postprocess build-hook harness).

    Each standard is written to <build_dir>/<id>/index.html, and
    <build_dir>/index.html lists them. `only` restricts generation to the
    given standard ids. Any failure aborts the run; the top-level index is
    only written once every standard has been rendered.

    source_dir is the repo root that the register's local (non-published)
    resources resolve against - see Resolver.local_path().

    Returns the path to the top-level index.html.
    """
    if only:
        known = {s['id'] for s in standards}
        unknown = sorted(set(only) - known)
        if unknown:
            raise ValueError(
                f"Unknown standard id(s) in 'only': {unknown} (available: {sorted(known)})"
            )
        standards = [s for s in standards if s['id'] in set(only)]

    _check_build_dir(build_dir, source_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for std in standards:
        std_id = std['id']
        logger.info("Generating standard %s", std_id)
        loader = Loader(register, std, source_dir, extra_registers=list(extra_registers))
        metadata, clauses, resolver = loader.load()
        doc = Assembler(metadata, clauses, resolver).assemble()

        out_dir = build_dir / std_id
        Renderer(resolver, templates_dir).render(doc, out_dir)
        (out_dir / _MARKER).write_text('', encoding='utf-8')
        (out_dir / 'report.json').write_text(
            json.dumps({'standard': std_id, 'blocks': loader.report}, indent=2) + '\n',
            encoding='utf-8')

        entries.append({
            'id': std_id,
            'title': metadata.title,
            'subtitle': _subtitle(metadata),
        })

    _render_index(entries, build_dir, templates_dir)
    if not only:
        _remove_stale(build_dir, {e['id'] for e in entries})

    out = build_dir / 'index.html'
    logger.info("Written %s", out)
    return out

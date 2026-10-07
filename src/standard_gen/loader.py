from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml
import requests

from .models import (
    StandardMetadata, ReqClass, Requirement, AppliesTo, Dependency,
    TestResource, ProseClause, TermsClause, ReferencesClause,
    Term, Reference, ConformanceClause, AnnexA, Example, Snippet,
)
from .resolver import Resolver

logger = logging.getLogger(__name__)


class Loader:
    """
    Takes an already-parsed compiled register plus one standard's definition
    (an entry from standards.yaml, see generate.load_standards()) and produces
    the raw data objects that Assembler will turn into a StandardDocument.

    Pure in-memory transform - no file/network I/O of its own beyond what
    Resolver.fetch() does while walking clauses (local source files or
    remote bblock resources). Register/extra-register loading (from disk,
    or from a build-plugin hook payload) is the caller's job - see
    generate.generate() for the shared entry point CLI and the build plugin
    both use.
    """

    def __init__(
        self,
        register: dict,
        standard: dict,
        source_dir: Path,
        extra_registers: list[dict] = (),
    ):
        self._register = register
        self._standard = standard
        self._source_dir = source_dir
        self._extra_registers = list(extra_registers)

    def load(self) -> tuple[StandardMetadata, list, Resolver]:
        """
        Returns (metadata, clause_data_list, resolver).
        """
        local_register = self._register
        source_dir = self._source_dir

        std = self._standard
        metadata = _parse_metadata(std)

        imported_bblocks = self._load_imported_registers(local_register)
        for reg in self._extra_registers:
            imported_bblocks.extend(reg.get('bblocks', []))

        resolver = Resolver(metadata, local_register, imported_bblocks, source_dir)

        prefix = std['prefix']
        local_by_id = {
            bb['itemIdentifier']: bb
            for bb in local_register.get('bblocks', [])
            if bb['itemIdentifier'].startswith(prefix)
        }

        clauses = []
        req_classes = []  # collected for auto clauses

        clause_entries = std.get('clauses') or _clauses_from_index(local_by_id)

        for entry in clause_entries:
            if isinstance(entry, dict) and 'auto' in entry:
                clauses.append({'auto': entry['auto']})
                continue

            bblock_id = entry['bblock'] if isinstance(entry, dict) else entry
            bb = local_by_id.get(bblock_id)
            if not bb:
                logger.warning("Clause bblock not found in register: %s", bblock_id)
                continue

            item_class = bb.get('itemClass', 'clause')
            content = self._load_clause(bb, item_class, resolver)
            if content is None:
                continue

            clauses.append(content)
            if isinstance(content, ReqClass):
                req_classes.append(content)

        # Resolve auto entries now that req_classes is complete
        resolved = []
        for entry in clauses:
            if isinstance(entry, dict) and 'auto' in entry:
                auto_type = entry['auto']
                if auto_type == 'conformance':
                    resolved.append(ConformanceClause(req_classes=req_classes))
                elif auto_type == 'annex-a':
                    resolved.append(self._build_annex_a(req_classes, resolver))
                else:
                    logger.warning("Unknown auto clause type: %s", auto_type)
            else:
                resolved.append(entry)

        return metadata, resolved, resolver

    # ------------------------------------------------------------------
    # Clause loading
    # ------------------------------------------------------------------

    def _load_clause(self, bb: dict, item_class: str, resolver: Resolver):
        if item_class in ('clause',):
            return self._load_prose_clause(bb, resolver)
        elif item_class == 'terms':
            return self._load_terms_clause(bb, resolver)
        elif item_class == 'references':
            return self._load_references_clause(bb, resolver)
        elif item_class == 'requirements-class':
            return self._load_req_class(bb, resolver)
        else:
            logger.warning("Unhandled itemClass '%s' for %s — treating as prose",
                           item_class, bb['itemIdentifier'])
            return self._load_prose_clause(bb, resolver)

    def _load_prose_clause(self, bb: dict, resolver: Resolver) -> ProseClause:
        desc_url = bb['sourceFiles'].rstrip('/') + '/description.md'
        try:
            description_md = resolver.fetch(desc_url)
        except Exception as e:
            logger.warning("Could not fetch description.md for %s: %s", bb['itemIdentifier'], e)
            description_md = ''
        return ProseClause(
            bblock_id=bb['itemIdentifier'],
            name=bb['name'],
            description_md=description_md,
            normative=bb.get('normative', True),
        )

    def _load_terms_clause(self, bb: dict, resolver: Resolver) -> TermsClause:
        terms_url = self._resource_url(bb, 'terms')
        terms_data = {}
        if terms_url:
            try:
                terms_data = yaml.safe_load(resolver.fetch(terms_url)) or {}
            except Exception as e:
                logger.warning("Could not fetch terms.yaml for %s: %s", bb['itemIdentifier'], e)

        desc_url = bb['sourceFiles'].rstrip('/') + '/description.md'
        preamble = ''
        try:
            preamble = resolver.fetch(desc_url)
        except Exception:
            pass

        terms = [
            Term(
                term=t['term'],
                definition=t.get('definition', ''),
                sources=t.get('sources', []),
                note=t.get('note'),
            )
            for t in terms_data.get('terms', [])
        ]
        terms.sort(key=lambda t: t.term.lower())

        return TermsClause(
            bblock_id=bb['itemIdentifier'],
            name=bb['name'],
            terms=terms,
            abbreviated_terms=terms_data.get('abbreviated-terms', {}),
            preamble_md=preamble,
        )

    def _load_references_clause(self, bb: dict, resolver: Resolver) -> ReferencesClause:
        refs_url = self._resource_url(bb, 'references')
        refs_data = {}
        if refs_url:
            try:
                refs_data = yaml.safe_load(resolver.fetch(refs_url)) or {}
            except Exception as e:
                logger.warning("Could not fetch references.yaml for %s: %s", bb['itemIdentifier'], e)

        desc_url = bb['sourceFiles'].rstrip('/') + '/description.md'
        preamble = ''
        try:
            preamble = resolver.fetch(desc_url)
        except Exception:
            pass

        def parse_refs(entries):
            return [
                Reference(
                    title=r['title'],
                    doc_id=r.get('doc-id'),
                    uri=r.get('uri'),
                    date=r.get('date'),
                )
                for r in (entries or [])
            ]

        return ReferencesClause(
            bblock_id=bb['itemIdentifier'],
            name=bb['name'],
            normative=parse_refs(refs_data.get('normative', [])),
            informative=parse_refs(refs_data.get('informative', [])),
            preamble_md=preamble,
        )

    def _load_req_class(self, bb: dict, resolver: Resolver) -> Optional[ReqClass]:
        req_url = self._resource_url(bb, 'requirements')
        if not req_url:
            logger.warning("No requirements resource for %s", bb['itemIdentifier'])
            return None

        try:
            req_data = yaml.safe_load(resolver.fetch(req_url)) or {}
        except Exception as e:
            logger.error("Could not fetch requirements.yaml for %s: %s", bb['itemIdentifier'], e)
            return None

        desc_url = bb['sourceFiles'].rstrip('/') + '/description.md'
        description_md = ''
        try:
            description_md = resolver.fetch(desc_url)
        except Exception:
            pass

        # Derive class IDs from bblock identifier suffix after "requirements."
        class_id = _req_class_id_from_bblock(bb['itemIdentifier'])
        req_class_uri = bb.get('req-class-uri') or resolver.req_uri(class_id)
        conf_class_uri = bb.get('conformance-class-uri') or resolver.conf_uri(class_id)

        # Test resources from compiled register metadata
        test_resources = [
            TestResource(
                url=tr['url'],
                id=tr.get('id'),
                method=tr.get('method'),
                require_fail=tr.get('require-fail', False),
            )
            for tr in bb.get('testResources', [])
            if 'url' in tr
        ]

        # Dependencies
        depends_on = []
        for dep in req_data.get('depends-on', []):
            if 'uri' in dep:
                raw_uri = dep['uri']
                if raw_uri.startswith('bblocks://'):
                    identifier = raw_uri[len('bblocks://'):]
                    dep_bb = resolver.get_bblock(identifier)
                    title = dep.get('title') or (dep_bb['name'] if dep_bb else identifier)
                    resolved_uri = resolver.resolve_bblocks_link(identifier)
                    depends_on.append(Dependency(uri=resolved_uri, title=title))
                else:
                    depends_on.append(Dependency(uri=raw_uri, title=dep.get('title')))
            elif 'bblock' in dep:
                dep_bb = resolver.get_bblock(dep['bblock'])
                dep_name = dep_bb['name'] if dep_bb else dep['bblock']
                dep_uri = resolver.conf_uri(_req_class_id_from_bblock(dep['bblock']))
                depends_on.append(Dependency(uri=dep_uri, title=dep_name))

        # Requirements
        requirements = []
        std_target = req_data.get('standardization-target', bb.get('standardization-target', ''))
        for req_entry in req_data.get('requirements', []):
            req_id = req_entry['id']
            req_uri = req_entry.get('uri') or resolver.req_uri(req_id)

            applies_to = None
            if at := req_entry.get('applies-to'):
                applies_to = AppliesTo(
                    bblock=at.get('bblock', ''),
                    json_path=at.get('json-path'),
                )

            req = Requirement(
                id=req_id,
                uri=req_uri,
                level=req_entry.get('level', 'SHALL'),
                statement=req_entry.get('statement', ''),
                condition=req_entry.get('condition'),
                applies_to=applies_to,
                tested_by=req_entry.get('tested-by', []),
                note=req_entry.get('note'),
                import_examples=int(req_entry.get('import-examples', 0)),
            )
            # Resolve tested-by to actual TestResource objects
            req.test_resources = resolver.resolve_tested_by(req.tested_by, test_resources)
            requirements.append(req)

        self._attach_imported_examples(requirements, resolver)
        examples = self._load_examples(bb, resolver)

        return ReqClass(
            bblock_id=bb['itemIdentifier'],
            name=bb['name'],
            req_class_uri=req_class_uri,
            conf_class_uri=conf_class_uri,
            standardization_target=std_target,
            description_md=description_md,
            requirements=requirements,
            depends_on=depends_on,
            test_resources=test_resources,
            examples=examples,
        )

    # ------------------------------------------------------------------
    # Examples loading
    # ------------------------------------------------------------------

    def _load_examples(self, bb: dict, resolver: Resolver) -> list[Example]:
        json_full_url = bb.get('documentation', {}).get('json-full', {}).get('url')
        if not json_full_url:
            return []
        try:
            import json as _json
            full = _json.loads(resolver.fetch(json_full_url))
        except Exception as e:
            logger.warning("Could not fetch json-full for %s: %s", bb['itemIdentifier'], e)
            return []

        examples = []
        for ex in full.get('examples', []):
            snippets = [
                Snippet(language=s.get('language', 'text'), code=s.get('code', ''))
                for s in ex.get('snippets', [])
                if s.get('code')
            ]
            examples.append(Example(
                title=ex.get('title'),
                content=ex.get('content', ''),
                snippets=snippets,
            ))
        return examples

    def _attach_imported_examples(self, requirements: list, resolver: Resolver) -> None:
        """
        For each requirement with import-examples > 0 and an applies-to bblock,
        fetch up to that many examples from the bblock's json-full and attach
        them directly to the requirement. Each source bblock is fetched at most once.
        """
        import json as _json
        cache: dict[str, list] = {}

        for req in requirements:
            if not req.import_examples or not req.applies_to:
                continue
            identifier = req.applies_to.bblock

            if identifier not in cache:
                bb = resolver.get_bblock(identifier)
                if not bb:
                    logger.warning("import-examples: bblock not found: %s", identifier)
                    cache[identifier] = []
                    continue

                json_full_url = bb.get('documentation', {}).get('json-full', {}).get('url')
                if not json_full_url:
                    logger.debug("import-examples: no json-full for %s", identifier)
                    cache[identifier] = []
                    continue

                try:
                    full = _json.loads(resolver.fetch(json_full_url))
                except Exception as e:
                    logger.warning("import-examples: could not fetch json-full for %s: %s", identifier, e)
                    cache[identifier] = []
                    continue

                cache[identifier] = full.get('examples', [])

            for ex in cache[identifier][:req.import_examples]:
                snippets = [
                    Snippet(language=s.get('language', 'text'), code=s.get('code', ''))
                    for s in ex.get('snippets', [])
                    if s.get('code')
                ]
                req.examples.append(Example(
                    title=ex.get('title'),
                    content=ex.get('content', ''),
                    snippets=snippets,
                ))

    # ------------------------------------------------------------------
    # Annex A generation
    # ------------------------------------------------------------------

    def _build_annex_a(self, req_classes: list[ReqClass], resolver: Resolver) -> AnnexA:
        from .models import ATSEntry
        entries = []
        for rc in req_classes:
            for req in rc.requirements:
                entries.append(ATSEntry(
                    uri=resolver.ats_uri(req.uri),
                    req_uri=req.uri,
                    req_id_slug=req.id_slug,
                    test_purpose=req.statement,
                    test_resources=req.test_resources,
                ))
        return AnnexA(entries=entries)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resource_url(self, bb: dict, role: str) -> Optional[str]:
        for res in bb.get('resources', []):
            if res.get('role') == role:
                return res.get('ref')
        return None

    def _load_imported_registers(self, local_register: dict) -> list[dict]:
        bblocks = []
        for url in local_register.get('imports', []):
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                reg = resp.json()
                bblocks.extend(reg.get('bblocks', []))
                logger.debug("Loaded %d bblocks from %s", len(reg.get('bblocks', [])), url)
            except Exception as e:
                logger.warning("Could not load imported register %s: %s", url, e)
        return bblocks


def _clauses_from_index(local_by_id: dict) -> list:
    """
    Fallback clause ordering when no explicit 'clauses' list is in standards.yaml.
    Sorts BBs by clause-index, wraps with conformance after first entry and annex-a at end.
    """
    sortable = [
        (bb.get('clause-index', 999), bb['itemIdentifier'])
        for bb in local_by_id.values()
        if bb.get('clause-index') is not None
    ]
    sortable.sort()

    entries = [{'bblock': ident} for _, ident in sortable]

    # Insert conformance after position 1 (i.e. after scope), append annex-a at end
    if len(entries) > 1:
        entries.insert(1, {'auto': 'conformance'})
    entries.append({'auto': 'annex-a'})
    return entries


def _load_yaml(path: Path) -> dict:
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _parse_metadata(std: dict) -> StandardMetadata:
    return StandardMetadata(
        title=std['title'],
        doc_number=std.get('doc-number', ''),
        doc_type=std.get('type', 'Standard'),
        status=std.get('status', 'Draft'),
        version=std.get('version', ''),
        pub_date=std.get('pub-date'),
        base_uri=std['base-uri'],
        req_uri_template=std['req-uri-template'],
        conf_uri_template=std['conf-uri-template'],
        editors=std.get('editors', []),
        wg=std.get('wg', ''),
        keywords=std.get('keywords', []),
        abstract=std.get('abstract', ''),
        boilerplate=std.get('boilerplate', {}),
    )


def _req_class_id_from_bblock(bblock_id: str) -> str:
    """
    Extract the requirements class path segment from a bblock identifier.
    e.g. "ogc.api.processes.part1.requirements.core" → "core"
         "ogc.api.processes.part1.requirements.json" → "json"
    Uses everything after "requirements." as the class path.
    """
    marker = '.requirements.'
    idx = bblock_id.find(marker)
    if idx >= 0:
        return bblock_id[idx + len(marker):].replace('.', '/')
    # fallback: last segment
    return bblock_id.split('.')[-1]

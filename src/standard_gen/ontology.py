"""Extract a classes-and-properties summary from an ontology (Turtle)."""
from __future__ import annotations

import re
from typing import Optional

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

_CLASS_TYPES = (OWL.Class, RDFS.Class)
_PROPERTY_TYPES = {
    OWL.ObjectProperty: 'object',
    OWL.DatatypeProperty: 'datatype',
    OWL.AnnotationProperty: 'annotation',
    RDF.Property: 'property',
}
_DEFINITION_PREDICATES = (SKOS.definition, RDFS.comment)


def _text(graph: Graph, subject, predicates) -> str:
    """Best literal for the first predicate that has one: English, then untagged, then any."""
    for predicate in predicates:
        literals = [o for o in graph.objects(subject, predicate) if isinstance(o, Literal)]
        if not literals:
            continue
        for wanted in ('en', None):
            for lit in literals:
                lang = (lit.language or '').split('-')[0] or None
                if lang == wanted:
                    return str(lit)
        return str(literals[0])
    return ''


def _term(graph: Graph, node) -> dict:
    try:
        curie = graph.namespace_manager.curie(node) if isinstance(node, URIRef) else str(node)
    except Exception:
        curie = str(node)
    label = _text(graph, node, (RDFS.label, SKOS.prefLabel)) if isinstance(node, URIRef) else ''
    return {'uri': str(node), 'curie': curie, 'label': label or curie}


def _terms(graph: Graph, subject, predicate) -> list[dict]:
    """Named (non-blank) objects only; restrictions and unions are skipped."""
    nodes = sorted((o for o in graph.objects(subject, predicate) if isinstance(o, URIRef)), key=str)
    return [_term(graph, n) for n in nodes]


def _local_name(term: str) -> str:
    return re.split(r'[#/:]', term.rstrip('/#'))[-1]


def ontology_tables(turtle: str, only: Optional[list[str]] = None) -> Optional[dict]:
    """Return {'classes': [...], 'properties': [...]} for the terms the ontology defines.

    Only URI subjects typed as classes or properties are listed; each entry is
    {term, kind?, definition, superclasses|superproperties, domain, range}.
    `only` restricts the result to terms with these local names (a CURIE or URI is
    reduced to its local name). Returns None if nothing is left.
    """
    graph = Graph()
    graph.parse(data=turtle, format='turtle')

    classes = []
    for subject in {s for t in _CLASS_TYPES for s in graph.subjects(RDF.type, t)}:
        if isinstance(subject, BNode):
            continue
        classes.append({
            'term': _term(graph, subject),
            'definition': _text(graph, subject, _DEFINITION_PREDICATES),
            'parents': _terms(graph, subject, RDFS.subClassOf),
        })

    properties = []
    seen = set()
    for type_, kind in _PROPERTY_TYPES.items():
        for subject in graph.subjects(RDF.type, type_):
            if isinstance(subject, BNode) or subject in seen:
                continue
            seen.add(subject)
            properties.append({
                'term': _term(graph, subject),
                'kind': kind,
                'definition': _text(graph, subject, _DEFINITION_PREDICATES),
                'parents': _terms(graph, subject, RDFS.subPropertyOf),
                'domain': _terms(graph, subject, RDFS.domain),
                'range': _terms(graph, subject, RDFS.range),
            })

    if only:
        wanted = {_local_name(t) for t in only}
        classes = [c for c in classes if _local_name(c['term']['uri']) in wanted]
        properties = [p for p in properties if _local_name(p['term']['uri']) in wanted]
    for entries in (classes, properties):
        entries.sort(key=lambda e: e['term']['curie'].lower())
    if not classes and not properties:
        return None
    return {'classes': classes, 'properties': properties}

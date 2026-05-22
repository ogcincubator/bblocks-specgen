from __future__ import annotations

import logging

from .models import (
    StandardDocument, StandardMetadata, Section,
    ProseClause, TermsClause, ReferencesClause, ReqClass,
    ConformanceClause, AnnexA,
)
from .resolver import Resolver

logger = logging.getLogger(__name__)

_ANNEX_LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'


class Assembler:
    """
    Takes loader output and produces a fully numbered StandardDocument.
    Clause numbers are assigned sequentially; annexes are lettered.
    """

    def __init__(self, metadata: StandardMetadata, clauses: list, resolver: Resolver):
        self._metadata = metadata
        self._clauses = clauses
        self._resolver = resolver

    def assemble(self) -> StandardDocument:
        doc = StandardDocument(metadata=self._metadata)
        clause_num = 0
        annex_num = 0
        in_annexes = False

        for content in self._clauses:
            if isinstance(content, AnnexA):
                in_annexes = True
                letter = _ANNEX_LETTERS[annex_num]
                annex_num += 1
                doc.sections.append(Section(
                    number=letter,
                    title='Abstract Test Suite (Normative)',
                    anchor='annex-a',
                    content=content,
                ))
            elif isinstance(content, ConformanceClause):
                clause_num += 1
                doc.sections.append(Section(
                    number=str(clause_num),
                    title='Conformance',
                    anchor='conformance',
                    content=content,
                ))
            elif isinstance(content, ReqClass):
                clause_num += 1
                doc.sections.append(Section(
                    number=str(clause_num),
                    title=content.name,
                    anchor=f'clause-{clause_num}',
                    content=content,
                ))
            elif isinstance(content, (ProseClause, TermsClause, ReferencesClause)):
                if in_annexes:
                    letter = _ANNEX_LETTERS[annex_num]
                    annex_num += 1
                    doc.sections.append(Section(
                        number=letter,
                        title=content.name,
                        anchor=f'annex-{letter.lower()}',
                        content=content,
                    ))
                else:
                    clause_num += 1
                    anchor = _well_known_anchor(content) or f'clause-{clause_num}'
                    doc.sections.append(Section(
                        number=str(clause_num),
                        title=content.name,
                        anchor=anchor,
                        content=content,
                    ))
            else:
                logger.warning("Unknown clause type: %s", type(content))

        return doc


def _well_known_anchor(content) -> str | None:
    """Use stable anchors for well-known clause types."""
    if isinstance(content, TermsClause):
        return 'terms'
    if isinstance(content, ReferencesClause):
        return 'references'
    return None

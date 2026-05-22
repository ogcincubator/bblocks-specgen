from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class AppliesTo:
    bblock: str
    json_path: Optional[str] = None


@dataclass
class TestResource:
    url: str
    id: Optional[str] = None
    method: Optional[str] = None
    require_fail: bool = False


@dataclass
class Requirement:
    id: str           # e.g. "core/process-list-op"
    uri: str          # full derived URI
    level: str        # SHALL / SHOULD / MAY / SHALL NOT / SHOULD NOT
    statement: str
    condition: Optional[str] = None
    applies_to: Optional[AppliesTo] = None
    tested_by: list[str] = field(default_factory=list)
    note: Optional[str] = None
    test_resources: list[TestResource] = field(default_factory=list)

    @property
    def id_slug(self) -> str:
        return self.id.replace('/', '-').replace(' ', '-')


@dataclass
class ATSEntry:
    uri: str
    req_uri: str
    req_id_slug: str
    test_purpose: str
    test_resources: list[TestResource] = field(default_factory=list)


@dataclass
class Dependency:
    uri: str
    title: Optional[str] = None


@dataclass
class Snippet:
    language: str
    code: str


@dataclass
class Example:
    title: Optional[str]
    content: str
    snippets: list[Snippet] = field(default_factory=list)


@dataclass
class ReqClass:
    bblock_id: str
    name: str
    req_class_uri: str
    conf_class_uri: str
    standardization_target: str
    description_md: str
    requirements: list[Requirement] = field(default_factory=list)
    depends_on: list[Dependency] = field(default_factory=list)
    test_resources: list[TestResource] = field(default_factory=list)
    examples: list[Example] = field(default_factory=list)


@dataclass
class Term:
    term: str
    definition: str
    sources: list[dict] = field(default_factory=list)
    note: Optional[str] = None


@dataclass
class Reference:
    title: str
    doc_id: Optional[str] = None
    uri: Optional[str] = None
    date: Optional[str] = None


@dataclass
class ProseClause:
    bblock_id: str
    name: str
    description_md: str
    normative: bool = True


@dataclass
class TermsClause:
    bblock_id: str
    name: str
    terms: list[Term] = field(default_factory=list)
    abbreviated_terms: dict[str, str] = field(default_factory=dict)
    preamble_md: str = ""


@dataclass
class ReferencesClause:
    bblock_id: str
    name: str
    normative: list[Reference] = field(default_factory=list)
    informative: list[Reference] = field(default_factory=list)
    preamble_md: str = ""


@dataclass
class ConformanceClause:
    req_classes: list[ReqClass] = field(default_factory=list)


@dataclass
class AnnexA:
    entries: list[ATSEntry] = field(default_factory=list)


@dataclass
class SubSection:
    title: str
    anchor: str
    level: int  # normalized heading level (3 = top-level below the section h2)


@dataclass
class Section:
    number: str       # "1", "2", "A", etc.
    title: str
    anchor: str
    content: Any      # one of the clause types above
    subsections: list['SubSection'] = field(default_factory=list)


@dataclass
class StandardMetadata:
    title: str
    doc_number: str
    doc_type: str
    status: str
    version: str
    pub_date: Optional[str]
    base_uri: str
    req_uri_template: str
    conf_uri_template: str
    editors: list[dict]
    wg: str
    keywords: list[str]
    abstract: str
    boilerplate: dict


@dataclass
class StandardDocument:
    metadata: StandardMetadata
    sections: list[Section] = field(default_factory=list)

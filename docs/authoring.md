# Authoring a standard with bblocks-specgen

This guide explains how to structure a repository so that `bblocks-specgen` can render it as
an OGC standards document. For installation and CLI/plugin options, see the
[README](../README.md).

## The idea

A standard is a **set of OGC Blocks** (bblocks) plus one file, `standards.yaml`, at the root
of the repository:

- each **clause** of the document is a bblock (its `description.md` is the clause text);
- a bblock that also carries a `requirements.yaml` is a **requirements class**;
- terms and references are bblocks carrying `terms.yaml` / `references.yaml`;
- `standards.yaml` gives the document metadata and lists which blocks make up the standard,
  in which order.

Nothing in `standards.yaml` is read by `bblocks-postprocess`; specgen reads it directly, and
reads the block sources from the repository (or, for blocks outside it, from their published
URLs).

```
my-standard/
├── bblocks-config.yaml        # identifier-prefix, plugins.build (see README)
├── standards.yaml             # document metadata + clause list
└── _sources/
    ├── clauses/
    │   ├── scope/            { bblock.json, description.md }
    │   ├── terms/            { bblock.json, description.md?, terms.yaml }
    │   └── references/       { bblock.json, description.md?, references.yaml }
    └── requirements/
        └── core/             { bblock.json, description.md, requirements.yaml,
                                examples.yaml, tests.yaml, … }
```

## `standards.yaml`

A list of standards, or a mapping with a top-level `standards` list. One repository can hold
several standards; each is written to `<build-dir>/<id>/index.html`.

```yaml
standards:
  - id: part1                       # required; letters, digits, _ and - only (output folder)
    prefix: my.std.part1            # required; identifier prefix of the blocks in this standard
    title: "My Standard - Part 1: Core"      # required
    base-uri: http://www.opengis.net/spec/my-std-1/1.0    # required

    req-uri-template:  "{base-uri}/{status}req/{id}"      # optional; these are the defaults
    conf-uri-template: "{base-uri}/{status}conf/{id}"
    class-id-prefix: my.std.part1.requirements.           # optional, see "Class ids"

    doc-number: OGC 24-001           # cover page
    type: Standard                   # default: Standard
    status: Draft                    # default: Draft
    version: "1.0.0"
    pub-date: null
    editors:
      - {name: Jane Doe, affiliation: Example Org}
    wg: Example SWG
    keywords: [OGC API, example]
    abstract: |
      What this standard specifies.
    boilerplate:
      copyright-year: 2026
      patent-policy: OGC RF          # adds the patent-policy warning when "OGC RF"
      license: OGC Document Notice   # adds the license agreement text when present

    clauses:                         # optional; document order, see below
      - my.std.part1.clauses.scope
      - {auto: conformance}
      - my.std.part1.clauses.terms
      - my.std.part1.requirements.core
      - {auto: annex-a}
      - my.std.part1.annexes.history
```

### URI templates

`{base-uri}` is the standard's `base-uri`; `{id}` is the requirement or class id;
`{status}` is `draft/` when `status` is `Draft` (case-insensitive) and empty otherwise. With
the defaults, requirements class `core` gets `…/1.0/draft/req/core` and conformance class
`…/1.0/draft/conf/core`.

### `clauses`

Entries are block identifiers (or `{bblock: <identifier>}`), in document order. Only blocks
whose identifier starts with `prefix` are considered; a missing block is a warning.

- `{auto: conformance}` — a conformance clause with a table of all requirements classes in
  the standard. It is numbered like any other clause, so put it where you want it.
- `{auto: annex-a}` — the Abstract Test Suite annex, generated from the requirements.
- **Annexes:** every prose, terms or references clause listed *after* `{auto: annex-a}` is
  numbered as an annex (B, C, …) instead of a numbered clause.

If `clauses` is omitted, blocks with a `clause-index` number in `bblock.json` are used, sorted
by it, with the conformance clause after the first block and the ATS annex last. Prefer an
explicit list: it keeps document structure in one place.

## How a block becomes part of the document

Which role each block gets is decided from its contents:

| The block… | Role |
|---|---|
| has `itemClass: terms` | terms and definitions clause (`terms.yaml`) |
| has `itemClass: references` | references clause (`references.yaml`) |
| has a `requirements.yaml` | requirements class — **whatever its `itemClass`** (so a `model` block can carry requirements) |
| none of the above | prose clause (`description.md`) |

After a run, `<build-dir>/<id>/report.json` lists every block that went in, the role it got
and why. Check it when something is not rendered the way you expect. A block with
`itemClass: clause` that also has a `requirements.yaml`, or `itemClass: requirements-class`
without one, produces a warning.

The block's `name` (from `bblock.json`) is the clause title. `normative: false` in
`bblock.json` marks a prose clause as informative.

## Prose clauses: `description.md`

Plain Markdown. Notes:

- **Headings** are shifted so that the shallowest heading in the file becomes `###` (the
  clause title itself is the `##`), and appear in the table of contents. Write the file as
  you would normally, starting with `#` or `##`.
- **Links to other blocks:** `[text](bblocks://<identifier>)` links to the block's clause if it
  is in this document, or to its page in the viewer if it comes from an imported register.
- **Figures:** see below.
- The Markdown dialect is CommonMark plus tables.

### Figures

A captioned image alone in its paragraph is a numbered figure:

```markdown
![Core classes of the model](assets/core.svg)
```

renders as `Figure 3 — Core classes of the model` below the image ("Figure A.1" in annexes).
Captions may use inline Markdown. An image without a caption, or inside running text, is a
plain image.

To refer to a figure, link to the image path; the link text defaults to "Figure N":

```markdown
The classes are shown in [](assets/core.svg), and [this diagram](assets/core.svg) too.
```

Details:

- Paths are relative to the block's own source directory. Local images are copied to
  `<id>/assets/<block>/`; a missing image aborts the run. Remote URLs work too (numbered and
  referenceable, not copied). Absolute URLs under the register's `baseURL` are mapped to the
  local file.
- **An image is shown once**, where first included. Repeats (same or other block) are
  omitted; references point to the first.
- To give a figure a stable anchor (or to say which of two images wins), add an id:
  `![Caption](assets/core.svg){#fig-core}` and refer to it with `[](#fig-core)`.
- References may point forward. A link to an image that is not a figure produces a warning.
- Prefer SVG over PNG when you have both.

## Terms: `terms.yaml`

```yaml
terms:
  - term: coordinate operation
    definition: >
      Process for changing coordinates in a source CRS to coordinates in a target CRS.
    sources:                       # optional
      - title: ISO 19111:2019
        uri: https://www.iso.org/standard/74039.html
    note: Optional note.           # optional; shown as an editor's note

abbreviated-terms:                 # optional; abbreviation: expansion
  CRS: coordinate reference system
```

Terms are sorted alphabetically. `description.md` in the same block, if present, is shown as
the introduction of the clause.

## References: `references.yaml`

```yaml
normative:
  - title: "OpenAPI Specification 3.0"      # required
    doc-id: OAS 3.0                          # sort key and citation label
    uri: http://spec.openapis.org/oas/v3.0.4
    date: "2020"
informative:
  - title: "…"
    doc-id: …
```

`description.md`, if present, is shown before the lists.

## Requirements classes: `requirements.yaml`

```yaml
class-id: core                  # optional, see "Class ids"
standardization-target: Web API # optional

depends-on:                     # optional: other conformance classes this one requires
  - bblock: my.std.part1.requirements.common     # a class in this standard
  - uri: bblocks://some.other.block               # resolved to the block's name and link
  - uri: http://example.org/spec/conf/x           # any URI
    title: Some other class

requirements:
  - id: core/landing-page       # required; the URI is derived as <req-uri-template> with this id
    level: SHALL                # default SHALL; also SHOULD, MAY, SHALL NOT, SHOULD NOT
    statement: >                # Markdown
      The server SHALL support the HTTP GET operation at the path `/`.
    condition: …                # optional; shown with the requirement
    note: …                     # optional
    applies-to:                 # optional
      bblock: my.std.api.paths.LandingPage
      json-path: $.properties.links   # optional, default $; selects the schema node
    tested-by:                  # optional; ids or file names from the block's tests.yaml
      - landing-page-success
    import-examples: 2          # optional: pull up to N examples from the applies-to block
```

Notes:

- **Requirement ids** conventionally start with the class id (`core/landing-page`): the id is
  substituted verbatim into the URI template, so `core/landing-page` gives `…/req/core/landing-page`.
- **`applies-to`** links the requirement to a block, and, when that block has a JSON Schema,
  adds a property table (name, type, required, description) for the selected `json-path`.
- **`tested-by`**: matched, in order, against the `id` and then the file name (with or
  without extension) of the block's test resources (`tests.yaml`, as published in
  `register.json`). If omitted, all of the block's test resources are listed. Each
  requirement also yields an entry in the Abstract Test Suite annex.
- **Examples:** the block's own `examples.yaml` examples are listed after the requirements
  (they come from the block's `json-full` documentation). `import-examples` appends examples
  of *another* block under a requirement. Images in an example are resolved against the block
  the example comes from.
- **`description.md`** is the class introduction. To put text *after* the requirements
  instead, insert the line `<!-- requirements -->`: everything before it is shown above the
  requirements, everything after it below.
- `req-class-uri` and `conformance-class-uri` in `bblock.json` override the derived class URIs.

### Class ids

The class id is the segment in `…/req/<id>` and `…/conf/<id>`. It is, in order of
precedence:

1. `class-id` in the block's `requirements.yaml`;
2. the block identifier with `class-id-prefix` removed, if the standard sets one;
3. the block identifier with the standard's `prefix` removed;
4. (blocks outside the standard) the last segment of the identifier.

Dots become `/`. Use `class-id-prefix` to keep requirements grouped in the register without the
group leaking into URIs: with `prefix: my.std.part1` and
`class-id-prefix: my.std.part1.requirements.`, the block `my.std.part1.requirements.core` gets
the class id `core`. `class-id-prefix` must start with `prefix`.

## Model blocks and ontology blocks as requirements classes

A requirements class is not tied to `itemClass: requirements-class`. A block of any
`itemClass` (for example `model`) that has a `requirements.yaml` becomes a requirements class
and keeps all of its normal bblock content (schema, ontology, examples, tests). Set
`class-id` explicitly when its identifier does not carry a meaningful class path.

### Ontology tables

A requirement with `applies-to: {bblock: <id>}` gets a property table built from the block's
JSON Schema. If the block has no schema properties but does have an `ontology` in the
register (an `ontology.ttl`), the requirement gets a "classes" table (subclass-of,
definition) and a "properties" table (domain, range, definition) instead, listing the terms
the ontology itself defines (named classes and object/datatype/annotation properties).
Labels and definitions prefer English. By default the tables list the whole ontology; add
`terms` to `applies-to` to list only some of it (local names, or CURIEs whose prefix is
ignored):

```yaml
applies-to:
  bblock: my.std.model
  terms: [CoordinateOperation, geosrs:SingleOperation]
```

## A minimal complete example

`bblocks-config.yaml` (excerpt):

```yaml
identifier-prefix: my.std.
plugins:
  build:
    - classes: [standard_gen.plugin.SpecgenBuildPlugin]
      pip: [bblocks-specgen @ git+https://github.com/ogcincubator/bblocks-specgen]
```

`standards.yaml`:

```yaml
standards:
  - id: core
    prefix: my.std.
    title: My Standard
    base-uri: http://www.opengis.net/spec/my-std/1.0
    doc-number: OGC 24-001
    clauses:
      - my.std.scope
      - {auto: conformance}
      - my.std.model
      - {auto: annex-a}
```

`_sources/scope/bblock.json` (`name`, `status`, `dateTimeAddition`, `itemClass` and `version` are
the only fields the bblocks schema requires; see the bblocks-postprocess docs for the rest):

```json
{ "name": "Scope", "itemClass": "clause", "status": "under-development",
  "dateTimeAddition": "2026-01-01T00:00:00Z", "version": "1.0" }
```

`_sources/scope/description.md`:

```markdown
This standard defines …
```

`_sources/model/bblock.json` — a model block that is also a requirements class:

```json
{ "name": "Model", "itemClass": "model", "status": "under-development",
  "dateTimeAddition": "2026-01-01T00:00:00Z", "version": "1.0" }
```

`_sources/model/requirements.yaml`:

```yaml
class-id: model
requirements:
  - id: model/classes
    statement: An implementation SHALL use the classes defined in [](assets/classes.svg).
```

`_sources/model/description.md`:

```markdown
## Classes

![Classes of the model](assets/classes.svg)
```

Run `bblocks-postprocess` (which runs the plugin), then open
`standards/core/index.html`; `standards/core/report.json` shows how each block was used.

## Troubleshooting

- **A block shows up as prose but should be a requirements class** — check `report.json`:
  specgen did not find `requirements.yaml` next to the block's `bblock.json`.
- **URIs look like `/req/requirements/core`** — the class id defaults to the identifier minus
  `prefix`; set `class-id-prefix` or `class-id`.
- **The run aborts on an image** — the image path is relative to the *block's* source
  directory, not to the repository root or to `standards.yaml`.
- **Any failure aborts the whole run**; the top-level index is only written after every
  standard has rendered successfully.

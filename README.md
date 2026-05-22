# bblocks-specgen

A Python CLI tool that generates OGC standards documents (HTML) from a compiled
[Building Blocks](https://github.com/opengeospatial/bblocks) register.

Instead of authoring standards in AsciiDoc/Metanorma, the source lives as Building Block
definitions (YAML, Markdown, JSON Schema). `bblocks-postprocess` compiles these into a
`register.json`, and `bblocks-specgen` renders that into a structured HTML document
following OGC conventions: front matter, scope, terms & definitions, normative clauses
with requirements, conformance class table, and an abstract test suite annex.

## Implemented

- [x] Document cover page — title, editors, document number, status, version, publication date
- [x] Boilerplate — copyright notice, patent policy, license statement
- [x] Prose clauses — rendered from `description.md` per Building Block
- [x] Terms & definitions clause — loaded from `terms.yaml`, sorted alphabetically
- [x] References clause — normative and informative, loaded from `references.yaml`
- [x] Requirements classes — loaded from `requirements.yaml`; rendered as numbered requirement boxes with level (SHALL/SHOULD/MAY), statement, condition, and tested-by links
- [x] Conformance class summary table — auto-generated from all requirements classes
- [x] Abstract Test Suite (Annex A) — auto-generated ATS entries per requirement
- [x] Examples — loaded from `documentation.json-full.url`; rendered with title, prose, and code snippets per requirements class
- [x] Requirements property table — fetches the bblock JSON Schema and renders a Property / Type+Format / Required / Description table inside each requirement box
- [x] Subheading support — headings in `description.md` are normalized to start at h3 and appear in the section table of contents
- [x] Clause ordering fallback — uses `clause-index` metadata when no explicit `clauses` list is given in `standards.yaml`
- [x] Multi-register support — `--extra-register` allows importing additional compiled registers for cross-register bblock resolution
- [x] `import-examples: N` on a requirement — pulls up to N examples from the external bblock's `json-full`, appended after any locally defined examples; each source bblock is fetched at most once per requirements class
- [x] `bblocks://` URIs in `depends-on` — resolved to bblock name and viewer URL automatically from the imported register, no hand-typed title needed

## Pending

- [ ] Requirements property table — resolve `$ref` chains, handle `allOf`/`oneOf`, show enum values and constraints
- [ ] `requirements.json` — machine-readable requirements manifest output
- [ ] Subheading hierarchical numbering (e.g. 7.1, 7.1.1) in the table of contents
- [ ] Unit tests (`test_resolver.py`, `test_assembler.py`)
- [ ] PDF output via WeasyPrint

## Installation

```bash
git clone https://github.com/opengeospatial/bblocks-specgen.git
cd bblocks-specgen
python -m venv venv
venv/bin/pip install -e .
```

## Usage

First, run `bblocks-postprocess` in your Building Blocks repository to produce a compiled
`register.json` (typically at `build-local/register.json`). The repository must also have a
`standards.yaml` at the root so that standards metadata is embedded into `register.json`.

```bash
venv/bin/bblocks-specgen --register path/to/build-local/register.json
```

The generated document is written to `build/standard/index.html` by default.

### Options

| Option | Description |
|---|---|
| `--register REGISTER_JSON` | Path to compiled `register.json` **(required)** |
| `--prefix PREFIX` | BB identifier prefix to select a standard (required when the register contains multiple standards) |
| `--build-dir DIR` | Output directory (default: `build/standard`) |
| `--extra-register REGISTER_JSON` | Additional compiled `register.json` files to import for cross-register bblock resolution (repeatable) |
| `-v`, `--verbose` | Enable debug logging |

### Example

```bash
# From the root of an ogcapi-processes-standard-as-bblocks checkout:
bblocks-postprocess   # produces build-local/register.json

bblocks-specgen \
  --register build-local/register.json \
  --build-dir build/standard

open build/standard/index.html
```

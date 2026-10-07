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
- [x] Multiple standards per repo — each `standards.yaml` entry (required `id`) is generated to `<build-dir>/<id>/`, with an index page listing them
- [x] `import-examples: N` on a requirement — pulls up to N examples from the external bblock's `json-full`, appended after any locally defined examples; each source bblock is fetched at most once per requirements class
- [x] `bblocks://` URIs in `depends-on` — resolved to bblock name and viewer URL automatically from the imported register, no hand-typed title needed

## Pending

- [ ] Requirements property table — resolve `$ref` chains, handle `allOf`/`oneOf`, show enum values and constraints
- [ ] `requirements.json` — machine-readable requirements manifest output
- [ ] Subheading hierarchical numbering (e.g. 7.1, 7.1.1) in the table of contents
- [ ] Unit tests (`test_resolver.py`, `test_assembler.py`)
- [ ] PDF output via WeasyPrint

See [docs/authoring.md](docs/authoring.md) for the full authoring guide: `standards.yaml`,
`requirements.yaml`, `terms.yaml`, `references.yaml`, figures, and a worked example.

## Installation

```bash
git clone https://github.com/ogcincubator/bblocks-specgen.git
cd bblocks-specgen
python -m venv venv
venv/bin/pip install -e .
```

## Usage

First, run `bblocks-postprocess` in your Building Blocks repository to produce a compiled
`register.json` (typically at `build-local/register.json`). The repository must also have a
`standards.yaml` at the root defining the standards to generate (read directly by this tool,
not by `bblocks-postprocess`).

```bash
venv/bin/bblocks-specgen --register path/to/build-local/register.json
```

### `standards.yaml`

A list of standards (or a mapping with a top-level `standards` list). Each entry requires:

- `id` — unique; letters, digits, `_` and `-` only. Used as the output folder name.
- `prefix` — the BB identifier prefix whose blocks make up this standard.
- `title`

plus the metadata fields already supported (`base-uri`, `req-uri-template`, `conf-uri-template`,
`clauses`, `doc-number`, etc.).

### How a block becomes a clause

Which blocks form a standard is decided by `prefix` and the `clauses` list. How each one is
rendered is decided from its content, not from a `standards.yaml` entry:

1. `itemClass: terms` / `references` → terms / references clause.
2. Otherwise, a block that has a `requirements.yaml` next to its `description.md` is a
   **requirements class**, whatever its `itemClass` (e.g. a `model` block).
3. Anything else is a prose clause (`description.md`).

`requirements.yaml` may start with `class-id: <id>`, the segment used in the `/req/<id>` and
`/conf/<id>` URIs. If omitted, it defaults to the block identifier with the standard's `prefix`
removed (dots become `/`). To keep requirements grouped under a namespace in the register
(e.g. `<prefix>.requirements.core`) without that group leaking into the class URIs, set
`class-id-prefix: <prefix>.requirements.` on the standard in `standards.yaml` (a full identifier prefix, which must start with `prefix`): `<prefix>.requirements.core`
then gets the class id `core`. An explicit `class-id` always wins.

### Figures

An image alone in its paragraph with a caption (`![Caption text](assets/diagram.png)`) is rendered
as a numbered figure, with the caption below it: "Figure 3 — Caption text" ("Figure A.1" in annexes).
Captions may contain inline Markdown. An image without a caption, or one inside running text, is
rendered as a plain `<img>`.

Image paths are resolved relative to the block's source directory. Local images are copied to
`<id>/assets/<block>/`; a missing image aborts the run. Remote URLs are left as they are.

To refer to a figure from the text, link to the same image path; the link is replaced by a link to
the figure, whose text is "Figure N" if the link text is empty (link text, if given, is kept):

```markdown
The classes are shown in [](assets/core.png).
```

An image is shown only once, where it is first included: if the same image is embedded again
(in the same block or another), the repeat is omitted and references point to the first. This
also holds for remote images, which are numbered and referenced the same way but not copied.
Images in examples (including those pulled in with `import-examples`) are resolved against the
block the example comes from, and absolute URLs under the register's `baseURL` are mapped back to
the local file. The `assets/` folder is rebuilt on every run, so images that are no longer used
disappear.

Because this is an ordinary link, it also works when the Markdown is viewed outside specgen.
To give a figure a stable anchor, or to disambiguate when the same image is used twice, add an
explicit id, `![Caption](assets/core.png){#fig-core}`, and link to it with `[](#fig-core)`.
References can point forward to figures that appear later in the document. A link to an image
that is not a figure produces a warning.

### Output

Each standard is written to `<build-dir>/<id>/index.html` (even when there is only one), and
`<build-dir>/index.html` lists the available standards. Each folder also gets a `report.json`
listing every block that went into the document, the role it was given and why. `<build-dir>` defaults to `standards`.
Any failure aborts the run without writing the top-level index. Folders of standards that no
longer exist are removed, but only if this tool created them (they contain a `.specgen` marker).

### Options

| Option | Description |
|---|---|
| `--register REGISTER_JSON` | Path to compiled `register.json` **(required)** |
| `--standards-file STANDARDS_YAML` | Standards definitions (default: `standards.yaml` in the repo root) |
| `--root-dir DIR` | Repo root (default: the parent of the `register.json` directory) |
| `--only ID` | Generate only this standard id (repeatable; default: all) |
| `--build-dir DIR` | Output directory (default: `standards`) |
| `--extra-register REGISTER_JSON` | Additional compiled `register.json` files to import for cross-register bblock resolution (repeatable) |
| `-v`, `--verbose` | Enable debug logging |

### Example

```bash
# From the root of an ogcapi-processes-standard-as-bblocks checkout:
bblocks-postprocess   # produces build-local/register.json

bblocks-specgen --register build-local/register.json

open standards/index.html
```

## As a bblocks-postprocess build plugin

`standard_gen.plugin.SpecgenBuildPlugin` runs the same generation as a
[build (lifecycle-hook) plugin](https://github.com/opengeospatial/bblocks-postprocess-action/blob/develop/docs/implemented/build-lifecycle-hooks.md),
firing at `after_run` — once, on a successful `bblocks-postprocess` run, right
after the final `register.json` (post-uplift) is available — instead of being
invoked by hand afterward. `Assembler`/`Renderer` are unchanged; the
CLI and the plugin both funnel through the same `standard_gen.generate.generate()`
entry point, so behavior is identical either way.

Requires a `v1.*.*`-or-later `bblocks-postprocess` release with build-plugin
support (see that repo's CLAUDE.md "Releasing" section — the mechanism only
reaches `full@v1`/`postprocess@v1` consumers once a release tag has shipped).

Declare it in the register repo's `bblocks-config.yaml`. All `config` keys are optional
(the values shown are the defaults); `config` requires `bblocks-postprocess` v1.1.8 or later:

```yaml
plugins:
  build:
    - classes: [standard_gen.plugin.SpecgenBuildPlugin]
      pip: [bblocks-specgen @ git+https://github.com/ogcincubator/bblocks-specgen]
      config:
        standards-file: standards.yaml   # relative to the repo root
        build-dir: standards             # relative to the repo root, or absolute
        only: []                         # standard ids to generate (default: all)
        extra-registers: []              # register.json URLs or paths to import
```

Unknown config keys or wrong types abort the run. The standards definitions are read from
`standards-file` (see [`standards.yaml`](#standardsyaml) above), not from `register.json`.

# Instructions for AI agents

For an AI agent changing this repository: what is here, the invariants it holds,
and the commands that verify a change. Degardis's own behavior, schemas, and CLI
surface are documented in [README.md](README.md) and [docs/](docs/); what the
code does is in the code. Neither is restated here.

Don't edit this file without an explicit permission from the repository owner.

Don't bump version, or the `CURRENT_FORMAT_VERSION` constant, without an explicit permission from the repository owner.

## What this repository is

Degardis is a Python command-line compiler: it reads a skill source written as
Markdown files with YAML frontmatter, resolves what each class of work needs,
and renders an installable bundle. The repository holds the compiler, not a
collection of skills.

- [degardis/](degardis/) — the package published to PyPI. All product code.
- [docs/](docs/) — documentation for people. See [audiences](#who-each-text-is-written-for).
- [tools/](tools/) — repository scripts, not product code.
- [examples/structured-summary/](examples/structured-summary/) — the one public
  example skill, and the only one `examples/` may hold. It validates clean, uses
  every construct kind the format defines, and builds every documented feature.
- [tests/fixtures/skills/demo/](tests/fixtures/skills/demo/) — synthetic sources
  driving the compiler's checks: test data, not examples, malformed on purpose
  where a check needs it. `alpha` carries every construct kind and every overlap
  placement has to tell apart; `beta` is the second skill discovery and
  multi-skill builds need.
- `.artifacts/` — untracked scratch directory for build output.

## Setup and verification

Python 3.10 or newer; CI runs 3.10 and 3.14. Install with
`python -m pip install -e ".[lint]"`.

Run the following checks that are relevant to your change, don't waste time and
token on the ones that are not.

```console
python -m ruff check .
python -m unittest discover -s tests -v
python -m tools.generate_manual --check
python -m degardis validate examples/structured-summary
```

Build into a throwaway directory such as `.artifacts`, never a real agent skill
directory: a rebuild replaces that skill's folder and ZIP there.

The conformance cases in [tests/test_conformance.py](tests/test_conformance.py)
are where the format's guarantees are stated, one case per test, each with the
failure it prevents in its docstring. Read them before changing what a bundle
looks like; a guarantee that is not one of those cases is not yet a guarantee.

## Invariants

Preserve these, or change one deliberately and say why. Each states a property to
hold, not the mechanism currently holding it — read the code and its tests for
that, and do not copy either back into this file.

- **The agent reads the root, then one page.** `SKILL.md` routes a request
  straight to a task page, and that page carries the task's whole knowledge
  closure. No generated layer may sit between them: an index every run passes
  through answers no question the run had, and the compiler already knows which
  knowledge belongs to which task.
- **The facet index is the only lookup the bundle keeps.** It survives because
  which facets apply is decided by the situation, which only the running agent
  sees. A task never selects a facet, and removing the complete generated
  `facets/` tree must leave `SKILL.md` and every task page byte-for-byte
  unchanged, so a facet missed, or matched wrongly, cannot change validity or
  failure.
- **Type is directory. Identity is file stem. Metadata is frontmatter. Content
  is Markdown body.** No source file declares an id: a second spelling of a name
  the filename already carries is a name that can disagree with itself. Renaming
  a file is what renames a construct.
- **The compiler owns no words but `wording.py`'s.** Every principle, knowledge
  unit, facet, and task body is the author's, read from the skill being
  compiled. A principle reference resolves to that skill's own file and nowhere
  else — not the package, not another installed skill, not a cache, not the
  network — so one source states one thing whichever version compiled it.
- **Ordinary compilation moves authored material and never edits it.** Heading
  depth is re-levelled so a document becomes a section, relative links are
  re-addressed so they still resolve from where the text landed, and a
  hard-wrapped paragraph is folded back into one line so the width of the
  author's editor stops travelling with the text. Nothing is paraphrased,
  merged, summarized, invented, reordered, or silently dropped. A page over
  budget is reported with what weighs most on it; what to cut is the author's.
- **Selection is the author's; placement is the compiler's.** A principle every
  task names is stated once in the root, one some tasks name is stated on each of
  those pages, and both readings are complete. The same split governs anything
  later placed this way.
- **Every declared relationship is consumed by the compiler.** A relationship
  that changes no generated page is a claim the source makes and the bundle
  cannot show, and does not belong in the format.
- **A dependency is declared, never inferred.** Nothing follows from a word
  appearing in prose, so ordinary editing cannot move material between pages.
- **A budget is what one load costs its reader.** The root is charged against
  every run whether or not it is read; a task page is opened once, deliberately,
  and is the whole of what that work needs. Neither limit is a round number
  chosen for looking like a limit; change one only against what a reader actually
  pays.
- **A reference is bare where its field names the namespace, and qualified where
  the field accepts more than one kind.** The rule is stated to the author rather
  than learned per field.
- **Every check code is a literal with an explanation, an explanation has a
  check, and a case makes it fire.** A code assembled at runtime can no longer be
  checked against the table; an entry no module can report describes a check the
  compiler never runs; a code no test exercises is a check nobody has run. The
  third is satisfied by a case that reports the code, never by listing it.
- **The explain table is data, and its filenames are its vocabulary.**
  [degardis/explain_codes/](degardis/explain_codes/) holds one file per code,
  named for the code it explains, so the directory listing is the set of known
  codes and no catalog can disagree with it; a sentence a family of codes shares
  is stated once in [degardis/explain_codes/wording/](degardis/explain_codes/wording/)
  and named by each of them. No explanation is written in Python: the words
  belong to whoever repairs a source.
- **Code spelling.** `namespace.hyphenated-name`, except where it names a key of
  the source, which it spells exactly as the key does —
  `interface.short_description-length`, not `short-description-length`. The rule
  is stated to the reader where an unrecognized code lists the known ones, so an
  author who knows the key can build the code rather than look it up.
- **A missing or invalid field reports a check naming the key.** The three
  ways a field goes wrong are three checks, because they are three repairs:
  `<namespace>.missing-<key>` for a required field that is not there,
  `<namespace>.unknown-field` for one the schema does not declare, and
  `<namespace>.invalid-<key>` for a value that is there and cannot be read. That
  holds for every construct, the manifest, `content`, and `interface`, so an
  author who knows the key can build the code rather than read a message. The
  exception is a field nested in a list item, such as a task's resource: it keeps
  the enclosing item's check, because there the item rather than the file is the
  unit an author repairs.
- **Checks collect; they do not stop at the first problem.** Every finding is
  gathered, and `explain` names all unknown codes together rather than refusing
  at the first. One record is kept per distinct finding, so a message naming
  only the file it was found in makes two findings identical and drops one: name
  what was refused — the construct, the field, the reference, the page — not
  just where.
- **The manual has one source, and all of it is printable.**
  [degardis/manual_topics/](degardis/manual_topics/) holds the catalog and the
  topic prose, so every part of the manual is reachable by a `degardis manual`
  name and none of it is written in Python; prose that no name reaches is not a
  topic and does not belong there, and neither does a topic named for something
  the compiler does not do. `docs/manual.md` is generated from those topics and
  [tools/manual_template.md](tools/manual_template.md), which carries the
  document's own heading, lead, and notice and nothing a topic could carry
  instead. The generated copy is never edited, and CI fails a stale one.
- **One set of findings, three renderings.** `validate`, the `inspect` line
  report, and `build` run the same checks over the same compilation and set the
  same exit status; `--only` and `--all` choose what is printed, never what is
  checked. Anything that checks a source belongs in `validate.py`'s own
  compilation, not on one output path; `inspection.py` shapes that compilation
  into the one result dictionary all three read, and decides nothing about
  validity.
- **The report is the only machine interface.** No plan, closure, source-map, or
  coverage file is emitted beside the document — which is something the `inspect`
  help has to say, since an agent has that help and nothing else.
- **Builds are atomic per skill.** A failure leaves existing artifacts as they
  were, a completed sibling still commits, and a promoted warning stops the
  build before anything is written.
- **A rebuild is byte-identical, on every host.** Nothing in generated text or in
  the order of its sections may depend on the machine, the filesystem, or
  discovery order.
- **`-h` works on either side of the command name:** `degardis -h build` prints
  what `degardis build -h` prints.
- **One version source.** `degardis/__init__.py:__version__`; the publish
  workflow refuses a release whose tag is not `v<that version>`. An unreleased
  branch does not have a version tag.
- **Report shape is contract.** A report row's columns and their order, and a
  summary line, are as much an interface as the CLI options are, and the suite
  asserts them literally. Help prose is not: no test reads it, because a
  rewording would fail every such test and a behavior change would fail none.
- **The root's section order is fixed, and it carries nothing it can point at.**
  No knowledge, no facet catalog, no resource index; a section with nothing to
  carry contributes no heading at all. The root is loaded every time the skill is
  selected, so it is held to a smaller attention budget than a task page.
- **The compiler establishes artifact integrity, never behavioral utility.**
  Nothing here scores whether a skill helps an agent, and there is no command
  that claims to: a compiler grading its own output would grade it against
  criteria it also wrote. Say so where a reader might infer otherwise, and do not
  add a manual topic, a metric, or a command that implies the opposite.

## Who each text is written for

- **`README.md` and `docs/`** are for people: a reader deciding whether to use
  Degardis, authoring a skill, or looking a command up. Keep them prose, and do
  not mirror agent-facing output fields into them beyond what that reader needs.
- **The manual is one text for two readers**, `degardis manual TOPIC` for an
  agent that has only the CLI and `docs/manual.md` for a person in a browser, so
  a topic is written in the author's vocabulary. It explains the source format
  and observable artifact behavior, never how the compiler implements selection
  or generation: no internal locations, structures, or processing steps. An
  artifact-layout topic may name a path that an artifact reader must open, but
  another topic must not expose that path as an implementation mechanism. A
  manual topic states a diagnostic rule and its repair without naming its check
  code; check codes and their explanations belong only in `explain_codes/`.
- **The installed package ships no `docs/`.** A manual topic and a command's help
  are the only text it carries, so neither may send a reader outside the CLI. The
  help is a short paragraph naming the topic that holds the detail; an epilog
  grown past that says its topic is incomplete.
- **`degardis inspect` — its output and its `--help` — is for AI agents.** The
  output is line-oriented and shaped for token cost rather than for a person, and
  the help is what tells an agent which option produces which rows.
- **`validate`, `list`, and `build` reports** are for a person at a
  terminal; `validate` is the CI gate a person reads. An agent wanting the same
  facts as data uses `inspect`.
- **The `explain` table** is for whoever repairs a source, agent or author: what
  triggers the check, why it matters, and a resolution if applicable. It is
  hand-written because a check knows its condition, not why an author should
  care.
- **The generated `SKILL.md` and task pages** are for the agent executing the
  skill: the author's own material, placed where that work needs it.
- **Diagnostic messages** name what is wrong and where, and carry the code, so a
  reader can look the check up instead of guessing.

## Conventions

- Start every module with `from __future__ import annotations`, and annotate
  public signatures.
- Keep to the 3.10 language floor; nothing newer may be required to import the
  package.
- Write docstrings that explain why the code is shaped this way — the failure it
  prevents, the alternative rejected, the invariant it holds — and omit them
  where the name already says it. `analysis.py` and `markdown.py` are the house
  style.
- Nothing enforces formatting; match the surrounding file's wrapping and layout.
- Ask before adding a dependency, including a test-only one.
- A failure carries its check code however it reaches the caller — raised,
  collected, or printed — so `degardis explain` follows from any of them. A
  raise a check explains passes the code; a one-off failure no check names
  passes nothing.

## When you change X, also change Y

| Change | Also update |
| --- | --- |
| A check | The literal code, its `explain_codes/<code>.yaml` file, a test case that makes it fire, and the manual topic stating the rule without naming its code, where it changes what `validate` accepts |
| A construct's schema — a field, or a kind | That construct's field set and reader in `sources.py`, `analysis.py` where placement reads it, `render.py` where it appears, and that construct's topic in `manual_topics/` |
| A required field, on any schema | The `missing` code written at the call site that reads it, its `explain_codes/<code>.yaml` file, and that schema's required rows in its manual topic |
| A content key | The key tuples in `content.py` and that key's `invalid` code, the reader `sources.py` dispatches to, `manual_topics/manifest.md`, and the example and fixtures that select it |
| A manifest or `interface` key | `registry.py`'s field set and its checks, `content.py` where it selects files, `package.py` where it reaches the interface metadata, and `manual_topics/manifest.md` or `manual_topics/interface.md` |
| What reaches a page, or where it lands | `analysis.py`, the checks in `validate.py` that resolve every reference, `render.py`'s page shape, and `manual_topics/relationships.md` or `manual_topics/principles.md` |
| A CLI option or command | The command's help and `Examples:` block in `cli.py`, `docs/cli.md`, and the command list in `README.md` |
| An inspect dimension or one of its rows | `output.py`, `INSPECT_DIMENSIONS` and the row builders in `inspection.py`, `manual_topics/inspection.md` where the row shapes are stated, and the `inspect` section of `docs/cli.md` |
| The wording of a generated Markdown section | `wording.py` only; `render.py` holds the structure, not the words |
| A generated page's path | `bundlepaths.py` only; every other module asks it |
| A manual topic | Its file, `manual_topics/topics.yaml` where the name, summary, or cross-references change, every `cli.py` help text naming that topic, and `docs/manual.md` regenerated |
| The generated bundle's layout | `package.py`, `bundlepaths.py`, the conformance cases that read it, and `docs/artifact-format.md` |
| The source format | `CURRENT_FORMAT_VERSION` and every manual topic the change reaches |
| The version | `degardis/__init__.py` only, tagged `v<version>` |

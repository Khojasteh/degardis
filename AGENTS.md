# AGENTS.md

For an AI agent changing this repository: what is here, the invariants it holds,
and the commands that verify a change. Degardis's own behavior, schemas, and CLI
surface are documented in [README.md](README.md) and [docs/](docs/); what the
code does is in the code. Neither is restated here.

## What this repository is

Degardis is a Python command-line compiler: it reads a skill source written as
YAML, checks its control flow and data flow, lowers every binding construct into
the workflow location where it is enforced, and renders an installable bundle.
The repository holds the compiler, not a collection of skills.

- [degardis/](degardis/) — the package published to PyPI. All product code.
- [docs/](docs/) — documentation for people. See [audiences](#who-each-text-is-written-for).
- [examples/structured-summary/](examples/structured-summary/) — the one public
  example skill, and the only one `examples/` may hold. It validates clean, uses
  every construct kind the format defines, and builds every documented feature.
- [tests/fixtures/skills/demo/](tests/fixtures/skills/demo/) — synthetic sources
  driving the compiler's checks: test data, not examples, malformed on purpose
  where a check needs it. `alpha` carries every construct, every step form,
  every binding phase, and all three protocol scopes at once, because most of
  what a check has to see is a property of one source rather than of one check.
- `.artifacts/` — untracked scratch directory for build output.

## Setup and verification

Python 3.10 or newer; CI runs 3.10 and 3.14. Runtime dependencies are Pillow,
PyYAML, and resvg_py, pinned in [pyproject.toml](pyproject.toml). Install with
`python -m pip install -e ".[lint]"`.

CI lints once on 3.14, then runs the suite on both versions and validates and
builds the example. Run the same before you finish; each step must end in `All
checks passed!`, `OK`, `[PASS]`, and a `Summary:` line with no failure or
warning:

```console
python -m ruff check .
python -m unittest discover -s tests -v
python -m degardis validate examples/structured-summary
python -m degardis build examples/structured-summary --output .artifacts
```

Then confirm the documentation for what you changed still matches it — see
[when you change X](#when-you-change-x-also-change-y).

Tests are standard-library `unittest`, discovered from `tests/`, using only
PyYAML and Pillow beyond it. Ruff is the only development tool, pinned in the
`lint` extra and configured in [pyproject.toml](pyproject.toml); CI fails a pull
request it reports on. Do not introduce a pytest, formatter, or type checker as a
side effect of another change. Ruff selects errors and bug patterns, not
formatting, so nothing enforces line length or import order: widen `select`
deliberately, and prefer fixing a finding over adding to `ignore`.

`build` is the only command that writes; every other command reads sources and
prints a report.

- Build into a throwaway directory such as `.artifacts`, never a real agent skill
  directory: a rebuild replaces that skill's folder and ZIP there. A build whose
  `--output` overlaps a source tree is refused.

The conformance cases in [tests/test_conformance.py](tests/test_conformance.py)
are where the format's guarantees are stated, one case per test, each with the
failure it prevents in its docstring. Read them before changing what a bundle
looks like; a guarantee that is not one of those cases is not yet a guarantee.

## Invariants

Preserve these, or change one deliberately and say why. Each states a property to
hold, not the mechanism currently holding it — read the code and its tests for
that, and do not copy either back into this file.

- **Required execution is progressively complete.** `SKILL.md` is the control
  plane; required workflow bodies live under `execution/`, and every edge
  between them is compiler-generated and fail-closed. Arbitrary documentation
  links cannot carry required execution.
- **A heading is a command, never a topic.** Every generated node's heading
  states the action, check, decision, or return that node performs, so an agent
  skimming headings reads what to do rather than being invited to infer content
  from a title. A heading that reads as a topic, or a command that does not
  close as a sentence, is reported.
- **A prohibition renders as the negative command it means.** A provision's own
  sentence names the thing not to do, which as a heading would read as an
  instruction to do it, so the heading states the negative and the source's own
  sentence is kept beside it.
- **Runtime node ids are short, opaque, and deterministic.** They are derived
  from stable semantic source identity, so a rebuild reproduces them; full
  provenance stays in inspection data rather than in a runtime label, and a
  collision is a build error rather than an order-dependent rename.
- **`blocked` is the compiler's outcome, not the source's.** Every workflow
  declares it, every binding check can return it, and a source may not declare,
  return, or map it (`workflow.reserved-outcome`). It names what failed and what
  was available to it, so a run that stops says why.
- **A gate that verifies a check has to dominate it.** `verify: {gate: X}` reads
  X's decision, so X must lie on every path to the node the check constrains;
  otherwise the verification names a value that may not exist
  (`workflow.missing-gate`).
- **Advice can never become authority.** A heuristic renders only on the
  decision or gate that named it; naming one in a verification, a state
  transition, an effect authorization, a return contract, or on any other step
  form is reported (`heuristic.invalid-placement`,
  `heuristic.used-as-authority`). Guidance renders once per scope, and a
  generated page carries no binding command.
- **Profiles are auxiliary retrieval material, never execution state.**
  Workflows never select or depend on a profile, and removing the complete
  generated `profiles/` tree must leave `SKILL.md` and every `execution/` module
  byte-for-byte unchanged. A profile missed, or matched wrongly, therefore
  cannot change validity or failure.
- **A `during` item renders beside a command, so only a form that states one
  carries it.** An action, a call, a pattern procedure item, and a return do; a
  decision, a gate, and a branch state a choice instead. The selector is matched
  at every form so that a `during` item selecting only those three is reported
  as active-and-unlowered — an error naming the phase — rather than as a
  selector that matched nothing, which would leave a bound policy out of the
  document behind a warning.
- **Every check code is a literal with an explanation, and every explanation has
  a check.** A code must appear as a string literal in the module that reports
  it and have an `explain.py:CHECKS` entry. Both directions matter: a code
  assembled at runtime can no longer be checked against that table, and an entry
  no module can report describes a check the compiler never runs.
- **Code spelling.** `namespace.hyphenated-name`, except where it names a key of
  the source, which it spells exactly as the key does —
  `interface.short_description-length`, not `short-description-length`. The rule
  is stated to the reader where an unrecognized code lists the known ones, so an
  author who knows the key can build the code rather than look it up.
- **A required field that is absent reports a check naming the key.** The three
  ways a field goes wrong are three checks, because they are three repairs:
  `<namespace>.missing-<key>` for a required field that is not there,
  `<namespace>.unknown-field` for one the schema does not declare, and
  `<namespace>.invalid-shape` for a value that is there and cannot be read. That
  holds for every construct, the manifest, `content`, and `interface`, so an
  author who knows the key can build the code rather than read a message. Each
  code is written out at the call site that reports it rather than assembled or
  looked up in a table, which is what lets the coverage check find it. The
  exception is a field nested in a provision, a hook, a step, a procedure item,
  or an advice item: its absence keeps the enclosing item's check, because there
  the item rather than the file is the unit an author repairs.
- **Checks collect; they do not stop at the first problem.** `Diagnostics`
  gathers every finding, and `explain` explains every code it was given and names
  all unknown ones together. It keeps one record per distinct finding, so a
  message naming only the file it was found in makes two findings identical and
  drops one: name what was refused — the construct, the field, the node, the
  pattern — not just where.
- **Every help text naming the source format reads `CURRENT_FORMAT_VERSION`**,
  imported from the module whose check enforces it, so none can drift from what
  `validate` accepts. Only a hardcoded literal reintroduces that risk, so a
  command states the format where its reader needs it rather than sending them
  to another command's `-h`.
- **One set of findings, three renderings.** `validate`, the `inspect` line
  report, and `build` run the same checks over the same compilation and set the
  same exit status; `--only` and `--all` choose what is printed, never what is
  checked. Anything that checks a source belongs in `validate.py`'s own
  inspection, not on one output path.
- **The report is the only machine interface.** No workflow, step, protocol,
  record, runtime, coverage, or source-map file is emitted beside the document —
  which is something the `inspect` help has to say, since an agent has that help
  and nothing else.
- **Builds are atomic per skill.** A failure leaves existing artifacts as they
  were, a completed sibling still commits, and a promoted warning stops the
  build before anything is written.
- **A rebuild is byte-identical, on every host.** Nothing in generated text, a
  node label, or a section order may depend on the machine, the filesystem, or
  discovery order.
- **`-h` works on either side of the command name:** `degardis -h build` prints
  what `degardis build -h` prints.
- **One version source.** `degardis/__init__.py:__version__`; the publish
  workflow refuses a release whose tag is not `v<that version>`.
- **Report shape is contract.** A report row's columns and their order, a summary
  line, and help text are as much an interface as the CLI options are.
- **The root's section order is fixed, and it carries nothing it can point at.**
  No workflow body, no workflow directory, no profile catalog, no reference,
  script, or asset index; a section with nothing to carry contributes no heading
  at all. The root is loaded every time the skill is selected, so it is held to
  a smaller attention budget than an execution module.
- **A budget is what one load costs its reader.** The root's and a module's
  limits exist to keep a generated file inside a single read on a host whose
  own limits the compiler cannot know. Neither is a round number chosen for
  looking like a limit; change one only against what a reader actually pays.
- **Optimize reading without skipping execution.** Module planning may reorder
  independent nodes and move boundaries, but every required node and edge stays
  reachable. Compare complete layouts by worst-path execution bytes, then loads,
  then total execution bytes; count each call invocation and pair its outcome
  with only its own continuation. Profiles cannot decide placement.

## Who each text is written for

- **`README.md` and `docs/`** are for people: a reader deciding whether to use
  Degardis, authoring a skill, or looking a command up. Keep them prose, and do
  not mirror agent-facing output fields into them beyond what that reader needs.
- **`degardis inspect` — its output and its `--help` — is for AI agents.** An
  agent running the installed CLI has only help output: no README, no `docs/`. So
  that epilog is its complete account of the command and of the CLI around it —
  the dimensions, the source-format vocabulary, the output legend, how to gate on
  the result, the exit status, the sibling commands it needs next, and runnable
  examples. Agent-facing text may send a reader to another command's `-h`, never
  to `docs/`.
- **`validate`, `list`, and `build` reports** are for a person at a terminal;
  `validate` is the CI gate a person reads. An agent wanting the same findings as
  data uses `inspect --only diagnostics`.
- **The `explain` table** is for whoever repairs a source, agent or author: what
  triggers the check, why it matters, and a failing and a passing example. It is
  hand-written because a check knows its condition, not why an author should
  care.
- **The generated `SKILL.md`** is for the agent executing the skill. Its only
  compiler-owned words live in `wording.py`; everything else is the author's own
  command, rendered where it is enforced.
- **Diagnostic messages** name what is wrong and where, and carry the code, so a
  reader can look the check up instead of guessing.

## Conventions

- Start every module with `from __future__ import annotations`, and annotate
  public signatures.
- Keep to the 3.10 language floor; nothing newer may be required to import the
  package.
- Write docstrings that explain why the code is shaped this way — the failure it
  prevents, the alternative rejected, the invariant it holds — and omit them
  where the name already says it. `fingerprint.py` and `lowering.py`'s frame and
  label sections are the house style. A module's own docstring is what tells the
  next reader what it owns, which is why no inventory of that lives here.
- Nothing enforces formatting; match the surrounding file's wrapping and layout.
- Ask before adding a dependency, including a test-only one.
- A failure carries its check code however it reaches the caller — raised,
  collected, or printed — so `degardis explain` follows from any of them. A
  raise a check explains passes the code; a one-off failure no check names
  passes nothing.

## When you change X, also change Y

| Change | Also update |
| --- | --- |
| A check | The literal code, its `explain.py:CHECKS` entry, and `docs/reference.md` where it changes what `validate` accepts |
| A construct's schema — a field, a phase, a step form, a selector key | The field set in `sources.py`, the check that rejects unknown keys, `lowering.py` where that field is enforced, `render.py` where it appears, and that construct's section in `docs/reference.md` |
| A required field, on any schema | The `missing` code written at the call site that reads it, its `explain.py:CHECKS` entry, and that schema's required rows in `docs/reference.md` |
| A manifest or `interface` key | `registry.py`'s field set and its checks, `content.py` where it selects files, `package.py` where it reaches the interface metadata, and the `skill.yaml` section of `docs/reference.md` |
| The DExpr grammar, a namespace, or a type | `dexpr.py`, the checks that report its codes, and the DExpr section of `docs/reference.md` |
| What a scope binds, or where lowering puts it | `lowering.py`'s scope resolution and node placement, the checks in `validate.py` that hold every bound item to a node, `render.py`'s node shape, and both the schema and the lowering sections of `docs/reference.md` |
| A CLI option or command | The command's help and `Examples:` block in `cli.py`, the CLI section of `docs/reference.md`, and the command list in `README.md` |
| An inspect dimension or one of its rows | `output.py`, `INSPECT_DIMENSIONS` in `validate.py`, the `inspect` epilog legend, and the `inspect` section of `docs/reference.md` |
| The wording of a generated Markdown section | `wording.py` only; `render.py` holds the structure, not the words |
| The generated bundle's layout | `package.py`, `render.py`'s page targets, the conformance cases that read it, `docs/artifact-format.md`, and `docs/concepts.md` |
| The source format | `CURRENT_FORMAT_VERSION` and every section of `docs/reference.md` the change reaches |
| The version | `degardis/__init__.py` only, tagged `v<version>` |

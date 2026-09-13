### Building a bundle

```console
degardis build my-skill --output .artifacts
```

By default, each skill is written as a folder. Add `--zip` to write a ZIP
archive instead. Add `--fail-on-warning` to stop before writing when any warning
is reported; without it, warnings do not block the build.

Every selected skill is checked before the first byte is written. A build is
atomic per skill: a failure leaves an existing artifact exactly as it was, and a
sibling that completed still commits.

Build into a throwaway directory rather than a live agent skill directory: a
rebuild replaces that skill's folder and ZIP there.

A rebuild is byte-identical, on every host. Nothing in the generated text or in
the order of its sections depends on the machine, the filesystem, or the order
files were discovered in.

### Page budgets

Four page types have budgets, and all findings are warnings rather than errors.

`SKILL.md` is charged against every run, since it is loaded before any work
begins.

A task page is opened once, after the agent knows what it is doing. It carries
the task's whole knowledge closure, so it has the one-load budget. A host may
return an oversized page truncated.

Each principle or guide page is one additional load. Its activation determines
when the reader opens it; without activation, it applies unconditionally. The
principle and guide budgets apply to their respective pages.

Nothing is ever dropped to make a page fit. The finding names the largest
contributors, and the repairs are yours: remove knowledge the task does not need,
shorten what it does, split a task that is really two, or move material to a
separate guide load. For an oversized principle or guide, shorten
it or divide genuinely distinct material into separately usable files.

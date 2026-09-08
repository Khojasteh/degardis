## The source folder

The source is an ordinary folder that you edit and keep. `degardis build` turns
it into a separate bundle for an agent host. You never edit that bundle, and a
command pointed at one—a directory holding `SKILL.md` and no `skill.yaml`, or a
ZIP archive—is reported rather than read.

`skill.yaml` sits at the top of the folder. Every other selected YAML file
defines one named construct, and the manifest's `content` patterns decide which
files are selected.

The following tree is a useful convention. It makes a skill easy to browse, but
the manifest—not the directory name—decides what each selected file is.

```text
my-skill/
  skill.yaml
  workflows/
  policies/
  rules/
  protocols/
  patterns/
  heuristics/
  guidance/
  records/
  profiles/
  references/
  scripts/
  assets/
```

Two rules bound the folder. Everything the skill ships must sit inside it: a
content pattern or a resource path that resolves outside the skill directory
is reported. And a build output directory may not be the source
directory, sit inside one, or contain one, so build into a throwaway directory
such as `.artifacts` while you work.

### Extension fields

Use a field beginning with `x-`, such as `x-owner`, for metadata another tool
owns. You may add extension fields at the top level of `skill.yaml` and in any
Markdown frontmatter block. Every extension value must be valid YAML.

Extension fields are for the tool that owns them. They are ignored by Degardis.
Beyond reading the value under the YAML profile, Degardis does not validate an
extension field's shape or meaning.

All unprefixed field names are reserved for Degardis. An unrecognized manifest
field is refused. An unrecognized unprefixed field in task, knowledge,
principle, profile, or guide frontmatter produces a warning, because it may be a
misspelling or collide with a field Degardis defines later. Rename metadata your
own tool uses with an `x-` prefix.

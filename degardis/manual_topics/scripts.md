### Scripts

`content.scripts` selects files a skill ships to be run. The compiler copies each
one byte for byte.

A ZIP bundle records the file executable. A folder build leaves its permissions
as it found them, so a host reading skills from the filesystem takes them from
your source tree.

Link to a script from authored Markdown where an agent needs to run it:

```markdown
Run [[script:check.py]] before publishing the result.
```

The inline target is relative to the `scripts/` root. A selected script that no
authored Markdown links to is reported as a warning: the bundle would carry a
file no reader reaches.

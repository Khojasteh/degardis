### Scripts

`content.scripts` selects files a skill ships to be run. The compiler copies
each one byte for byte and writes it executable in the bundle.

Link to a script from authored Markdown where an agent needs to run it:

```markdown
Run [[script:check.py]] before publishing the result.
```

The inline target is relative to the script directory. Every selected script
must be linked from authored Markdown.

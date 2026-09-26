### Scripts

`content.scripts` selects executable helpers. Each selected script is copied unchanged to the same path it has in the source, wherever the manifest selects it from, and is executable in both folder and ZIP builds, whatever permissions the source file has. A file selected as an asset is never executable, even under a `scripts/` directory.

An inline reference links a script:

```markdown
Run [[script:check.py]] before publishing.
```

The target is the script's source-relative path, or any trailing part of it made of whole segments. When it ends more than one selected script, as `check.py` ends both `scripts/check.py` and `tools/check.py`, the reference is refused until it names one, such as `tools/check.py`. A selected script with no inline reference warns because no reader reaches it.

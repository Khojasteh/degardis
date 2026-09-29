### Scripts

`content.scripts` selects executable helpers. Each selected script is copied unchanged and is executable in both folder and ZIP builds, wherever it sits and whatever permissions the source file has. No other bundle file is executable, including a file selected as an asset under a `scripts/` directory.

A selected script with no inline reference warns because no reader reaches it.

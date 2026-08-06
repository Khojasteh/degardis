"""How YAML problems reach the author."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from degardis.cli import main
from degardis.validate import validate

from tests.support import copy_skills


class YamlReportingTests(unittest.TestCase):
    def test_malformed_yaml_is_reported_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = copy_skills(Path(directory))
            manifest = root / "alpha" / "skill.yaml"
            manifest.write_text("name: alpha\ninterface: [\n", encoding="utf-8")

            for command in ("list", "validate", "build"):
                with self.subTest(command=command):
                    stderr = io.StringIO()
                    arguments = [command, str(root / "alpha")]
                    if command == "build":
                        arguments.extend(["--output", str(root / "output")])
                    with contextlib.redirect_stderr(stderr):
                        code = main(arguments)

                    self.assertEqual(1, code)
                    self.assertIn("[ERROR]", stderr.getvalue())
                    self.assertIn("Invalid YAML", stderr.getvalue())

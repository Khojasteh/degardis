"""The status line: that it moves, that it stays off a pipe, and that it is inert.

The line exists only to prove a slow compilation is alive, so the behaviors
worth pinning are that it advances on its own, that a redirected stream collects
nothing extra, and that a run which draws it produces exactly the bundle and the
findings a run which draws nothing produces.
"""

from __future__ import annotations

import io
import time
import unittest

from degardis.progress import StatusLine, status_line
from degardis.validate import compile_all

from tests.support import CANONICAL_EXAMPLE, FIXTURES


class Terminal(io.StringIO):
    """A stream that claims to be a terminal, which is the only thing checked."""

    encoding = "utf-8"

    def isatty(self) -> bool:
        return True


class Pipe(io.StringIO):
    encoding = "utf-8"

    def isatty(self) -> bool:
        return False


class DisplaySelectionTests(unittest.TestCase):
    def test_a_redirected_stream_is_given_the_silent_display(self):
        """A pipe, a log, and an agent reading the CLI must see no extra byte."""
        stream = Pipe()
        with status_line(stream) as watcher:
            watcher.phase("Reading demo")
            time.sleep(0.25)
        self.assertEqual("", stream.getvalue())

    def test_a_stream_that_cannot_say_whether_it_is_a_terminal_stays_silent(self):
        class Mute(io.StringIO):
            def isatty(self):
                raise ValueError("detached")

        stream = Mute()
        with status_line(stream) as watcher:
            watcher.phase("Reading demo")
        self.assertEqual("", stream.getvalue())

    def test_a_terminal_is_given_the_live_display(self):
        stream = Terminal()
        with status_line(stream) as watcher:
            self.assertIsInstance(watcher, StatusLine)
            watcher.phase("Reading demo")
        self.assertIn("Reading demo", stream.getvalue())


class StatusLineTests(unittest.TestCase):
    def test_the_line_advances_while_one_phase_keeps_running(self):
        """A label that has not moved proves nothing; this is the whole point."""
        stream = Terminal()
        with status_line(stream) as watcher:
            watcher.phase("Planning modules 3/42")
            time.sleep(0.45)
        painted = stream.getvalue().count("Planning modules 3/42")
        self.assertGreater(painted, 1)

    def test_the_line_is_erased_before_the_caller_writes_its_report(self):
        stream = Terminal()
        with status_line(stream) as watcher:
            watcher.phase("Reading demo")
        # Whatever was drawn, the cursor is back at the start of a blank row.
        tail = stream.getvalue().rsplit("\r", 2)[-2]
        self.assertEqual("", tail.strip())

    def test_a_stream_that_fails_mid_run_does_not_fail_the_run(self):
        class Breaks(Terminal):
            def write(self, text):
                raise OSError("gone")

        with status_line(Breaks()) as watcher:
            watcher.phase("Reading demo")
            time.sleep(0.15)


class CompilationIsUnaffectedTests(unittest.TestCase):
    def test_a_displayed_run_and_a_silent_run_compile_the_same_bundle(self):
        """Progress may name a phase; it may not reach a byte or a finding."""
        for root in (CANONICAL_EXAMPLE, FIXTURES / "alpha"):
            with self.subTest(skill=root.name):
                quiet = compile_all([root])[0]
                shown = compile_all([root], StatusLine(Terminal()))[0]
                self.assertEqual(
                    quiet.compiled.rendered.execution_modules,
                    shown.compiled.rendered.execution_modules,
                )
                self.assertEqual(
                    quiet.compiled.rendered.skill_text,
                    shown.compiled.rendered.skill_text,
                )
                self.assertEqual(
                    [item.code for item in quiet.diagnostics.records],
                    [item.code for item in shown.diagnostics.records],
                )


if __name__ == "__main__":
    unittest.main()

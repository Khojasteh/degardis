"""Tell a person at a terminal that a slow compilation is still running.

Compiling a large skill spends seconds inside two phases that print nothing, so
a silent run is indistinguishable from a hung one. The status line is therefore
animated on a timer rather than only on phase changes: a label that has not
moved for three seconds proves nothing, while a turning spinner and a rising
elapsed time do.

It writes to stderr so the report on stdout stays pipeable, and only when that
stream is a terminal, so a redirected run, a CI log, and an agent reading the
output all see exactly the bytes they saw before. Nothing here is a report: the
line is erased before the caller writes one, and no part of it is a record of
what the build did.
"""

from __future__ import annotations

import itertools
import shutil
import threading
import time
from types import TracebackType
from typing import TextIO


TICK_SECONDS = 0.1
# Below this the run is over before a reader could look, and a number that
# appears and vanishes reads as a glitch rather than as progress.
ELAPSED_AFTER_SECONDS = 0.5
FRAMES = "|/-\\"
FANCY_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class Progress:
    """The default: a compiler that reports progress to nobody.

    Every phase call goes through this class, so the compiler names its phases
    once and the caller decides whether anything renders them.
    """

    def phase(self, label: str) -> None:
        """Name what is running now."""

    def close(self) -> None:
        """Release the display, leaving the stream as it was found."""

    def __enter__(self) -> Progress:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class Scope(Progress):
    """A display that adds the same suffix to every phase handed to it.

    A phase names what is running; which of several skills it is running for
    belongs to the caller that knows the position. Keeping the two apart lets
    the compiler name its phases without counting anything, and closing a scope
    leaves the display open, because the scope never owned it.
    """

    def __init__(self, inner: Progress, suffix: str) -> None:
        self._inner = inner
        self._suffix = suffix

    def phase(self, label: str) -> None:
        self._inner.phase(f"{label}{self._suffix}")


class StatusLine(Progress):
    """One rewritten terminal line, advanced by a timer as well as by phases."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._frames = _frames(stream)
        self._label = ""
        self._started = time.monotonic()
        self._width = 0
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._spin = itertools.cycle(self._frames)
        self._ticker = threading.Thread(target=self._run, daemon=True)
        self._ticker.start()

    def phase(self, label: str) -> None:
        with self._lock:
            self._label = label
            self._draw()

    def close(self) -> None:
        self._done.set()
        self._ticker.join(timeout=1.0)
        with self._lock:
            self._erase()

    def _run(self) -> None:
        while not self._done.wait(TICK_SECONDS):
            with self._lock:
                self._draw()

    def _draw(self) -> None:
        if self._done.is_set() or not self._label:
            return
        elapsed = time.monotonic() - self._started
        text = f"{next(self._spin)} {self._label}"
        if elapsed >= ELAPSED_AFTER_SECONDS:
            text += f" [{elapsed:.0f}s]"
        # A line that wraps cannot be rewritten by a carriage return: the
        # cursor comes back to the start of the last row, not of the message.
        limit = max(shutil.get_terminal_size((80, 24)).columns - 1, 20)
        if len(text) > limit:
            text = text[: limit - 1] + "…" if _fancy(self._stream) else text[:limit]
        self._paint(text.ljust(self._width))
        self._width = len(text)

    def _erase(self) -> None:
        if self._width:
            self._paint(" " * self._width)
            self._width = 0

    def _paint(self, text: str) -> None:
        try:
            self._stream.write("\r" + text + "\r")
            self._stream.flush()
        except (OSError, ValueError):
            # A closed or detached stream must not fail the build it decorates.
            self._done.set()


def _fancy(stream: TextIO) -> bool:
    """Can this stream carry the characters a nicer line would use?"""
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        "…".encode(encoding)
        FANCY_FRAMES.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _frames(stream: TextIO) -> str:
    return FANCY_FRAMES if _fancy(stream) else FRAMES


def status_line(stream: TextIO) -> Progress:
    """A live line where a person is watching, and silence everywhere else.

    Being at a terminal is the whole condition. A redirected stream, a pipe, a
    log file, and an agent reading the CLI all take the silent form, so the
    bytes any of them collects are unchanged and no caller has to ask for that.
    """
    if not hasattr(stream, "isatty"):
        return Progress()
    try:
        interactive = stream.isatty()
    except (OSError, ValueError):
        return Progress()
    return StatusLine(stream) if interactive else Progress()

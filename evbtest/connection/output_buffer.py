"""Thread-safe output buffer with regex pattern matching."""

import re
import threading
import time
from typing import Optional


class OutputBuffer:
    """Thread-safe output buffer with regex pattern matching.

    Used by both SSH and TCP serial connections.
    Provides:
      - append(text): add new output (from reader thread)
      - read_new(): get everything since last read
      - wait_for_pattern(): block until regex appears or timeout
      - peek_unconsumed(): non-blocking check without advancing position
      - clear(): discard buffered content
    """

    def __init__(self, max_size: int = 1_000_000):
        self._buffer = ""
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._max_size = max_size
        self._read_pos = 0

    def append(self, text: str) -> None:
        """Add new output data. Called from reader threads."""
        with self._condition:
            self._buffer += text
            # Trim from front if over max size
            if len(self._buffer) > self._max_size:
                overflow = len(self._buffer) - self._max_size
                self._buffer = self._buffer[overflow:]
                self._read_pos = max(0, self._read_pos - overflow)
            self._condition.notify_all()

    def read_new(self, wait: bool = False, timeout: float = 1.0) -> str:
        """Return all text since last read_new call. Advances read position."""
        with self._condition:
            if wait and self._read_pos >= len(self._buffer):
                self._condition.wait(timeout=timeout)
            new_text = self._buffer[self._read_pos :]
            self._read_pos = len(self._buffer)
            return new_text

    def wait_for_pattern(
        self, pattern: str | re.Pattern, timeout: float = 30.0
    ) -> tuple[str, Optional[re.Match]]:
        """Block until pattern appears in unconsumed buffer data.

        Only searches from _read_pos onwards. On match, advances _read_pos
        and returns the matched text. On timeout, does NOT advance _read_pos
        so data is preserved for the next caller.
        """
        if isinstance(pattern, str):
            regex = re.compile(pattern)
        else:
            regex = pattern

        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                unconsumed = self._buffer[self._read_pos :]
                match = regex.search(unconsumed)
                if match:
                    self._read_pos = len(self._buffer)
                    return unconsumed, match
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return unconsumed, None
                self._condition.wait(timeout=remaining)

    def peek_unconsumed(self) -> str:
        """Return unconsumed text without advancing read position."""
        with self._lock:
            return self._buffer[self._read_pos :]

    def drain(self) -> None:
        """Advance read position to end, discarding unconsumed data.

        Called before sending a new command to ensure wait_for_pattern
        only matches data that arrives AFTER the command is sent.
        """
        with self._condition:
            self._read_pos = len(self._buffer)

    def clear(self) -> None:
        """Discard all buffered content."""
        with self._condition:
            self._buffer = ""
            self._read_pos = 0

    def get_all(self) -> str:
        """Return entire buffer contents without advancing read position."""
        with self._lock:
            return self._buffer

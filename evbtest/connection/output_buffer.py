"""Thread-safe output buffer with regex pattern matching."""

import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class OutputBuffer:
    """Thread-safe output buffer with regex pattern matching.

    Used by both SSH and TCP serial connections.
    Optionally writes all I/O to a session log file.
    """

    def __init__(self, max_size: int = 1_000_000):
        self._buffer = ""
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._max_size = max_size
        self._read_pos = 0
        self._log_file = None
        self._log_lock = threading.Lock()

    def set_session_log(self, path: str | Path) -> None:
        """Open a session log file. All subsequent append/send data is written."""
        with self._log_lock:
            if self._log_file:
                self._log_file.close()
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._log_file = open(path, "a", encoding="utf-8")

    def close_session_log(self) -> None:
        """Close the session log file."""
        with self._log_lock:
            if self._log_file:
                self._log_file.close()
                self._log_file = None

    # ANSI escape sequence pattern
    _ANSI_RE = re.compile(r"\x1b\[[^a-zA-Z]*[a-zA-Z]|\x1b\][^\x07]*\x07")

    def _write_log(self, direction: str, text: str) -> None:
        """Write a log entry.

        For sends (>>>): write a single marked line with timestamp.
        For receives (<<<): append cleaned text as-is, no per-chunk prefix.
        """
        with self._log_lock:
            if not self._log_file:
                return
            if direction == ">>>":
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                self._log_file.write(f"\n[{ts}] >>> {text.strip()}\n")
            else:
                # Strip ANSI and normalize line endings for readability
                clean = self._ANSI_RE.sub("", text)
                clean = clean.replace("\r\n", "\n").replace("\r", "")
                self._log_file.write(clean)
            self._log_file.flush()

    def log_send(self, data: str) -> None:
        """Log data sent to device."""
        self._write_log(">>>", data)

    def log_command_block(self, command: str, output: str) -> None:
        """Write a structured command+output block to the session log.

        Called from the executor after a command completes, ensuring
        proper ordering (no interleaving with other commands).
        """
        with self._log_lock:
            if not self._log_file:
                return
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._log_file.write(f"\n[{ts}] >>> {command}\n")
            if output:
                self._log_file.write(output)
                if not output.endswith("\n"):
                    self._log_file.write("\n")
            self._log_file.flush()

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
        """Advance read position to end, discarding unconsumed data."""
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

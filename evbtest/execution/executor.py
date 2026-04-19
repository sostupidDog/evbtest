"""Command execution engine."""

import re
import time
from dataclasses import dataclass

from evbtest.connection.base import ConnectionBase
from evbtest.connection.exceptions import PatternTimeoutError

# ANSI escape sequence pattern for stripping from output
_ANSI_RE = re.compile(r"\x1b\[[^a-zA-Z]*[a-zA-Z]|\x1b\][^\x07]*\x07")


@dataclass
class CommandResult:
    """Result of a single command execution."""

    command: str
    output: str
    match: re.Match | None = None
    success: bool = True
    elapsed: float = 0.0


class CommandExecutor:
    """High-level command execution on a ConnectionBase.

    Handles:
      - Sending command + newline
      - Stripping command echo from output
      - Waiting for a prompt or arbitrary pattern
      - Timeout enforcement
      - Fire-and-forget commands (no wait)
      - Raw byte sequences (for U-Boot interrupt, special keys)
    """

    def __init__(
        self,
        connection: ConnectionBase,
        default_prompt: str = r"[#\$>]\s*$",
        echo_strip: bool = True,
    ):
        self._conn = connection
        self._default_prompt = default_prompt
        self._echo_strip = echo_strip

    def execute(
        self,
        command: str,
        wait_for: str | None = None,
        timeout: float | None = None,
        send_newline: bool = True,
    ) -> CommandResult:
        """Execute command and wait for response.

        Args:
            command: The command string to send.
            wait_for: Regex pattern to wait for. If None, uses default_prompt.
                      Pass "" (empty string) for fire-and-forget.
            timeout: Seconds to wait. None uses connection default.
            send_newline: Whether to append \\n to command.

        Returns:
            CommandResult with output, match, timing.

        Raises:
            PatternTimeoutError if pattern not matched within timeout.
        """
        effective_timeout = timeout or self._conn.timeout
        effective_pattern = wait_for if wait_for is not None else self._default_prompt

        start = time.monotonic()
        # Drain stale output before sending, so read_until only matches
        # data that arrives AFTER this command
        self._conn.drain()
        self._conn.send(command)
        if send_newline:
            self._conn.send("\n")

        if effective_pattern == "":
            # Fire-and-forget
            return CommandResult(command=command, output="", elapsed=0.0)

        output, match = self._conn.read_until(effective_pattern, timeout=effective_timeout)
        elapsed = time.monotonic() - start

        if match is None:
            raise PatternTimeoutError(effective_pattern, output, effective_timeout)

        # Strip the echoed command line from output
        clean_output = self._strip_echo(command, output) if self._echo_strip else output
        # Strip ANSI escape sequences
        clean_output = _ANSI_RE.sub("", clean_output)
        # Normalize line endings
        clean_output = clean_output.replace("\r\n", "\n").replace("\r", "")

        return CommandResult(
            command=command,
            output=clean_output,
            match=match,
            success=True,
            elapsed=elapsed,
        )

    def execute_raw(self, data: bytes | str) -> None:
        """Send raw data without any processing.

        For sending Ctrl-C, U-Boot interrupt sequences, etc.
        """
        self._conn.send(data)

    def wait_for(
        self,
        pattern: str,
        timeout: float | None = None,
        error_on_timeout: bool = True,
    ) -> CommandResult:
        """Wait for a pattern without sending anything.

        Useful for watching boot output.
        """
        effective_timeout = timeout or self._conn.timeout
        start = time.monotonic()
        output, match = self._conn.read_until(pattern, timeout=effective_timeout)
        elapsed = time.monotonic() - start

        if error_on_timeout and match is None:
            raise PatternTimeoutError(pattern, output, effective_timeout)

        # Strip ANSI escapes and normalize line endings
        output = _ANSI_RE.sub("", output)
        output = output.replace("\r\n", "\n").replace("\r", "")

        return CommandResult(
            command="<wait>",
            output=output,
            match=match,
            success=(match is not None),
            elapsed=elapsed,
        )

    def wait_for_any(
        self,
        patterns: list[str],
        timeout: float | None = None,
    ) -> tuple[CommandResult, int]:
        """Wait for any of several patterns.

        Returns (result, index_of_matched_pattern).
        Useful for 'wait for login: OR wait for U-Boot>'.
        """
        effective_timeout = timeout or self._conn.timeout
        compiled = [re.compile(p) for p in patterns]
        deadline = time.monotonic() + effective_timeout
        start = time.monotonic()

        while True:
            for i, regex in enumerate(compiled):
                output, match = self._conn.read_until(regex.pattern, timeout=0.05)
                if match is not None:
                    elapsed = time.monotonic() - start
                    return (
                        CommandResult(
                            command="<wait_any>",
                            output=output,
                            match=match,
                            success=True,
                            elapsed=elapsed,
                        ),
                        i,
                    )

            if time.monotonic() >= deadline:
                elapsed = time.monotonic() - start
                output = self._conn.read(timeout=0.1)
                return (
                    CommandResult(
                        command="<wait_any>",
                        output=output,
                        success=False,
                        elapsed=elapsed,
                    ),
                    -1,
                )

    def send_line(self, text: str) -> None:
        """Send text + newline without waiting. Fire-and-forget."""
        self._conn.send(text + "\n")

    def _strip_echo(self, command: str, output: str) -> str:
        """Remove the echoed command from the beginning of output.

        SSH/serial terminals echo the command back. We strip the first line
        if it matches the sent command.
        """
        lines = output.split("\n")
        if lines and command.strip() in lines[0].strip():
            return "\n".join(lines[1:])
        return output

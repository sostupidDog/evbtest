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
        self._default_prompt = re.compile(default_prompt)
        self._echo_strip = echo_strip

    def execute(
        self,
        command: str,
        wait_for: str | None = None,
        timeout: float | None = None,
        send_newline: bool = True,
    ) -> CommandResult:
        """Execute command and wait for response.

        Always waits for the default prompt to ensure complete output capture.
        If wait_for is provided, additionally verifies it appears in the output.

        Args:
            command: The command string to send.
            wait_for: Optional regex to verify in output after prompt returns.
                      Pass "" (empty string) for fire-and-forget.
            timeout: Seconds to wait. None uses connection default.
            send_newline: Whether to append \\n to command.

        Returns:
            CommandResult with output, match, timing.

        Raises:
            PatternTimeoutError if prompt or wait_for pattern not matched.
        """
        effective_timeout = timeout or self._conn.timeout

        start = time.monotonic()
        # Drain stale output before sending, so read_until only matches
        # data that arrives AFTER this command
        self._conn.drain()
        self._conn.send(command)
        if send_newline:
            self._conn.send("\n")

        if wait_for == "":
            # Fire-and-forget
            return CommandResult(command=command, output="", elapsed=0.0)

        # Always wait for default prompt -- guarantees complete output
        output, match = self._conn.read_until(
            self._default_prompt, timeout=effective_timeout
        )
        elapsed = time.monotonic() - start

        if match is None:
            raise PatternTimeoutError(self._default_prompt, output, effective_timeout)

        # Strip the echoed command line from output
        clean_output = self._strip_echo(command, output) if self._echo_strip else output
        # Strip ANSI escape sequences
        clean_output = _ANSI_RE.sub("", clean_output)
        # Normalize line endings
        clean_output = clean_output.replace("\r\n", "\n").replace("\r", "")

        # Verify optional wait_for pattern appears in output
        if wait_for is not None:
            wf_match = re.search(wait_for, clean_output)
            if wf_match is None:
                raise PatternTimeoutError(wait_for, clean_output, effective_timeout)
            match = wf_match

        # Log the complete command block to session log
        self._conn.log_command_block(command, clean_output)

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

        # Log to session log
        self._conn.log_command_block(f"<wait: {pattern}>", output)

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
        Useful for 'wait for login: OR wait for U-Boot'.

        Combines all patterns into a single regex so only one read_until
        call is needed, avoiding the busy-wait loop.
        """
        effective_timeout = timeout or self._conn.timeout
        compiled = [re.compile(p) for p in patterns]

        # Combine into single regex: (?:p1)|(?:p2)|(?:p3)
        combined = re.compile("|".join(f"(?:{p})" for p in patterns))

        start = time.monotonic()
        output, match = self._conn.read_until(combined, timeout=effective_timeout)
        elapsed = time.monotonic() - start

        if match is None:
            return (
                CommandResult(
                    command="<wait_any>",
                    output=output,
                    success=False,
                    elapsed=elapsed,
                ),
                -1,
            )

        # Determine which original pattern matched
        matched_idx = -1
        for i, regex in enumerate(compiled):
            if regex.search(output):
                matched_idx = i
                break

        return (
            CommandResult(
                command="<wait_any>",
                output=output,
                match=match,
                success=True,
                elapsed=elapsed,
            ),
            matched_idx,
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

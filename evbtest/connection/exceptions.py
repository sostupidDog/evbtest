"""Connection-related exceptions."""


class ConnectionError(Exception):
    """Base connection error."""


class ConnectionTimeoutError(ConnectionError):
    """Operation timed out."""


class ConnectionClosedError(ConnectionError):
    """Remote end closed the connection."""


class PatternTimeoutError(ConnectionError):
    """wait_for_pattern timed out without matching."""

    def __init__(self, pattern, output: str, timeout: float):
        import re as _re
        self.pattern = pattern.pattern if isinstance(pattern, _re.Pattern) else pattern
        self.output = output
        self.timeout = timeout
        super().__init__(
            f"Pattern '{self.pattern}' not found within {timeout}s. "
            f"Last output: {output[-500:]!r}"
        )

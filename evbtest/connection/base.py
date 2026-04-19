"""Abstract base class for all transport connections."""

import re
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Optional


class ConnectionState(Enum):
    """Connection state machine."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ConnectionBase(ABC):
    """Abstract interface for all transport connections.

    Every connection type (SSH, TCP serial, etc.) must implement this.
    The interface is designed around a streaming output model:
    - Call connect() to establish the session
    - Call send() to write data/command bytes
    - Call read() or read_until() to consume output
    - Call disconnect() to tear down
    - Call set_session_log() to enable I/O logging to file
    """

    def __init__(self, connection_id: str, timeout: float = 30.0):
        self.connection_id = connection_id
        self.timeout = timeout
        self._state = ConnectionState.DISCONNECTED
        self._session_log_path: str | None = None

    @property
    def state(self) -> ConnectionState:
        return self._state

    @abstractmethod
    def connect(self) -> None:
        """Establish connection. Raises ConnectionError on failure."""

    @abstractmethod
    def disconnect(self) -> None:
        """Tear down connection cleanly."""

    @abstractmethod
    def send(self, data: bytes | str) -> None:
        """Send raw data. If str, encoded as UTF-8."""

    @abstractmethod
    def read(self, timeout: float | None = None) -> str:
        """Read whatever output is currently available (non-blocking up to timeout).
        Returns empty string if nothing available."""

    @abstractmethod
    def read_until(
        self,
        pattern: str | re.Pattern,
        timeout: float | None = None,
    ) -> tuple[str, re.Match | None]:
        """Block until regex pattern appears in output or timeout.
        Returns (accumulated_output, match_object).
        match_object is None on timeout."""

    def drain(self) -> None:
        """Discard any buffered output. Called before sending a new command
        to ensure read_until only matches data arriving AFTER the send."""

    def set_session_log(self, path: str | Path) -> None:
        """Enable session logging: all sent/received data written to file."""
        self._session_log_path = str(path)

    def close_session_log(self) -> None:
        """Close session log file."""
        self._session_log_path = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.disconnect()

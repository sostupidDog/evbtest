"""SSH connection transport using paramiko."""

import re
import socket
import threading
import time
from typing import Optional

import paramiko

from evbtest.connection.base import ConnectionBase, ConnectionState
from evbtest.connection.exceptions import (
    ConnectionClosedError,
    ConnectionError,
    ConnectionTimeoutError,
)
from evbtest.connection.output_buffer import OutputBuffer


class SSHConnection(ConnectionBase):
    """SSH transport using paramiko invoke_shell for persistent session.

    Uses invoke_shell() rather than exec_command() to maintain a persistent
    terminal session across multi-step flows (e.g., U-Boot -> Linux boot).

    A background reader thread continuously drains the SSH channel into the
    output buffer, enabling condition-variable-based waiting in read_until
    instead of polling recv().
    """

    def __init__(
        self,
        connection_id: str,
        host: str,
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        key_filename: str | None = None,
        timeout: float = 30.0,
    ):
        super().__init__(connection_id, timeout)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_filename = key_filename
        self._client: paramiko.SSHClient | None = None
        self._channel: paramiko.Channel | None = None
        self._buffer = OutputBuffer()
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def connect(self) -> None:
        """Establish SSH connection and open interactive shell.

        Safe to call on an already-disconnected connection (reconnect scenario):
        cleans up stale resources before attempting a new connection.
        """
        # Clean up any stale resources from a previous session
        if self._state not in (ConnectionState.DISCONNECTED, ConnectionState.ERROR):
            self.disconnect()
        self._buffer.clear()

        self._state = ConnectionState.CONNECTING
        try:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                key_filename=self.key_filename,
                timeout=self.timeout,
                look_for_keys=True,
            )
            self._channel = self._client.invoke_shell(
                term="xterm", width=200, height=50
            )
            self._channel.settimeout(0.1)

            # Start background reader thread
            self._stop_event.clear()
            self._reader_thread = threading.Thread(
                target=self._reader_loop, daemon=True
            )
            self._reader_thread.start()

            self._state = ConnectionState.CONNECTED
            if self._session_log_path:
                self._buffer.set_session_log(self._session_log_path)
        except Exception as e:
            self._state = ConnectionState.ERROR
            raise ConnectionError(f"SSH connection failed: {e}") from e

    def _reader_loop(self) -> None:
        """Background thread: continuously read from SSH channel into buffer."""
        while not self._stop_event.is_set():
            try:
                data = self._channel.recv(4096)
                if not data:
                    self._state = ConnectionState.DISCONNECTED
                    break
                text = data.decode("utf-8", errors="replace")
                self._buffer.append(text)
            except socket.timeout:
                continue
            except OSError:
                if not self._stop_event.is_set():
                    self._state = ConnectionState.ERROR
                break

    def disconnect(self) -> None:
        """Tear down SSH connection."""
        self._stop_event.set()
        self._buffer.close_session_log()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=5.0)
        if self._channel:
            try:
                self._channel.close()
            except OSError:
                pass
        if self._client:
            self._client.close()
        self._channel = None
        self._client = None
        self._reader_thread = None
        self._state = ConnectionState.DISCONNECTED

    def set_session_log(self, path) -> None:
        """Set session log path and open log file if already connected."""
        self._session_log_path = str(path)
        if self._state == ConnectionState.CONNECTED:
            self._buffer.set_session_log(path)

    def send(self, data: bytes | str) -> None:
        """Send data over SSH channel."""
        if self._channel is None:
            raise ConnectionError("Not connected")
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._channel.sendall(data)

    def drain(self) -> None:
        """Discard any buffered output."""
        self._buffer.drain()

    def log_command_block(self, command: str, output: str) -> None:
        """Write a structured command+output block to session log."""
        self._buffer.log_command_block(command, output)

    def read(self, timeout: float | None = None) -> str:
        """Return everything accumulated in the buffer since last read."""
        return self._buffer.read_new(wait=True, timeout=timeout or self.timeout)

    def read_until(
        self,
        pattern: str | re.Pattern,
        timeout: float | None = None,
    ) -> tuple[str, re.Match | None]:
        """Block until pattern appears in output or timeout.

        The background reader thread continuously feeds data into the buffer,
        so we delegate to the buffer's wait_for_pattern method which uses
        a Condition variable for efficient blocking.
        """
        return self._buffer.wait_for_pattern(pattern, timeout=timeout or self.timeout)

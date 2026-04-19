"""SSH connection transport using paramiko."""

import re
import socket
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
    terminal session across multi-step flows (e.g., U-Boot → Linux boot).
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

    def connect(self) -> None:
        """Establish SSH connection and open interactive shell."""
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
            self._state = ConnectionState.CONNECTED
            if self._session_log_path:
                self._buffer.set_session_log(self._session_log_path)
        except Exception as e:
            self._state = ConnectionState.ERROR
            raise ConnectionError(f"SSH connection failed: {e}") from e

    def disconnect(self) -> None:
        """Tear down SSH connection."""
        try:
            self._buffer.close_session_log()
            if self._channel:
                self._channel.close()
            if self._client:
                self._client.close()
        finally:
            self._channel = None
            self._client = None
            self._state = ConnectionState.DISCONNECTED

    def send(self, data: bytes | str) -> None:
        """Send data over SSH channel."""
        if self._channel is None:
            raise ConnectionError("Not connected")
        if isinstance(data, str):
            self._buffer.log_send(data)
            data = data.encode("utf-8")
        else:
            self._buffer.log_send(data.decode("utf-8", errors="replace"))
        self._channel.sendall(data)

    def drain(self) -> None:
        """Discard any buffered output."""
        self._buffer.drain()

    def read(self, timeout: float | None = None) -> str:
        """Poll channel for available data."""
        if self._channel is None:
            raise ConnectionError("Not connected")

        deadline = time.monotonic() + (timeout or self.timeout)
        collected = ""

        while time.monotonic() < deadline:
            try:
                chunk = self._channel.recv(4096)
                if chunk:
                    text = chunk.decode("utf-8", errors="replace")
                    self._buffer.append(text)
                    collected += text
                else:
                    # Channel closed
                    self._state = ConnectionState.DISCONNECTED
                    raise ConnectionClosedError("SSH channel closed")
            except socket.timeout:
                if collected:
                    break
                continue
        return collected

    def read_until(
        self,
        pattern: str | re.Pattern,
        timeout: float | None = None,
    ) -> tuple[str, re.Match | None]:
        """Block until pattern appears in SSH output or timeout."""
        if self._channel is None:
            raise ConnectionError("Not connected")

        if isinstance(pattern, str):
            regex = re.compile(pattern)
        else:
            regex = pattern

        effective_timeout = timeout or self.timeout
        deadline = time.monotonic() + effective_timeout

        while True:
            # Check unconsumed buffer for pattern (without advancing position)
            unconsumed = self._buffer.peek_unconsumed()
            match = regex.search(unconsumed)
            if match:
                # Consume everything up to current buffer end
                self._buffer.read_new(wait=False)
                return unconsumed, match

            if time.monotonic() >= deadline:
                # Timeout - return unconsumed data WITHOUT consuming it
                return unconsumed, None

            # Try to receive more data
            try:
                chunk = self._channel.recv(4096)
                if chunk:
                    text = chunk.decode("utf-8", errors="replace")
                    self._buffer.append(text)
                else:
                    self._state = ConnectionState.DISCONNECTED
                    raise ConnectionClosedError("SSH channel closed")
            except socket.timeout:
                pass

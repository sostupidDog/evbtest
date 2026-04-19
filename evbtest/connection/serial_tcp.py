"""Talent TCP serial port server connection."""

import re
import socket
import threading
import time
from typing import Optional

from evbtest.connection.base import ConnectionBase, ConnectionState
from evbtest.connection.exceptions import (
    ConnectionClosedError,
    ConnectionError,
)
from evbtest.connection.output_buffer import OutputBuffer


class SerialTCPConnection(ConnectionBase):
    """Raw TCP connection to a Talent serial port server (network-to-serial bridge).

    This is a transparent TCP socket -- bytes written go straight to the
    serial port, bytes arriving from the serial port appear on the socket.
    No protocol framing, no Telnet negotiation.

    A background reader thread continuously drains the socket into the output
    buffer, preventing the kernel TCP receive buffer from filling up and
    causing backpressure to the serial server.
    """

    def __init__(
        self,
        connection_id: str,
        host: str,
        port: int,
        timeout: float = 30.0,
    ):
        super().__init__(connection_id, timeout)
        self.host = host
        self.port = port
        self._socket: socket.socket | None = None
        self._buffer = OutputBuffer()
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def connect(self) -> None:
        """Establish TCP connection to serial port server."""
        self._state = ConnectionState.CONNECTING
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.host, self.port))
            self._socket.settimeout(0.1)

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
            raise ConnectionError(f"TCP serial connection failed: {e}") from e

    def _reader_loop(self) -> None:
        """Background thread: continuously read from TCP socket into buffer."""
        while not self._stop_event.is_set():
            try:
                data = self._socket.recv(4096)
                if not data:
                    # Connection closed by remote
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
        """Tear down TCP connection."""
        self._stop_event.set()
        self._buffer.close_session_log()
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=5.0)
        self._socket = None
        self._reader_thread = None
        self._state = ConnectionState.DISCONNECTED

    def send(self, data: bytes | str) -> None:
        """Send data over TCP socket."""
        if self._socket is None:
            raise ConnectionError("Not connected")
        if isinstance(data, str):
            self._buffer.log_send(data)
            data = data.encode("utf-8")
        else:
            self._buffer.log_send(data.decode("utf-8", errors="replace"))
        self._socket.sendall(data)

    def drain(self) -> None:
        """Discard any buffered output."""
        self._buffer.drain()

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
        so we just delegate to the buffer's wait_for_pattern method.
        """
        return self._buffer.wait_for_pattern(pattern, timeout=timeout or self.timeout)

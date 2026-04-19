"""High-level device interaction object for Python test authors."""

import logging
import time
from pathlib import Path

from evbtest.config.schema import DeviceConfig
from evbtest.connection.base import ConnectionBase
from evbtest.connection.ssh import SSHConnection
from evbtest.execution.executor import CommandExecutor, CommandResult


class DeviceHandle:
    """High-level device interaction object passed to Python test cases.

    Wraps a ConnectionBase + CommandExecutor and provides a fluent,
    convenient API for test authors.
    """

    def __init__(self, device_config: DeviceConfig, connection: ConnectionBase):
        self.config = device_config
        self._conn = connection
        self._executor = CommandExecutor(
            connection,
            default_prompt=device_config.prompt_pattern,
        )
        self._log = logging.getLogger(f"evbtest.device.{device_config.name}")
        # Drain stale output from connection init (MOTD, banner, etc.)
        connection.drain()

    @property
    def name(self) -> str:
        return self.config.name

    def execute(
        self,
        command: str,
        wait_for: str | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        """Send a command and wait for response (or custom pattern)."""
        self._log.info(f"$ {command}")
        result = self._executor.execute(command, wait_for=wait_for, timeout=timeout)
        if result.output:
            self._log.debug(f"Output: {result.output[:200]}")
        return result

    def wait_for(self, pattern: str, timeout: float = 60.0) -> CommandResult:
        """Wait for a pattern without sending anything."""
        self._log.info(f"Waiting for: {pattern}")
        result = self._executor.wait_for(pattern, timeout=timeout)
        self._log.info(f"Matched in {result.elapsed:.1f}s")
        return result

    def wait_for_any(
        self, patterns: list[str], timeout: float = 60.0
    ) -> tuple[CommandResult, int]:
        """Wait for any of several patterns. Returns (result, matched_index)."""
        self._log.info(f"Waiting for any of: {patterns}")
        result, idx = self._executor.wait_for_any(patterns, timeout=timeout)
        if idx >= 0:
            self._log.info(
                f"Matched pattern #{idx} ({patterns[idx]}) in {result.elapsed:.1f}s"
            )
        return result, idx

    def send_raw(self, data: bytes | str) -> None:
        """Send raw data. For Ctrl-C, special sequences."""
        self._log.info(f"Sending raw: {data!r}")
        self._executor.execute_raw(data)

    def send_line(self, text: str) -> None:
        """Send text + newline without waiting."""
        self._log.info(f">> {text}")
        self._executor.send_line(text)

    def interrupt_uboot(
        self,
        interrupt_char: str = "\x03",
        boot_pattern: str = "Hit any key",
        prompt_pattern: str = "=>",
        timeout: float = 30.0,
    ) -> None:
        """Convenience: detect U-Boot autoboot message and interrupt it."""
        self._log.info("Waiting for U-Boot autoboot prompt...")
        self.wait_for(boot_pattern, timeout=timeout)
        self.send_raw(interrupt_char)
        self.wait_for(prompt_pattern, timeout=5.0)
        self._log.info("U-Boot interrupted, at prompt")

    def flash_via_tftp(
        self,
        server_ip: str,
        image_name: str,
        load_addr: str = "0x80000000",
        flash_cmd: str | None = None,
        timeout: float = 180.0,
    ) -> CommandResult:
        """Convenience: TFTP download + optional flash command."""
        self.execute(f"setenv serverip {server_ip}")
        self.execute(f"tftpboot {load_addr} {image_name}", timeout=timeout)
        if flash_cmd:
            return self.execute(flash_cmd, timeout=timeout)
        return self.execute("bootm", timeout=timeout)

    def boot_and_login(
        self,
        login_prompt: str = "login:",
        username: str = "root",
        shell_prompt: str = "#",
        boot_timeout: float = 120.0,
    ) -> None:
        """Convenience: wait for boot, then login."""
        self.wait_for(login_prompt, timeout=boot_timeout)
        self.execute(username, wait_for=shell_prompt)

    def upload(
        self,
        local_path: str,
        remote_path: str,
        timeout: float = 300.0,
    ) -> None:
        """Upload a file to the device.

        SSH connections use SFTP. Serial connections are not supported
        (use flash_via_tftp or TFTP commands instead).
        """
        if not isinstance(self._conn, SSHConnection):
            raise RuntimeError(
                "File upload requires SSH connection. "
                "For serial connections, use TFTP (flash_via_tftp) instead."
            )
        if self._conn._client is None:
            raise RuntimeError("SSH not connected")

        self._log.info(f"Uploading {local_path} -> {remote_path}")
        start = time.monotonic()

        sftp = self._conn._client.open_sftp()
        try:
            sftp.put(local_path, remote_path)
            elapsed = time.monotonic() - start
            self._log.info(f"Upload complete ({elapsed:.1f}s)")
            self._conn.log_command_block(
                f"<upload: {local_path} -> {remote_path}>",
                f"Uploaded in {elapsed:.1f}s",
            )
        finally:
            sftp.close()

    def download(
        self,
        remote_path: str,
        local_path: str,
        timeout: float = 300.0,
    ) -> None:
        """Download a file from the device.

        SSH connections use SFTP. Serial connections are not supported.
        """
        if not isinstance(self._conn, SSHConnection):
            raise RuntimeError(
                "File download requires SSH connection. "
                "For serial connections, use TFTP instead."
            )
        if self._conn._client is None:
            raise RuntimeError("SSH not connected")

        self._log.info(f"Downloading {remote_path} -> {local_path}")
        start = time.monotonic()

        # Ensure local directory exists
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)

        sftp = self._conn._client.open_sftp()
        try:
            sftp.get(remote_path, local_path)
            elapsed = time.monotonic() - start
            self._log.info(f"Download complete ({elapsed:.1f}s)")
            self._conn.log_command_block(
                f"<download: {remote_path} -> {local_path}>",
                f"Downloaded in {elapsed:.1f}s",
            )
        finally:
            sftp.close()

    def reboot(
        self,
        wait_for: str | None = None,
        timeout: float = 120.0,
        disconnect_wait: float = 30.0,
    ) -> CommandResult:
        """Send reboot command, wait for disconnect, reconnect, wait for prompt.

        Flow:
          1. Send 'reboot' (fire-and-forget)
          2. Wait for connection to drop (up to disconnect_wait seconds)
          3. Reconnect (with retry)
          4. Wait for wait_for pattern or shell prompt (device boot complete)

        For SSH connections, the shell prompt is typically available immediately
        after reconnect (no login prompt). For serial connections, wait_for
        defaults to the device's login_prompt config.

        Args:
            wait_for: Pattern to wait for after reconnect. None = auto-detect
                      (use login_prompt from device config, or prompt_pattern
                      for SSH).
            timeout: Total timeout for reconnect + boot wait.
            disconnect_wait: How long to wait for connection to drop.

        Returns the result of the final wait_for.
        """
        self._log.info("Rebooting device...")

        # Determine what to wait for after reconnect
        if wait_for is None:
            wait_for = self.config.login_prompt
            # SSH connections get a shell directly, use prompt_pattern instead
            if isinstance(self._conn, SSHConnection):
                wait_for = self.config.prompt_pattern

        # Send reboot command — fire-and-forget since connection will drop
        self._executor.execute("reboot", wait_for="", timeout=5.0)

        # Wait for connection to drop
        self._log.info("Waiting for connection to drop...")
        drop_start = time.monotonic()
        while time.monotonic() - drop_start < disconnect_wait:
            if not self._conn.is_connected():
                self._log.info("Connection dropped")
                break
            time.sleep(0.5)
        else:
            self._log.warning(
                f"Connection did not drop within {disconnect_wait}s, "
                "proceeding with reconnect attempt"
            )

        # Reconnect with retry — device may still be booting
        self._log.info("Reconnecting...")
        reconnect_deadline = time.monotonic() + timeout
        retry_delay = 3.0
        last_err = None
        while time.monotonic() < reconnect_deadline:
            time.sleep(retry_delay)
            try:
                self._conn.connect()
                self._log.info("Reconnected")
                break
            except Exception as e:
                last_err = e
                self._log.debug(f"Reconnect attempt failed: {e}, retrying...")
        else:
            raise RuntimeError(
                f"Failed to reconnect after reboot within {timeout}s: {last_err}"
            )

        # Re-init executor (new connection)
        self._executor = CommandExecutor(
            self._conn,
            default_prompt=self.config.prompt_pattern,
        )
        # Drain any stale output from reconnect
        self._conn.drain()

        # Wait for device to be ready
        self._log.info(f"Waiting for device ready: '{wait_for}'")
        result = self.wait_for(wait_for, timeout=timeout)
        self._log.info(f"Device ready after reboot ({result.elapsed:.1f}s)")
        return result

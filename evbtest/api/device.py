"""High-level device interaction object for Python test authors."""

import logging

from evbtest.config.schema import DeviceConfig
from evbtest.connection.base import ConnectionBase
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

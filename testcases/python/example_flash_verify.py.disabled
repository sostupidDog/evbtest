"""Example Python test case: Flash firmware and verify with custom logic."""

import re

from evbtest.api import TestCase


class FirmwareFlashVerifyTest(TestCase):
    """Flash firmware via TFTP in U-Boot, boot, verify version and drivers."""

    name = "firmware_flash_verify_python"
    description = "Full firmware flash + boot + verification (Python API)"
    tags = ["flash", "firmware", "full-verification"]

    def setup(self):
        self.firmware_version = "v2.1"
        self.server_ip = "192.168.1.100"
        self.image_name = "firmware_v2.1.bin"

    def run(self):
        dev = self.device

        # Phase 1: Interrupt U-Boot
        dev.interrupt_uboot(
            boot_pattern="Hit any key to stop autoboot",
            prompt_pattern="=>",
            timeout=30,
        )

        # Phase 2: Configure TFTP and download
        dev.execute(f"setenv serverip {self.server_ip}", wait_for="=>")
        result = dev.execute(
            f"tftpboot 0x80000000 {self.image_name}",
            wait_for="Bytes transferred",
            timeout=120,
        )
        # Parse the transfer size from output
        size_match = re.search(r"Bytes transferred = (\d+)", result.output)
        assert size_match, f"TFTP download failed: {result.output}"
        image_size = int(size_match.group(1))
        assert image_size > 100000, f"Suspicious image size: {image_size}"

        # Phase 3: Flash to NAND
        dev.execute(
            "nand write.raw.noskip 0x80000000 0x0 0x400000",
            wait_for="=>",
            timeout=180,
        )

        # Phase 4: Boot
        dev.send_line("boot")
        result = dev.wait_for("Linux version", timeout=120)
        assert result.success, "Kernel did not boot"

        dev.wait_for("login:", timeout=60)
        dev.execute("root", wait_for="#")

        # Phase 5: Verify firmware version
        result = dev.execute("cat /etc/firmware-version")
        assert self.firmware_version in result.output, (
            f"Expected {self.firmware_version}, got: {result.output}"
        )

        # Phase 6: Verify kernel driver loaded
        result = dev.execute("lsmod")
        assert "my_driver" in result.output, "Driver not loaded"

        # Phase 7: Run driver self-test
        result = dev.execute("my_driver_test --all", timeout=60)
        assert "PASS" in result.output and "FAIL" not in result.output, (
            f"Driver self-test failed: {result.output}"
        )

    def teardown(self):
        """Ensure clean state even if test failed."""
        try:
            self.device.send_raw(b"\x03")  # Ctrl-C
            self.device.execute("", wait_for="#", timeout=5)
        except Exception:
            pass  # Best effort

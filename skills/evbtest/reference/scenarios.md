# Common Test Scenarios

## Kernel Replace + Rollback

```python
from evbtest.api import TestCase

class KernelReplace(TestCase):
    name = "kernel_replace"
    old_kernel = None

    def setup(self):
        r = self.device.execute("uname -r")
        self.old_kernel = r.output.strip()

    def run(self):
        d = self.device

        # Backup current kernel
        d.execute("cp /boot/zImage /boot/zImage.bak")

        # Upload new kernel (SSH)
        d.upload("/local/new_kernel.bin", "/boot/zImage")

        # Reboot with auto-reconnect
        d.reboot(timeout=120)

        # Verify new kernel
        r = d.execute("uname -r")
        assert "new_version" in r.output, f"Wrong kernel: {r.output}"

    def teardown(self):
        # Cleanup backup
        self.device.execute("rm -f /boot/zImage.bak", timeout=5)
```

## Firmware Flash via U-Boot (Serial)

```python
class UbootFlash(TestCase):
    name = "uboot_flash"

    def run(self):
        d = self.device

        # Interrupt U-Boot
        d.interrupt_uboot(timeout=30)

        # TFTP download + flash
        d.flash_via_tftp("192.168.1.100", "firmware_v2.bin", load_addr="0x80000000")

        # Boot into new firmware
        d.boot_and_login(boot_timeout=120)

        # Verify
        r = d.execute("cat /etc/version")
        assert "v2" in r.output
```

## Dual-Channel: Serial Monitor + SSH Control

```python
class DualMonitor(TestCase):
    name = "dual_monitor"
    use_secondary = True

    def run(self):
        ssh = self.device
        serial = self.secondary_device

        # Start kernel log on serial
        serial.send_line("dmesg -w")

        # Trigger action via SSH
        ssh.execute("echo test > /proc/driver/test")

        # Verify on serial
        r = serial.wait_for("driver: test received", timeout=10)
        assert r.success, f"Driver did not receive: {r.output}"
```

## Preflight Check Before Tests

```yaml
# testcases/yaml/preflight.yaml
preflight:
  settings:
    default_timeout: 10
  steps:
    - name: "check_firmware_uploaded"
      send: "ls /tmp/firmware.bin"
      wait_for: "firmware.bin"
    - name: "check_tftp_server"
      send: "ping -c 1 192.168.1.100"
      wait_for: "1 received"
    - name: "check_no_stale_process"
      send: "pgrep stale_daemon"
      expect_not: "\\d+"
```

```bash
evb-test run --preflight testcases/yaml/preflight.yaml
```

## Driver Stress Test with Negative Assertion

```yaml
test:
  name: "driver_stress"
  settings:
    default_timeout: 30
  phases:
    - name: "load_driver"
      steps:
        - name: "insmod"
          send: "insmod my_driver.ko"
          wait_for: "my_driver loaded"

    - name: "stress"
      steps:
        - name: "run_stress_1000_iters"
          send: "./stress_test.sh -n 1000"
          wait_for: "All done"
          expect_not: "fail|FAIL|error|panic|Oops"

    - name: "unload"
      steps:
        - name: "rmmod"
          send: "rmmod my_driver"
          wait_for: "my_driver unloaded"
```

## Multi-Device Parallel Test

Configure multiple devices in `configs/devices.yaml`, then:

```bash
# Run same tests on all devices in parallel
evb-test run

# Run on specific device
evb-test run -D evb_board_1
```

Each device gets its own connection. Tests on different devices run in parallel; tests on the same device run sequentially.

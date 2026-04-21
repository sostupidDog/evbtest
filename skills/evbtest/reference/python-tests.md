# Writing Python Test Cases

File location: `testcases/python/*.py`

## Basic Structure

```python
from evbtest.api import TestCase

class MyTest(TestCase):
    name = "my_test"
    tags = ["smoke"]

    def run(self):
        d = self.device
        r = d.execute("uname -a")
        assert "Linux" in r.output

    def setup(self):
        """Optional, called before run()"""

    def teardown(self):
        """Optional, called after run() even on failure"""
```

## TestCase Class Attributes

| Attribute | Default | Description |
|-----------|---------|-------------|
| `name` | class name | Test name shown in results |
| `tags` | `[]` | String list for filtering |
| `use_secondary` | `False` | Request secondary connection for dual-channel |

## DeviceHandle API

### Command Execution

```python
# Execute command, wait for shell prompt, return output
r = d.execute("uname -a")
# r.output  → str, cleaned output (ANSI stripped, echo removed)
# r.success → bool
# r.match   → re.Match object or None
# r.elapsed → float, seconds

# Execute with custom wait pattern
r = d.execute("free -h", wait_for="Mem:", timeout=10)

# Fire-and-forget (no wait)
d.send_line("background_cmd &")

# Send raw bytes (Ctrl-C, special keys)
d.send_raw("\x03")
```

### Waiting

```python
# Wait for pattern without sending
r = d.wait_for("login:", timeout=120)

# Wait for first match from multiple patterns
r, idx = d.wait_for_any(["login:", "Kernel panic", "Call trace"], timeout=120)
if idx == 0:
    print("Boot OK")
elif idx == 1:
    print("Kernel panic!")
```

### File Transfer (SSH only)

```python
# Upload local file to device
d.upload("/local/firmware.bin", "/tmp/firmware.bin")

# Download file from device
d.download("/var/log/kern.log", "/local/kern.log")

# Serial connections: use TFTP instead
d.flash_via_tftp("192.168.1.100", "firmware.bin")
```

### Reboot with Auto-Reconnect

```python
# Reboot, wait for disconnect, reconnect with retry
# SSH: auto-detects shell prompt
# Serial: waits for login_prompt
d.reboot(timeout=120)

# After reboot, device is ready for commands
r = d.execute("uname -r")
```

### U-Boot Convenience Methods

```python
# Interrupt U-Boot autoboot
d.interrupt_uboot(timeout=30)

# TFTP download + flash
d.flash_via_tftp("192.168.1.100", "firmware.bin", load_addr="0x80000000")

# Wait for boot then login
d.boot_and_login(boot_timeout=120)
```

### Dual-Channel

```python
class DualTest(TestCase):
    name = "dual_test"
    use_secondary = True

    def run(self):
        ssh = self.device               # Primary (SSH)
        serial = self.secondary_device   # Secondary (serial)

        # Monitor serial while executing SSH commands
        serial.execute("dmesg -w &")
        ssh.execute("reboot")
        serial.wait_for("login:", timeout=120)
```

## CommandResult

| Field | Type | Description |
|-------|------|-------------|
| `output` | str | Cleaned output (ANSI stripped, echo removed) |
| `success` | bool | Whether pattern matched |
| `match` | re.Match or None | Regex match object |
| `elapsed` | float | Execution time in seconds |

## Multiple Tests in One File

A single `.py` file can define multiple TestCase subclasses. Each gets its own task, result, and session log:

```python
from evbtest.api import TestCase

class TestKernel(TestCase):
    name = "kernel_check"
    def run(self):
        r = self.device.execute("uname -r")
        assert "5.10" in r.output

class TestMemory(TestCase):
    name = "memory_check"
    def run(self):
        r = self.device.execute("free -h")
        assert "Mem:" in r.output
```

## Important Notes

- `assert` or raise exceptions to indicate failure
- Normal return from `run()` = PASS
- `teardown()` always runs, even on failure
- `self.device` is a DeviceHandle, auto-injected by framework
- `prompt_pattern` in device config controls how framework detects command completion

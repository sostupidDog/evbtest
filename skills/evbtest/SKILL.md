---
name: evbtest
description: Use when the user asks to write/run device tests, test firmware, test kernel drivers, SSH tests, serial tests, or mentions "evb-test" / "evbtest". Use for automating commands on remote devices via SSH or serial console.
version: 0.4.0
---

# evbtest — Remote Device Test Framework

Automate testing on remote devices via SSH or Talent TCP serial port server.

## Setup

```bash
pip install -e .
evb-test init                              # Create configs/, testcases/, logs/
evb-test list-devices                      # Verify device config
```

## CLI Commands

```bash
evb-test run                               # Run all tests in testcases/
evb-test run -D <device>                   # Run on specific device only
evb-test run -t <path>                     # Run specific test file or directory
evb-test run --no-log                      # Disable session log files
evb-test run -x                            # Stop on first failure
evb-test run --preflight <file>            # Preflight env check (skip tests on failure)
evb-test connect <device>                  # Interactive debug session
evb-test check <test.yaml>                 # Validate YAML syntax
```

## Device Config (`configs/devices.yaml`)

```yaml
devices:
  my_server:
    description: "Linux server"
    connection:
      type: ssh                 # or: serial_tcp
      host: 192.168.1.10
      port: 22
      username: root
      password: "secret"
    prompt_pattern: "[#\\$]\\s*$"

  my_board:
    description: "ARM64 board"
    connection:
      type: serial_tcp
      host: 192.168.1.200
      port: 5001
    prompt_pattern: "[#\\$>]\\s*$"
    uboot_prompt: "=>"
```

## Writing Tests

### YAML (`testcases/yaml/*.yaml`)

```yaml
test:
  name: "smoke"
  device: "my_server"
  settings:
    default_timeout: 10
  phases:
    - name: "checks"
      steps:
        - name: "check_os"
          send: "uname -a"
          wait_for: "GNU/Linux"
        - name: "check_uptime"
          send: "uptime"
          wait_for: "load average"
        - name: "send_ctrl_c"
          send_raw: "\x03"
          wait_for: "=>"
```

Step fields: `send`, `send_raw`, `wait_for` (regex, must match), `expect` (extra positive assertion), `expect_not` (negative assertion — output must NOT contain), `timeout`, `on_timeout` (fail|continue), `delay_before`, `delay_after`.

### Preflight Checks

Run environment checks before all tests per device. If any step fails, all tests for that device are skipped.

```yaml
preflight:
  settings:
    default_timeout: 10
  steps:
    - name: "check_file"
      send: "ls /tmp/firmware.bin"
      wait_for: "firmware.bin"
```

```bash
evb-test run --preflight testcases/yaml/preflight.yaml
```

### Python (`testcases/python/*.py`)

```python
from evbtest.api import TestCase

class MyTest(TestCase):
    name = "my_test"

    def run(self):
        d = self.device

        r = d.execute("uname -a")
        assert "Linux" in r.output

        r = d.execute("free -h", wait_for="Mem:", timeout=10)

        d.wait_for("login:", timeout=120)     # Watch output
        d.send_raw("\x03")                    # Ctrl-C
        d.send_line("cmd &")                  # Fire-and-forget
        d.interrupt_uboot()                   # U-Boot convenience
        d.flash_via_tftp(server, image)       # TFTP flash
        d.boot_and_login()                    # Boot + login
        d.upload("/local/file", "/remote/file")  # SFTP upload (SSH only)
        d.download("/remote/file", "/local/file")  # SFTP download (SSH only)
        d.reboot(timeout=120)                 # Reboot + auto-reconnect

    def setup(self):    ...                   # Optional
    def teardown(self): ...                   # Optional, runs on failure too
```

### Dual-Channel (SSH + Serial on same device)

Add `secondary_connection` to device config, set `use_secondary = True` on test:

```yaml
devices:
  my_board:
    connection:
      type: ssh
      host: 192.168.1.10
      username: root
      password: "secret"
    secondary_connection:
      type: serial_tcp
      host: 192.168.1.200
      port: 5001
```

```python
class DualTest(TestCase):
    name = "dual_test"
    use_secondary = True

    def run(self):
        ssh = self.device              # Primary (SSH)
        serial = self.secondary_device  # Secondary (serial)
        serial.execute("dmesg -w &")
        ssh.execute("reboot")
        serial.wait_for("login:", timeout=120)
```

## Session Logs

Per-test log files in `logs/<timestamp>/`. Each command captured as `[time] >>> command` followed by full output. Disable with `--no-log`.

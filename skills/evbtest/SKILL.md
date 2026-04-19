---
name: evbtest
description: Use this skill when the user asks to "write device tests", "run evb-test", "test firmware", "test kernel driver", "SSH test", "serial port test", "remote command test", mentions "evb-test" or "evbtest", or needs to automate testing on remote devices via SSH or serial console. Also use when creating test cases for embedded systems, firmware verification, or device bring-up.
version: 0.1.0
---

# evbtest — Remote Device Test Framework

Automate testing on remote devices via SSH or Talent TCP serial port server. Write tests in YAML (declarative) or Python (programmatic), run them across multiple devices in parallel.

## Project Setup

```bash
# Install framework
pip install -e .

# Initialize project directories
evb-test init

# Verify devices are configured
evb-test list-devices
```

Dependencies: `paramiko`, `pyyaml`, `click`, `rich` (installed automatically).

## Quick Reference: CLI Commands

```bash
# Run all tests on all devices
evb-test run -d configs/devices.yaml -t testcases/

# Run specific test on specific device
evb-test run -d configs/devices.yaml -t testcases/yaml/my_test.yaml -D device_name

# Run tests tagged "smoke"
evb-test run --tags smoke

# Interactive debugging session to a device
evb-test connect device_name

# Validate YAML test case syntax
evb-test check testcases/yaml/my_test.yaml

# Initialize project structure
evb-test init

# List configured devices
evb-test list-devices
```

## Configuration: Device Definitions

File: `configs/devices.yaml`

```yaml
devices:
  my_board:
    description: "Description"
    tags: ["arm64", "flash-capable"]
    connection:
      type: serial_tcp          # or: ssh
      host: 192.168.1.200
      port: 5001
      timeout: 30.0
    prompt_pattern: "[#\\$>]\\s*$"
    uboot_prompt: "=>"
    login_prompt: "login:"
    env:
      TFTP_SERVER: "192.168.1.100"

  my_server:
    description: "Linux server"
    tags: ["x86"]
    connection:
      type: ssh
      host: 192.168.1.10
      port: 22
      username: root
      password: "secret"        # or use key_filename
      # key_filename: ~/.ssh/id_rsa
    prompt_pattern: "[#\\$]\\s*$"
```

**Connection types:**
- `serial_tcp`: Talent network-to-serial converter. Raw TCP to IP:port, no protocol framing.
- `ssh`: SSH via paramiko. Uses `invoke_shell` for persistent terminal session.

## Writing Tests: YAML Format

File location: `testcases/yaml/*.yaml`

```yaml
test:
  name: "test_identifier"
  description: "What this test does"
  tags: ["smoke", "firmware"]
  device: "device_name"          # Target device from devices.yaml

  settings:
    default_timeout: 30          # Default step timeout (seconds)
    fail_fast: true              # Stop on first failure

  phases:
    - name: "phase_name"
      steps:
        - name: "step_description"
          send: "command"              # Send command + newline
          # OR: send_raw: "\x03"       # Send raw bytes (Ctrl-C)
          # OR: send_no_newline: "x"   # Send without newline
          wait_for: "regex_pattern"    # Wait for regex match
          expect: "regex_pattern"      # Additional assertion on output
          timeout: 30                  # Override timeout (seconds)
          on_timeout: "fail"           # "fail" | "continue" | "skip_rest"
          delay_before: 0.5           # Sleep before sending
          delay_after: 0.5            # Sleep after matching
```

**Step execution flow:** For each step, the runner sends the command, then waits for `wait_for` pattern. If `expect` is set, it additionally verifies that pattern appears in output. Steps run sequentially within each phase.

**Pattern matching:** All `wait_for` and `expect` values are Python regex. Use `(?i)` for case-insensitive matching. Example: `wait_for: "(?i)linux"`.

**Fire-and-forget:** Omit `wait_for` to skip waiting for response.

## Writing Tests: Python API

File location: `testcases/python/*.py`

```python
from evbtest.api import TestCase

class MyTest(TestCase):
    name = "my_test"
    tags = ["smoke"]

    def run(self):
        d = self.device                    # DeviceHandle instance

        # Execute command, wait for default prompt
        r = d.execute("uname -a")
        assert "Linux" in r.output

        # Execute with custom wait pattern
        r = d.execute("uptime", wait_for="load average", timeout=10)

        # Wait without sending (watch output)
        r = d.wait_for("login:", timeout=120)

        # Send raw bytes (Ctrl-C, escape sequences)
        d.send_raw("\x03")

        # Fire-and-forget
        d.send_line("some command")

        # Convenience: interrupt U-Boot
        d.interrupt_uboot(timeout=30)

        # Convenience: TFTP flash
        d.flash_via_tftp("192.168.1.100", "firmware.bin", timeout=180)

        # Convenience: boot and login
        d.boot_and_login(boot_timeout=120)

    def setup(self):
        """Optional: called before run()"""

    def teardown(self):
        """Optional: called after run(), even on failure"""
```

### DeviceHandle API Reference

| Method | Description |
|--------|-------------|
| `execute(cmd, wait_for=None, timeout=None) -> CommandResult` | Send command, wait for response |
| `wait_for(pattern, timeout=60) -> CommandResult` | Wait for pattern without sending |
| `wait_for_any(patterns, timeout=60) -> (CommandResult, int)` | Wait for first matching pattern |
| `send_raw(data)` | Send raw bytes/str |
| `send_line(text)` | Send text + newline, no wait |
| `interrupt_uboot(...)` | Detect and interrupt U-Boot autoboot |
| `flash_via_tftp(server, image, ...)` | TFTP download + flash |
| `boot_and_login(...)` | Wait for boot, then login |

### CommandResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `output` | `str` | Cleaned command output (ANSI stripped, echo removed) |
| `success` | `bool` | Whether pattern matched |
| `match` | `re.Match \| None` | Regex match object |
| `elapsed` | `float` | Execution time in seconds |
| `command` | `str` | The command that was sent |

## Framework Architecture

```
evbtest/
├── config/          # Device/test config loading (YAML)
├── connection/      # SSH + TCP serial transports
│   ├── base.py      # ConnectionBase ABC
│   ├── ssh.py       # paramiko invoke_shell
│   ├── serial_tcp.py # Raw TCP socket + reader thread
│   └── output_buffer.py # Thread-safe buffer with regex matching
├── execution/       # Command execution engine
│   ├── executor.py  # CommandExecutor: send/wait/strip echo
│   └── sequence.py  # Multi-step command sequences
├── api/             # User-facing API
│   ├── device.py    # DeviceHandle (high-level)
│   └── testcase.py  # TestCase base class
├── runner/          # Test discovery and execution
│   ├── yaml_runner.py   # YAML test interpreter
│   ├── python_runner.py # Python test loader
│   └── parallel.py      # asyncio multi-device runner
├── reporting/       # Output formatting
│   ├── result.py    # Result dataclasses
│   └── logger.py    # Rich terminal output
└── cli.py           # Click CLI (evb-test command)
```

## Common Test Patterns

### Pattern 1: U-Boot Firmware Flash

```yaml
phases:
  - name: "interrupt_uboot"
    steps:
      - name: "wait_autoboot"
        wait_for: "Hit any key to stop autoboot"
        timeout: 30
      - name: "interrupt"
        send_raw: "\x03"
        wait_for: "=>"

  - name: "flash"
    steps:
      - name: "tftp"
        send: "tftpboot 0x80000000 firmware.bin"
        wait_for: "Bytes transferred"
        timeout: 120
      - name: "write"
        send: "nand write 0x80000000 0x0 0x400000"
        wait_for: "=>"
        timeout: 180

  - name: "boot_verify"
    steps:
      - name: "boot"
        send: "boot"
        wait_for: "Linux version"
        timeout: 120
      - name: "login"
        wait_for: "login:"
        timeout: 60
      - name: "check_version"
        send: "cat /etc/firmware-version"
        expect: "v2\\.1"
```

### Pattern 2: Kernel Driver Validation

```python
class DriverTest(TestCase):
    name = "driver_validation"
    tags = ["driver"]

    def run(self):
        d = self.device
        d.execute("insmod my_driver.ko")
        r = d.execute("lsmod")
        assert "my_driver" in r.output, f"Driver not loaded: {r.output}"

        r = d.execute("dmesg | tail -5")
        assert "initialized" in r.output

        r = d.execute("my_driver_test --all", timeout=60)
        assert "PASS" in r.output, f"Self-test failed: {r.output}"
```

### Pattern 3: SSH Server Smoke Test

```yaml
test:
  name: "ssh_smoke"
  device: "my_server"
  settings:
    default_timeout: 10
  phases:
    - name: "basic"
      steps:
        - send: "uname -a"
          wait_for: "GNU/Linux"
        - send: "hostname"
          wait_for: ".+"         # Match any non-empty output
        - send: "uptime"
          wait_for: "load average"
        - send: "free -h"
          wait_for: "Mem:"
```

## Key Implementation Details

1. **SSH uses `invoke_shell`** not `exec_command` — maintains persistent session across multi-step flows
2. **TCP serial has background reader thread** — continuously drains socket to prevent buffer overflow
3. **OutputBuffer is thread-safe** — uses `threading.Condition` for blocking pattern waits
4. **ANSI escape codes are stripped** from executor output for clean matching
5. **Drain before send** — executor drains stale buffer data before each new command to prevent stale matches
6. **Parallel execution** — uses `asyncio.run_in_executor` with thread pool for blocking I/O connections

## Tips for Writing Good Tests

- **Be specific with patterns**: `wait_for: "Bytes transferred"` is better than `wait_for: "Bytes"`
- **Use case-insensitive matching** when needed: `wait_for: "(?i)linux"`
- **Set generous timeouts** for boot operations (60-180s)
- **Use `send_raw`** for control characters: `send_raw: "\x03"` for Ctrl-C
- **Use `on_timeout: "continue"`** for optional steps
- **Put teardown in `teardown()`** — it runs even if `run()` throws
- **Strip echo is on by default** — the echoed command line is removed from output
- **Use `evb-test connect <device>`** for interactive debugging before writing tests

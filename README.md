# evb-test

Lightweight Python framework for automated testing on remote devices via SSH or Talent TCP serial.

## Features

- **YAML + Python test formats** — Declarative YAML for common scenarios, Python for complex logic
- **SSH & Serial TCP** — Connect via SSH or Talent network-to-serial converter
- **Multi-device parallel** — Run tests across multiple devices concurrently
- **Connection pooling & auto-reconnect** — Reuses connections across tests, auto-recovers from drops
- **Session logging** — Per-test log files capturing all device I/O for post-analysis
- **Rich CLI output** — Real-time progress, result tables, failure details

## Install

```bash
pip install -e .
```

Requires Python >= 3.10.

## Quick Start

### 1. Initialize project

```bash
evb-test init
```

Creates `configs/`, `testcases/yaml/`, `testcases/python/`, `logs/`.

### 2. Configure devices

Edit `configs/devices.yaml`:

```yaml
devices:
  my_board:
    description: "ARM64 board via serial"
    tags: ["arm64"]
    connection:
      type: serial_tcp          # or: ssh
      host: 192.168.1.200
      port: 5001
    prompt_pattern: "[#\\$>]\\s*$"
    uboot_prompt: "=>"
    login_prompt: "login:"

  my_server:
    description: "Linux server via SSH"
    tags: ["x86"]
    connection:
      type: ssh
      host: 192.168.1.10
      port: 22
      username: root
      password: "secret"        # or: key_filename: ~/.ssh/id_rsa
    prompt_pattern: "[#\\$]\\s*$"
```

### 3. Write a YAML test

Create `testcases/yaml/smoke.yaml`:

```yaml
test:
  name: "smoke_test"
  device: "my_server"
  settings:
    default_timeout: 10
  phases:
    - name: "basic"
      steps:
        - name: "check_os"
          send: "uname -a"
          wait_for: "GNU/Linux"
        - name: "check_uptime"
          send: "uptime"
          wait_for: "load average"
        - name: "check_memory"
          send: "free -h"
          wait_for: "Mem:"
```

### 4. Run

```bash
# Default: run all tests in testcases/ on all devices
evb-test run

# Specific device
evb-test run -D my_server

# Specific test file
evb-test run -t testcases/yaml/smoke.yaml

# Disable session logs
evb-test run --no-log

# Interactive debug session
evb-test connect my_server

# Validate YAML syntax without running
evb-test check testcases/yaml/smoke.yaml

# List configured devices
evb-test list-devices
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `evb-test run` | Run test suite against configured devices |
| `evb-test connect <device>` | Open interactive session to a device |
| `evb-test list-devices` | List configured devices |
| `evb-test check <test.yaml>` | Validate YAML test case syntax |
| `evb-test init` | Initialize project directory |

### `run` options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--devices` | `-d` | `configs/devices.yaml` | Device config file |
| `--tests` | `-t` | `testcases/` | Test files or directories |
| `--device` | `-D` | all | Run only on this device |
| `--max-concurrent` | `-j` | 5 | Max parallel device connections |
| `--fail-fast` | `-x` | off | Stop on first failure |
| `--no-log` | | off | Disable session log files |
| `--output` | `-o` | `logs/` | Output directory |

## YAML Test Format

```yaml
test:
  name: "test_name"
  description: "What this test does"
  tags: ["tag1", "tag2"]
  device: "device_name"
  settings:
    default_timeout: 30
    fail_fast: true
  phases:
    - name: "phase_name"
      steps:
        - name: "step_name"
          send: "command"              # Send command + newline
          wait_for: "regex_pattern"    # Wait for regex match
          expect: "regex_pattern"      # Additional positive assertion
          expect_not: "regex_pattern"  # Negative assertion (must NOT appear)
          timeout: 30
          on_timeout: "fail"           # fail | continue
          delay_before: 0.5
          delay_after: 0.5
        - name: "raw_step"
          send_raw: "\x03"             # Send raw bytes (Ctrl-C)
```

**Key points:**
- `send` sends command + newline, then waits for prompt
- `wait_for` is a Python regex checked against command output
- `expect` is an additional positive regex assertion on output
- `expect_not` is a negative assertion — output must NOT contain this pattern
- Omit `wait_for` for fire-and-forget commands
- Use `(?i)` prefix for case-insensitive matching: `wait_for: "(?i)linux"`

**Three assertions explained:**

| Field | Direction | Use case |
|-------|-----------|----------|
| `wait_for` | must contain | Confirm command completed / keyword appeared |
| `expect` | must contain | Extra positive check (e.g. checksum ok) |
| `expect_not` | must NOT contain | Catch failures (e.g. "fail\|error\|panic") |

Example — multi-line results where any "fail" means the test failed:

```yaml
- name: "run_benchmark"
  send: "./run_benchmark.sh"
  wait_for: "All done"
  expect_not: "fail|FAIL|error"
```

## Python Test API

Create `testcases/python/my_test.py`:

```python
from evbtest.api import TestCase

class SmokeTest(TestCase):
    name = "smoke"
    tags = ["smoke"]

    def run(self):
        d = self.device

        r = d.execute("uname -a")
        assert "Linux" in r.output

        r = d.execute("free -h", wait_for="Mem:", timeout=10)

        r = d.wait_for("login:", timeout=120)   # Watch output without sending

        d.send_raw("\x03")                       # Ctrl-C
        d.send_line("background_cmd &")          # Fire-and-forget

        # Convenience methods
        d.interrupt_uboot(timeout=30)
        d.flash_via_tftp("192.168.1.100", "firmware.bin")
        d.boot_and_login(boot_timeout=120)

    def setup(self):
        """Optional pre-test setup"""

    def teardown(self):
        """Optional cleanup, runs even on failure"""
```

### DeviceHandle API

| Method | Returns | Description |
|--------|---------|-------------|
| `execute(cmd, wait_for, timeout)` | `CommandResult` | Send command, wait for response |
| `wait_for(pattern, timeout)` | `CommandResult` | Wait for pattern without sending |
| `wait_for_any(patterns, timeout)` | `(CommandResult, int)` | Wait for first match from list |
| `send_raw(data)` | — | Send raw bytes |
| `send_line(text)` | — | Send text + newline, no wait |
| `interrupt_uboot(...)` | — | Interrupt U-Boot autoboot |
| `flash_via_tftp(server, image, ...)` | `CommandResult` | TFTP download + flash |
| `boot_and_login(...)` | — | Wait for boot then login |

### CommandResult

| Field | Description |
|-------|-------------|
| `output` | Cleaned output (ANSI stripped, echo removed) |
| `success` | Whether pattern matched |
| `match` | Regex match object |
| `elapsed` | Execution time (seconds) |

## Session Logs

Each test generates a session log file capturing all command I/O:

```
logs/
└── 20260420_120000/
    ├── test_server_smoke_test.log
    ├── test_server_system_info.log
    └── evb_board_1_firmware_flash.log
```

Log format — each command as a clean block:

```
[12:00:01.234] >>> uname -a
Linux myboard 5.10.0-gnu
[root@board]#

[12:00:01.456] >>> free -h
              total   used   free
Mem:          1.8Gi   997Mi  113Mi
[root@board]#
```

## Architecture

```
evbtest/
├── cli.py               # Click CLI entry point
├── config/              # Device config loading
│   ├── schema.py        # DeviceConfig, SSHConfig, SerialTCPConfig
│   └── loader.py        # YAML config parser
├── connection/          # Transport layer
│   ├── base.py          # ConnectionBase ABC
│   ├── ssh.py           # SSH via paramiko invoke_shell + reader thread
│   ├── serial_tcp.py    # Raw TCP + background reader thread
│   ├── output_buffer.py # Thread-safe buffer, list-based, Condition wait
│   └── exceptions.py    # ConnectionError, PatternTimeoutError
├── execution/
│   ├── executor.py      # CommandExecutor: pre-compiled regex, drain-before-send
│   └── sequence.py      # Multi-step command sequences
├── api/
│   ├── device.py        # DeviceHandle
│   └── testcase.py      # TestCase base class
├── runner/
│   ├── yaml_runner.py   # YAML test interpreter
│   ├── python_runner.py # Python test loader
│   └── parallel.py      # asyncio runner, connection pool, auto-reconnect
└── reporting/
    ├── result.py        # Result dataclasses
    └── logger.py        # Rich terminal output
```

## Connection Types

### SSH (`type: ssh`)

Uses paramiko `invoke_shell()` for persistent terminal session. Background reader thread drains channel into OutputBuffer. Supports password and key-based auth.

### Talent Serial TCP (`type: serial_tcp`)

Raw TCP to a Talent network-to-serial converter. Background reader thread prevents buffer overflow. Baud rate is configured on the hardware side.

Both connection types use the same architecture: background reader thread + OutputBuffer with Condition variable for efficient blocking pattern matching.

## License

MIT

# evb-test

Lightweight Python test framework for remote server/device testing via SSH or Talent TCP serial port server.

## Features

- **Dual test formats** — YAML (declarative) for common scenarios, Python (programmatic) for complex logic
- **SSH & Serial TCP** — Connect via SSH or Talent network-to-serial converter
- **Multi-device parallel** — Run tests across multiple devices concurrently
- **Firmware test oriented** — U-Boot interaction, TFTP flashing, boot sequence, driver validation
- **Rich CLI output** — Colored terminal output with result tables
- **Minimal dependencies** — Only 4 required packages: paramiko, pyyaml, click, rich

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
    connection:
      type: serial_tcp
      host: 192.168.1.200
      port: 5001
    prompt_pattern: "[#\\$>]\\s*$"
    uboot_prompt: "=>"

  my_server:
    description: "Linux server via SSH"
    connection:
      type: ssh
      host: 192.168.1.10
      port: 22
      username: root
      password: "secret"
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
```

### 4. Run

```bash
# Run on specific device
evb-test run -d configs/devices.yaml -t testcases/yaml/smoke.yaml -D my_server

# Run all tests on all devices
evb-test run -d configs/devices.yaml -t testcases/

# Interactive debug session
evb-test connect my_server
```

## CLI Reference

```
evb-test run       Run test suite against configured devices
evb-test connect   Open interactive session to a device
evb-test list-devices  List configured devices
evb-test check     Validate YAML test case syntax
evb-test init      Initialize project directory
```

### `run` options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--devices` | `-d` | `configs/devices.yaml` | Device config file |
| `--tests` | `-t` | | Test files or directories (repeatable) |
| `--device` | `-D` | | Run only on this device |
| `--max-concurrent` | `-j` | 5 | Max parallel device connections |
| `--fail-fast` | `-x` | | Stop on first failure |

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
          send: "command string"
          wait_for: "regex_pattern"
          expect: "regex_pattern"        # Additional assertion
          timeout: 30
          on_timeout: "fail"             # fail | continue | skip_rest
          send_raw: "\x03"               # Raw bytes instead of send
          delay_before: 0.5
          delay_after: 0.5
```

- `send` — Send command + newline, then wait
- `send_raw` — Send raw bytes (Ctrl-C: `\x03`, etc.)
- `wait_for` — Python regex to match in output
- `expect` — Additional regex assertion on output
- Omit `wait_for` for fire-and-forget

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
        assert "Mem:" in r.output

    def setup(self):
        """Optional pre-test setup"""

    def teardown(self):
        """Optional cleanup, runs even on failure"""
```

### DeviceHandle API

| Method | Description |
|--------|-------------|
| `execute(cmd, wait_for, timeout)` | Send command, return `CommandResult` |
| `wait_for(pattern, timeout)` | Wait for pattern without sending |
| `wait_for_any(patterns, timeout)` | Wait for first match from list |
| `send_raw(data)` | Send raw bytes |
| `send_line(text)` | Send text + newline, no wait |
| `interrupt_uboot(...)` | Interrupt U-Boot autoboot |
| `flash_via_tftp(server, image, ...)` | TFTP download + flash |
| `boot_and_login(...)` | Wait for boot then login |

### CommandResult

| Field | Description |
|-------|-------------|
| `output` | Command output (ANSI stripped, echo removed) |
| `success` | Pattern matched |
| `elapsed` | Execution time (seconds) |
| `match` | Regex match object |

## Architecture

```
evbtest/
├── cli.py              # Click CLI entry point
├── config/             # Device & suite config loading
│   ├── schema.py       # Dataclasses: DeviceConfig, SSHConfig, SerialTCPConfig
│   └── loader.py       # YAML config parser
├── connection/         # Transport layer
│   ├── base.py         # ConnectionBase ABC
│   ├── ssh.py          # SSH via paramiko invoke_shell
│   ├── serial_tcp.py   # Raw TCP + background reader thread
│   ├── output_buffer.py # Thread-safe buffer with regex matching
│   └── exceptions.py   # ConnectionError, PatternTimeoutError
├── execution/          # Command execution engine
│   ├── executor.py     # CommandExecutor: send/wait/echo-strip
│   └── sequence.py     # Multi-step command sequences
├── api/                # User-facing Python API
│   ├── device.py       # DeviceHandle
│   └── testcase.py     # TestCase base class
├── runner/             # Test discovery & execution
│   ├── yaml_runner.py  # YAML test interpreter
│   ├── python_runner.py # Python test loader
│   └── parallel.py     # asyncio parallel runner
└── reporting/          # Output & results
    ├── result.py       # StepResult, TestResult, ParallelRunResult
    └── logger.py       # Rich terminal output
```

## Connection Types

### SSH (`type: ssh`)

Uses paramiko `invoke_shell()` for persistent terminal session. Supports password and key-based auth.

### Talent Serial TCP (`type: serial_tcp`)

Raw TCP connection to a Talent network-to-serial converter. A background reader thread continuously drains the socket to prevent buffer overflow. Baud rate is configured on the hardware side.

## License

MIT

# Writing YAML Test Cases

File location: `testcases/yaml/*.yaml`

## Basic Structure

```yaml
test:
  name: "test_name"
  description: "What this test does"
  tags: ["smoke", "kernel"]
  device: "my_server"          # Optional: override target device
  settings:
    default_timeout: 30
    fail_fast: true
  phases:
    - name: "phase_name"
      steps:
        - name: "step_name"
          send: "command"
          wait_for: "pattern"
```

## Step Fields

| Field | Type | Description |
|-------|------|-------------|
| `send` | string | Send command + newline |
| `send_raw` | string | Send raw bytes (e.g. `"\x03"` for Ctrl-C) |
| `wait_for` | regex | Must match in output (command completed) |
| `expect` | regex | Extra positive assertion (must contain) |
| `expect_not` | regex | Negative assertion (must NOT contain) |
| `timeout` | float | Seconds, overrides default_timeout |
| `on_timeout` | string | `fail` (default) or `continue` |
| `delay_before` | float | Wait seconds before executing step |
| `delay_after` | float | Wait seconds after step completes |

## Three Assertions

| Field | Direction | Use case |
|-------|-----------|----------|
| `wait_for` | must contain | Confirm command completed / keyword appeared |
| `expect` | must contain | Extra positive check (e.g. checksum ok) |
| `expect_not` | must NOT contain | Catch failures (e.g. `fail|error|panic`) |

## Examples

### Smoke Test

```yaml
test:
  name: "smoke_test"
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

### Multi-line Result with Negative Assertion

When a command outputs many lines, any "fail" means the test failed:

```yaml
- name: "run_benchmark"
  send: "./run_benchmark.sh"
  wait_for: "All done"
  expect_not: "fail|FAIL|error"
```

### Raw Sequence (Ctrl-C, U-Boot)

```yaml
- name: "send_ctrl_c"
  send_raw: "\x03"
  wait_for: "=>"
```

### Fire-and-forget Command

Omit `wait_for` to send without waiting:

```yaml
- name: "start_background_task"
  send: "long_running_cmd &"
```

### Continue on Timeout

```yaml
- name: "optional_check"
  send: "dmesg | grep uncommon_driver"
  wait_for: "uncommon_driver"
  timeout: 5
  on_timeout: "continue"
```

## Preflight Checks

Run environment checks before all tests per device. If any step fails, all tests for that device are marked SKIP.

```yaml
preflight:
  settings:
    default_timeout: 10
  steps:
    - name: "check_firmware_exists"
      send: "ls /tmp/firmware.bin"
      wait_for: "firmware.bin"
    - name: "check_no_stale_process"
      send: "pgrep stale_daemon"
      expect_not: "\\d+"
```

```bash
evb-test run --preflight testcases/yaml/preflight.yaml
```

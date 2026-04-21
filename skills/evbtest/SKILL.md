---
name: evbtest
description: Use when the user asks to write/run device tests, test firmware, test kernel drivers, SSH tests, serial tests, or mentions "evb-test" / "evbtest". Use for automating commands on remote devices via SSH or serial console.
version: 0.5.0
---

# evbtest — Remote Device Test Framework

Automate testing on remote devices via SSH or Talent TCP serial port server.

## Quick Start

```bash
pip install -e .
evb-test init                    # Create configs/, testcases/, logs/
evb-test list-devices            # Verify device config
evb-test run                     # Run all tests in testcases/
evb-test run -D <device>         # Run on specific device
evb-test run -t <path>           # Run specific test file or directory
evb-test run --preflight <file>  # Preflight env check
evb-test run -x                  # Stop on first failure
evb-test run --no-log            # Disable session logs
evb-test connect <device>        # Interactive debug session
evb-test check <test.yaml>       # Validate YAML syntax
```

## Reference Files

- `reference/device-config.md` — Device configuration (SSH, serial_tcp, dual-channel)
- `reference/yaml-tests.md` — How to write YAML test cases with all step fields
- `reference/python-tests.md` — How to write Python test cases with DeviceHandle API
- `reference/scenarios.md` — Common test scenarios (kernel replace, firmware flash, dual-channel)

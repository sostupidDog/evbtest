"""YAML test case runner."""

import logging
import re
import time
from pathlib import Path

import yaml

from evbtest.api.device import DeviceHandle
from evbtest.connection.exceptions import PatternTimeoutError
from evbtest.reporting.result import StepResult, TestResult


class YAMLTestCaseRunner:
    """Interpret and execute a YAML test case against a device."""

    def __init__(self, device: DeviceHandle):
        self._device = device
        self._log = logging.getLogger("evbtest.yaml_runner")

    def run_file(self, path: str) -> TestResult:
        """Load and execute a YAML test case file."""
        with open(path) as f:
            spec = yaml.safe_load(f)

        test_spec = spec.get("test", {})
        test_name = test_spec.get("name", Path(path).stem)
        settings = test_spec.get("settings", {})

        result = TestResult(device=self._device.name, test=test_name)
        result.status = "RUNNING"
        result.start_time = time.monotonic()

        try:
            for phase in test_spec.get("phases", []):
                phase_name = phase.get("name", "unnamed")
                self._log.info(f"Phase: {phase_name}")
                for step in phase.get("steps", []):
                    step_result = self._execute_step(step, settings)
                    result.add_step(step_result)
                    if not step_result.success:
                        if settings.get("fail_fast", True):
                            result.status = "FAIL"
                            result.end_time = time.monotonic()
                            return result
            result.status = "PASS"
        except Exception as e:
            self._log.error(f"Test error: {e}")
            result.status = "ERROR"
            result.error = str(e)
        finally:
            result.end_time = time.monotonic()

        return result

    def _execute_step(self, step: dict, settings: dict) -> StepResult:
        """Execute a single step from the YAML test case."""
        name = step.get("name", "unnamed")
        timeout = step.get("timeout", settings.get("default_timeout", 30))
        self._log.info(f"  Step: {name}")

        try:
            # Handle delay_before
            delay_before = step.get("delay_before", 0)
            if delay_before > 0:
                time.sleep(delay_before)

            # Handle delay_after
            delay_after = step.get("delay_after", 0)

            # Raw send (Ctrl-C, special sequences)
            if step.get("send_raw"):
                raw_data = step["send_raw"].encode("utf-8").decode("unicode_escape")
                self._device.send_raw(raw_data)
                if delay_after > 0:
                    time.sleep(delay_after)
                return StepResult(name=name, success=True)

            # Send without newline
            if step.get("send_no_newline"):
                self._device._conn.send(step["send_no_newline"])
                if delay_after > 0:
                    time.sleep(delay_after)
                return StepResult(name=name, success=True)

            # Standard send + wait_for: use executor for proper sequencing & logging
            if step.get("send"):
                cmd = step["send"]
                wait_pattern = step.get("wait_for")

                if step.get("fire_and_forget"):
                    self._device._conn.send(cmd + "\n")
                    self._device._conn.log_command_block(cmd, "")
                    if delay_after > 0:
                        time.sleep(delay_after)
                    return StepResult(name=name, success=True)

                if wait_pattern:
                    result = self._device.execute(
                        cmd, wait_for=wait_pattern, timeout=timeout
                    )
                else:
                    result = self._device.execute(cmd, timeout=timeout)

                # Verify expect pattern against output
                expect = step.get("expect")
                if expect and not re.search(expect, result.output):
                    return StepResult(
                        name=name,
                        success=False,
                        output=result.output,
                        elapsed=result.elapsed,
                        error=f"Expected pattern not found: {expect}",
                    )

                # Verify expect_not: output must NOT contain this pattern
                expect_not = step.get("expect_not")
                if expect_not:
                    not_match = re.search(expect_not, result.output)
                    if not_match:
                        return StepResult(
                            name=name,
                            success=False,
                            output=result.output,
                            elapsed=result.elapsed,
                            error=f"Unexpected pattern found: {not_match.group()!r} "
                                  f"(expect_not: {expect_not})",
                        )

                if delay_after > 0:
                    time.sleep(delay_after)
                return StepResult(
                    name=name,
                    success=True,
                    output=result.output,
                    elapsed=result.elapsed,
                )

            # Wait-only step (no send, just watch for pattern)
            wait_for = step.get("wait_for")
            if wait_for:
                result = self._device.wait_for(wait_for, timeout=timeout)
                if not result.success:
                    on_timeout = step.get("on_timeout", "fail")
                    if on_timeout == "continue":
                        self._log.warning(
                            f"  Step '{name}': timeout waiting for '{wait_for}', continuing"
                        )
                        return StepResult(
                            name=name,
                            success=False,
                            output=result.output,
                            elapsed=result.elapsed,
                            error=f"Timeout waiting for: {wait_for}",
                        )
                    return StepResult(
                        name=name,
                        success=False,
                        output=result.output,
                        elapsed=result.elapsed,
                        error=f"Timeout waiting for: {wait_for}",
                    )

            if delay_after > 0:
                time.sleep(delay_after)
            return StepResult(name=name, success=True)

        except PatternTimeoutError as e:
            on_timeout = step.get("on_timeout", "fail")
            if on_timeout == "continue":
                return StepResult(
                    name=name, success=False, output=e.output, error=str(e)
                )
            return StepResult(name=name, success=False, error=str(e))
        except Exception as e:
            return StepResult(name=name, success=False, error=str(e))

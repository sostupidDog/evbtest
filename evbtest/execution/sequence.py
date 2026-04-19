"""Multi-step command sequences for boot flows and firmware operations."""

import logging
import time
from dataclasses import dataclass

from evbtest.connection.exceptions import PatternTimeoutError
from evbtest.execution.executor import CommandExecutor, CommandResult


@dataclass
class SequenceStep:
    """One step in a multi-step command sequence."""

    send: str | None = None
    wait_for: str | None = None
    timeout: float = 30.0
    send_newline: bool = True
    send_raw: bytes | None = None
    on_timeout: str = "fail"  # "fail", "continue", "retry"
    retry_count: int = 0
    delay_before: float = 0.0
    delay_after: float = 0.0
    label: str = ""


class CommandSequence:
    """Execute a series of steps on a connection.

    Handles multi-stage interactions like U-Boot boot sequences:

        1. Wait for "Hit any key to stop autoboot"
        2. Send raw Ctrl-C to interrupt
        3. Wait for "=>" (U-Boot prompt)
        4. Send "setenv bootargs ..."
        5. Wait for "=>"
        6. Send "bootm"
        7. Wait for "login:" (may take 60+ seconds)
    """

    def __init__(self, executor: CommandExecutor, steps: list[SequenceStep]):
        self._executor = executor
        self._steps = steps
        self._log = logging.getLogger("evbtest.sequence")

    def execute(self) -> list[CommandResult]:
        """Execute all steps sequentially."""
        results = []
        for i, step in enumerate(self._steps):
            label = step.label or f"step_{i}"
            self._log.info(f"[{label}] Starting step {i + 1}/{len(self._steps)}")

            if step.delay_before > 0:
                time.sleep(step.delay_before)

            result = self._execute_step(step, label)
            results.append(result)

            if not result.success:
                if step.on_timeout == "fail":
                    raise PatternTimeoutError(
                        step.wait_for or "<no-pattern>",
                        result.output,
                        step.timeout,
                    )
                elif step.on_timeout == "skip_rest":
                    self._log.warning(f"[{label}] Skipping remaining steps")
                    break

            if step.delay_after > 0:
                time.sleep(step.delay_after)

        return results

    def _execute_step(self, step: SequenceStep, label: str) -> CommandResult:
        """Execute a single step with optional retry."""
        attempts = 1 + step.retry_count

        for attempt in range(attempts):
            if attempt > 0:
                self._log.info(f"[{label}] Retry attempt {attempt + 1}/{attempts}")

            # Send command or raw bytes
            if step.send_raw:
                self._log.debug(f"[{label}] Sending raw: {step.send_raw!r}")
                self._executor.execute_raw(step.send_raw)
            elif step.send:
                self._log.debug(f"[{label}] Sending: {step.send}")
                self._executor._conn.send(step.send)
                if step.send_newline:
                    self._executor._conn.send("\n")

            # Wait for pattern
            if step.wait_for:
                result = self._executor.wait_for(
                    step.wait_for,
                    timeout=step.timeout,
                    error_on_timeout=False,
                )
                if result.success:
                    self._log.info(f"[{label}] Matched: {step.wait_for}")
                    return result
                else:
                    self._log.warning(
                        f"[{label}] Pattern not matched (attempt {attempt + 1}): "
                        f"{step.wait_for}"
                    )
                    if attempt < attempts - 1:
                        continue
                    return result
            else:
                return CommandResult(command=step.send or "<raw>", output="")

        # Should not reach here, but just in case
        return CommandResult(command=step.send or "<raw>", output="", success=False)

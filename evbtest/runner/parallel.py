"""Multi-device parallel test execution using asyncio."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from evbtest.api.device import DeviceHandle
from evbtest.config.schema import DeviceConfig
from evbtest.connection import create_connection
from evbtest.reporting.result import ParallelRunResult, TestResult
from evbtest.runner.python_runner import PythonTestCaseRunner
from evbtest.runner.yaml_runner import YAMLTestCaseRunner


logger = logging.getLogger("evbtest.parallel")


@dataclass
class DeviceTestTask:
    """One device running one test case."""

    device_name: str
    test_name: str
    test_type: str  # "yaml" or "python"
    test_path: str
    result: TestResult | None = None
    log_path: str | None = None


class ParallelRunner:
    """Run tests across multiple devices concurrently using asyncio.

    Architecture:
      - Each device gets its own asyncio task
      - Device connections are thread-based (paramiko, sockets) but wrapped
        in asyncio.run_in_executor for non-blocking operation
      - Semaphore caps the total concurrent device connections
      - Each task gets a session log file capturing all device I/O
    """

    def __init__(
        self,
        device_configs: dict[str, DeviceConfig],
        max_concurrent: int = 10,
        log_dir: str = "logs",
        enable_logging: bool = True,
    ):
        self._device_configs = device_configs
        self._max_concurrent = max_concurrent
        self._log_dir = log_dir
        self._enable_logging = enable_logging
        self._log = logging.getLogger("evbtest.parallel")
        self._run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    async def run_tests(self, tasks: list[DeviceTestTask]) -> ParallelRunResult:
        """Run all device/test tasks concurrently."""
        start = time.monotonic()
        self._log.info(f"Starting parallel run: {len(tasks)} tasks")

        semaphore = asyncio.Semaphore(self._max_concurrent)
        coroutines = [self._run_single(task, semaphore) for task in tasks]
        await asyncio.gather(*coroutines, return_exceptions=True)

        duration = time.monotonic() - start
        run_result = ParallelRunResult(duration=duration)

        for task in tasks:
            run_result.total += 1
            if task.result:
                run_result.results.append(task.result)
                if task.result.status == "PASS":
                    run_result.passed += 1
                elif task.result.status == "FAIL":
                    run_result.failed += 1
                else:
                    run_result.errors += 1
            else:
                run_result.errors += 1

        self._log.info(
            f"Parallel run complete: {run_result.passed}/{run_result.total} passed "
            f"in {duration:.1f}s"
        )
        return run_result

    async def _run_single(
        self, task: DeviceTestTask, semaphore: asyncio.Semaphore
    ) -> None:
        """Execute one test on one device, respecting concurrency limit."""
        async with semaphore:
            loop = asyncio.get_event_loop()
            try:
                task.result = await loop.run_in_executor(
                    None,
                    self._execute_sync,
                    task,
                )
            except Exception as e:
                self._log.error(
                    f"Task {task.device_name}/{task.test_name}: {e}"
                )
                task.result = TestResult(
                    device=task.device_name,
                    test=task.test_name,
                    status="ERROR",
                    error=str(e),
                    start_time=time.monotonic(),
                    end_time=time.monotonic(),
                )

    def _execute_sync(self, task: DeviceTestTask) -> TestResult:
        """Synchronous test execution (runs in thread pool)."""
        device_config = self._device_configs.get(task.device_name)
        if device_config is None:
            return TestResult(
                device=task.device_name,
                test=task.test_name,
                status="ERROR",
                error=f"Device '{task.device_name}' not found in config",
                start_time=time.monotonic(),
                end_time=time.monotonic(),
            )

        # Create session log file for this task
        log_path = None
        if self._enable_logging:
            log_path = Path(self._log_dir) / self._run_timestamp / (
                f"{task.device_name}_{task.test_name}.log"
            )
            log_path.parent.mkdir(parents=True, exist_ok=True)
            task.log_path = str(log_path)

        connection = create_connection(device_config)
        if log_path:
            connection.set_session_log(log_path)
        try:
            self._log.info(f"Connecting to {task.device_name}...")
            connection.connect()
            if log_path:
                self._log.info(
                    f"Connected to {task.device_name}, log: {log_path}"
                )
            else:
                self._log.info(f"Connected to {task.device_name}")

            device = DeviceHandle(device_config, connection)

            if task.test_type == "yaml":
                runner = YAMLTestCaseRunner(device)
                return runner.run_file(task.test_path)
            else:
                runner = PythonTestCaseRunner(device)
                results = runner.run_file(task.test_path)
                # Return first result (or aggregate if multiple tests in file)
                if results:
                    return results[0]
                return TestResult(
                    device=task.device_name,
                    test=task.test_name,
                    status="ERROR",
                    error="No test classes found in Python file",
                    start_time=time.monotonic(),
                    end_time=time.monotonic(),
                )
        finally:
            self._log.info(f"Disconnecting from {task.device_name}...")
            connection.disconnect()

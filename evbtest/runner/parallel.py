"""Multi-device parallel test execution using asyncio."""

import asyncio
import logging
import time
from collections import defaultdict
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
      - Tasks are grouped by device. Each device gets one connection that
        is reused across all its test tasks.
      - Different devices run in parallel; tasks on the same device run
        sequentially (sharing one connection).
      - Semaphore caps the total concurrent device connections.
    """

    def __init__(
        self,
        device_configs: dict[str, DeviceConfig],
        max_concurrent: int = 10,
        log_dir: str = "logs",
        enable_logging: bool = True,
        on_task_complete=None,
    ):
        self._device_configs = device_configs
        self._max_concurrent = max_concurrent
        self._log_dir = log_dir
        self._enable_logging = enable_logging
        self._on_task_complete = on_task_complete
        self._log = logging.getLogger("evbtest.parallel")
        self._run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    async def run_tests(self, tasks: list[DeviceTestTask]) -> ParallelRunResult:
        """Run all device/test tasks concurrently."""
        start = time.monotonic()
        self._log.info(f"Starting parallel run: {len(tasks)} tasks")

        # Group tasks by device
        device_tasks: dict[str, list[DeviceTestTask]] = defaultdict(list)
        for task in tasks:
            device_tasks[task.device_name].append(task)

        semaphore = asyncio.Semaphore(self._max_concurrent)
        coroutines = [
            self._run_device_tasks(dev_name, dev_tasks, semaphore)
            for dev_name, dev_tasks in device_tasks.items()
        ]
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

    async def _run_device_tasks(
        self,
        device_name: str,
        tasks: list[DeviceTestTask],
        semaphore: asyncio.Semaphore,
    ) -> None:
        """Run all tasks for a single device, reusing one connection."""
        async with semaphore:
            loop = asyncio.get_event_loop()
            device_config = self._device_configs.get(device_name)
            if device_config is None:
                for task in tasks:
                    task.result = TestResult(
                        device=device_name,
                        test=task.test_name,
                        status="ERROR",
                        error=f"Device '{device_name}' not found in config",
                        start_time=time.monotonic(),
                        end_time=time.monotonic(),
                    )
                    if self._on_task_complete:
                        self._on_task_complete(task)
                return

            connection = create_connection(device_config)
            try:
                self._log.info(f"Connecting to {device_name}...")
                await loop.run_in_executor(None, connection.connect)
                self._log.info(f"Connected to {device_name}")

                for task in tasks:
                    try:
                        task.result = await loop.run_in_executor(
                            None,
                            self._execute_with_connection,
                            task,
                            device_config,
                            connection,
                        )
                    except Exception as e:
                        self._log.error(
                            f"Task {device_name}/{task.test_name}: {e}"
                        )
                        task.result = TestResult(
                            device=device_name,
                            test=task.test_name,
                            status="ERROR",
                            error=str(e),
                            start_time=time.monotonic(),
                            end_time=time.monotonic(),
                        )
                    finally:
                        if self._on_task_complete:
                            self._on_task_complete(task)
            finally:
                self._log.info(f"Disconnecting from {device_name}...")
                await loop.run_in_executor(None, connection.disconnect)

    def _execute_with_connection(
        self,
        task: DeviceTestTask,
        device_config: DeviceConfig,
        connection,
    ) -> TestResult:
        """Run a single test using an existing connection (sync, in thread)."""
        # Setup session log for this task
        log_path = None
        if self._enable_logging:
            log_path = Path(self._log_dir) / self._run_timestamp / (
                f"{task.device_name}_{task.test_name}.log"
            )
            log_path.parent.mkdir(parents=True, exist_ok=True)
            task.log_path = str(log_path)
            connection.set_session_log(log_path)

        try:
            device = DeviceHandle(device_config, connection)

            if task.test_type == "yaml":
                runner = YAMLTestCaseRunner(device)
                return runner.run_file(task.test_path)
            else:
                runner = PythonTestCaseRunner(device)
                results = runner.run_file(task.test_path)
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
            connection.close_session_log()

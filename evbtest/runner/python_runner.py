"""Python test case runner — discover and execute TestCase subclasses."""

import importlib.util
import inspect
import logging
import time
from pathlib import Path

from evbtest.api.device import DeviceHandle
from evbtest.api.testcase import TestCase
from evbtest.reporting.result import TestResult


class PythonTestCaseRunner:
    """Discover and execute Python test cases."""

    def __init__(
        self,
        device: DeviceHandle,
        secondary_device: DeviceHandle | None = None,
    ):
        self._device = device
        self._secondary_device = secondary_device
        self._log = logging.getLogger("evbtest.python_runner")

    def run_file(self, path: str) -> list[TestResult]:
        """Load a Python file, find all TestCase subclasses, and run them."""
        results = []
        test_classes = self._discover_tests(path)

        for cls in test_classes:
            result = self._run_test_class(cls)
            results.append(result)

        return results

    def run_class(self, test_class: type[TestCase]) -> TestResult:
        """Run a single TestCase class."""
        return self._run_test_class(test_class)

    def run_class_by_name(self, path: str, class_name: str) -> TestResult:
        """Run a specific TestCase class by name from a Python file."""
        test_classes = self._discover_tests(path)
        for cls in test_classes:
            instance = cls()
            if instance.name == class_name or cls.__name__ == class_name:
                return self._run_test_class(cls)
        return TestResult(
            device=self._device.name,
            test=class_name,
            status="ERROR",
            error=f"Test class '{class_name}' not found in {path}",
            start_time=time.monotonic(),
            end_time=time.monotonic(),
        )

    def _discover_tests(self, path: str) -> list[type[TestCase]]:
        """Import a Python file and find all TestCase subclasses."""
        file_path = Path(path).resolve()
        module_name = file_path.stem

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find all TestCase subclasses defined in this module
        test_classes = []
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, TestCase)
                and obj is not TestCase
                and obj.__module__ == module_name
            ):
                test_classes.append(obj)

        if not test_classes:
            self._log.warning(f"No TestCase subclasses found in {path}")

        return test_classes

    @staticmethod
    def discover_class_names(path: str) -> list[str]:
        """Discover TestCase subclass names in a Python file without running them.

        Returns list of test names (from cls.name, falling back to class __name__).
        Used by CLI to create one task per test class.
        """
        file_path = Path(path).resolve()
        module_name = file_path.stem

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return []

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        names = []
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, TestCase)
                and obj is not TestCase
                and obj.__module__ == module_name
            ):
                # Instantiate to get the resolved name
                instance = obj()
                names.append(instance.name)
        return names

    @staticmethod
    def discover_classes(path: str) -> list[tuple[str, dict]]:
        """Discover TestCase subclasses and their metadata.

        Returns list of (name, metadata_dict) tuples.
        metadata_dict includes: use_secondary
        """
        file_path = Path(path).resolve()
        module_name = file_path.stem

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return []

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        results = []
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, TestCase)
                and obj is not TestCase
                and obj.__module__ == module_name
            ):
                instance = obj()
                results.append((
                    instance.name,
                    {"use_secondary": getattr(obj, "use_secondary", False)},
                ))
        return results

    def _run_test_class(self, cls: type[TestCase]) -> TestResult:
        """Execute a single TestCase: setup → run → teardown."""
        instance = cls()
        instance.set_device(self._device)

        # Inject secondary device if test requests it
        if instance.use_secondary and self._secondary_device is not None:
            instance.set_secondary_device(self._secondary_device)

        result = TestResult(
            device=self._device.name,
            test=instance.name,
            status="RUNNING",
        )
        result.start_time = time.monotonic()

        try:
            # Setup
            self._log.info(f"Setup: {instance.name}")
            instance.setup()

            # Run
            self._log.info(f"Run: {instance.name}")
            instance.run()

            result.status = "PASS"
            instance._passed = True

        except AssertionError as e:
            self._log.error(f"Assert failed: {e}")
            result.status = "FAIL"
            result.error = str(e)
            instance._passed = False

        except Exception as e:
            self._log.error(f"Test error: {e}")
            result.status = "ERROR"
            result.error = str(e)
            instance._passed = False

        finally:
            # Teardown always runs
            try:
                self._log.info(f"Teardown: {instance.name}")
                instance.teardown()
            except Exception as e:
                self._log.warning(f"Teardown error: {e}")

            result.end_time = time.monotonic()

        return result

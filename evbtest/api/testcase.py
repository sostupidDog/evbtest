"""Base class for Python test cases."""

from abc import ABC, abstractmethod

from evbtest.api.device import DeviceHandle
from evbtest.execution.executor import CommandResult


class TestCase(ABC):
    """Base class for Python test cases.

    Subclass this and implement run(). The framework provides
    a DeviceHandle for each assigned device.

    Usage:
        class MyTest(TestCase):
            name = "my_test"
            tags = ["smoke"]

            def run(self):
                result = self.device.execute("uname -a")
                assert "Linux" in result.output
    """

    # Metadata -- can be overridden in subclass
    name: str = ""
    description: str = ""
    tags: list[str] = []

    def __init__(self):
        self.name = self.name or self.__class__.__name__
        self._device: DeviceHandle | None = None
        self._results: list[CommandResult] = []
        self._passed: bool | None = None
        self._error: Exception | None = None

    def set_device(self, device: DeviceHandle) -> None:
        """Called by the framework before run()."""
        self._device = device

    @property
    def device(self) -> DeviceHandle:
        """Access the device handle inside run()."""
        if self._device is None:
            raise RuntimeError("No device assigned. Are you inside run()?")
        return self._device

    @abstractmethod
    def run(self) -> None:
        """Implement the test logic here.

        Use self.device to interact with the device.
        Raise an exception to indicate failure.
        Normal return = pass.
        """

    def setup(self) -> None:
        """Optional setup, called before run(). Override as needed."""

    def teardown(self) -> None:
        """Optional teardown, called after run() (even on failure)."""

    @property
    def passed(self) -> bool | None:
        return self._passed

    @property
    def results(self) -> list[CommandResult]:
        return self._results

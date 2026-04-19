"""Test result data structures."""

from dataclasses import dataclass, field


@dataclass
class StepResult:
    """Result of a single test step."""

    name: str
    success: bool
    output: str = ""
    error: str | None = None
    elapsed: float = 0.0


@dataclass
class TestResult:
    """Result of a complete test case."""

    device: str
    test: str
    status: str = "PENDING"  # PENDING, RUNNING, PASS, FAIL, ERROR, SKIP
    steps: list[StepResult] = field(default_factory=list)
    error: str | None = None
    start_time: float = 0.0
    end_time: float = 0.0

    def add_step(self, step: StepResult) -> None:
        self.steps.append(step)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


@dataclass
class ParallelRunResult:
    """Aggregate result of a parallel test run."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    results: list[TestResult] = field(default_factory=list)
    duration: float = 0.0

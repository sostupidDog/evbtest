"""CLI logging and output formatting using rich."""

import logging

from rich.console import Console
from rich.table import Table

from evbtest.reporting.result import ParallelRunResult, TestResult


class TestLogger:
    """Formatted CLI output during test execution."""

    def __init__(self):
        self.console = Console()
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Configure Python logging to integrate with rich output."""
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger = logging.getLogger("evbtest")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    def log_step(
        self, device: str, step: str, status: str, output: str = ""
    ) -> None:
        """Log a single step execution."""
        color = {
            "PASS": "green",
            "FAIL": "red",
            "RUNNING": "yellow",
            "ERROR": "red",
        }.get(status, "white")
        self.console.print(
            f"  [{color}]{status}[/{color}] [{cyan}]{device}[/{cyan}]: {step}"
        )
        if output and status in ("FAIL", "ERROR"):
            self.console.print(f"    [dim]{output[-200:]}[/dim]")

    def log_result(self, result: TestResult) -> None:
        """Log a complete test result."""
        status_color = "green" if result.status == "PASS" else "red"
        self.console.print(
            f"[{status_color}]{result.status}[/{status_color}] "
            f"{result.test} on {result.device} ({result.duration:.1f}s)"
        )

    def print_summary(self, run_result: ParallelRunResult) -> None:
        """Print final summary table."""
        table = Table(title="Test Results Summary")
        table.add_column("Device")
        table.add_column("Test")
        table.add_column("Status")
        table.add_column("Duration")

        for r in run_result.results:
            color = "green" if r.status == "PASS" else "red"
            table.add_row(
                r.device,
                r.test,
                f"[{color}]{r.status}[/{color}]",
                f"{r.duration:.1f}s",
            )

        self.console.print(table)
        self.console.print(
            f"\n[bold]Total: {run_result.total} | "
            f"[green]Passed: {run_result.passed}[/green] | "
            f"[red]Failed: {run_result.failed}[/red] | "
            f"[yellow]Errors: {run_result.errors}[/yellow][/bold]"
        )

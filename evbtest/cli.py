"""CLI interface for evb-test framework."""

import asyncio
import select
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from evbtest.config.loader import ConfigLoader
from evbtest.config.schema import DeviceConfig
from evbtest.connection import create_connection
from evbtest.reporting.logger import TestLogger
from evbtest.runner.parallel import DeviceTestTask, ParallelRunner
from evbtest.runner.python_runner import PythonTestCaseRunner

console = Console()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, verbose):
    """evb-test: Lightweight remote device testing framework."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option(
    "--devices",
    "-d",
    default="configs/devices.yaml",
    help="Device config file",
)
@click.option("--tests", "-t", multiple=True, default=("testcases/",), help="Test files or directories (default: testcases/)")
@click.option("--device", "-D", "device_filter", default=None, help="Run only on this device")
@click.option("--tags", multiple=True, help="Filter tests by tag")
@click.option("--max-concurrent", "-j", default=5, help="Max parallel devices")
@click.option("--fail-fast", "-x", is_flag=True, help="Stop on first failure")
@click.option("--output", "-o", default="logs/", help="Output directory")
@click.option("--no-log", is_flag=True, help="Disable session log files")
@click.option("--preflight", "-p", default=None, help="Preflight check YAML (run before all tests per device)")
@click.pass_context
def run(ctx, devices, tests, device_filter, tags, max_concurrent, fail_fast, output, no_log, preflight):
    """Run test suite against configured devices."""
    console.print("[bold cyan]evb-test[/bold cyan] - Starting test run")

    # Load device configs
    device_path = Path(devices)
    if not device_path.exists():
        console.print(f"[red]Device config not found: {devices}[/red]")
        sys.exit(1)

    device_configs = ConfigLoader.load_devices(device_path)

    # Filter devices if specified
    if device_filter:
        if device_filter not in device_configs:
            console.print(f"[red]Unknown device: {device_filter}[/red]")
            console.print(f"Available: {', '.join(device_configs.keys())}")
            sys.exit(1)
        device_configs = {device_filter: device_configs[device_filter]}

    # Discover test files
    test_files = _discover_tests(tests)
    if not test_files:
        console.print("[yellow]No test files found[/yellow]")
        sys.exit(0)

    console.print(f"Found {len(test_files)} test file(s):")
    for tf in test_files:
        console.print(f"  [dim]{tf}[/dim]")
    console.print(f"Devices: {', '.join(device_configs.keys())}")

    # Build tasks: each test × each device
    tasks = []
    for test_path in test_files:
        test_type = "yaml" if test_path.suffix in (".yaml", ".yml") else "python"

        if test_type == "python":
            # Discover all TestCase subclasses with metadata
            class_info = PythonTestCaseRunner.discover_classes(str(test_path))
            if class_info:
                for cls_name, meta in class_info:
                    for dev_name in device_configs:
                        dev_cfg = device_configs[dev_name]
                        needs_sec = (
                            meta.get("use_secondary", False)
                            and dev_cfg.secondary_connection is not None
                        )
                        tasks.append(
                            DeviceTestTask(
                                device_name=dev_name,
                                test_name=cls_name,
                                test_type=test_type,
                                test_path=str(test_path),
                                test_class=cls_name,
                                needs_secondary=needs_sec,
                            )
                        )
            else:
                # No classes found — still create task to report the error
                for dev_name in device_configs:
                    tasks.append(
                        DeviceTestTask(
                            device_name=dev_name,
                            test_name=test_path.stem,
                            test_type=test_type,
                            test_path=str(test_path),
                        )
                    )
        else:
            test_name = test_path.stem
            for dev_name in device_configs:
                tasks.append(
                    DeviceTestTask(
                        device_name=dev_name,
                        test_name=test_name,
                        test_type=test_type,
                        test_path=str(test_path),
                    )
                )

    console.print(f"Total: {len(tasks)} task(s)\n")

    # Progress callback: print result as each task completes
    completed = [0]
    total_tasks = len(tasks)

    def on_task_complete(task):
        completed[0] += 1
        r = task.result
        if r is None:
            return
        status_color = {
            "PASS": "green", "FAIL": "red", "ERROR": "red", "SKIP": "yellow",
        }.get(r.status, "white")
        console.print(
            f"  [{completed[0]}/{total_tasks}] "
            f"[{status_color}]{r.status}[/{status_color}] "
            f"{r.test} @ {r.device} ({r.duration:.1f}s)"
        )

    # Run tests
    console.print("[bold]Running tests...[/bold]")
    # Validate preflight file if specified
    if preflight:
        preflight_path = Path(preflight)
        if not preflight_path.exists():
            console.print(f"[red]Preflight file not found: {preflight}[/red]")
            sys.exit(1)
        preflight = str(preflight_path)

    runner = ParallelRunner(
        device_configs, max_concurrent=max_concurrent, log_dir=output,
        enable_logging=not no_log, on_task_complete=on_task_complete,
        preflight_path=preflight,
    )
    result = asyncio.run(runner.run_tests(tasks))

    # Print summary
    test_logger = TestLogger()
    test_logger.print_summary(result)

    # Print log file paths
    log_tasks = [t for t in tasks if t.log_path]
    if log_tasks:
        console.print("\n[dim]Session logs:[/dim]")
        for t in log_tasks:
            console.print(f"  [dim]{t.log_path}[/dim]")

    # Exit code
    sys.exit(1 if result.failed > 0 or result.errors > 0 else 0)


@cli.command()
@click.argument("device_name")
@click.option(
    "--devices",
    "-d",
    default="configs/devices.yaml",
    help="Device config file",
)
def connect(device_name, devices):
    """Open interactive session to a device (for debugging)."""
    device_path = Path(devices)
    if not device_path.exists():
        console.print(f"[red]Device config not found: {devices}[/red]")
        sys.exit(1)

    device_configs = ConfigLoader.load_devices(device_path)
    config = device_configs.get(device_name)
    if not config:
        console.print(f"[red]Unknown device: {device_name}[/red]")
        console.print(f"Available: {', '.join(device_configs.keys())}")
        sys.exit(1)

    conn = create_connection(config)
    try:
        console.print(f"[green]Connecting to {device_name}...[/green]")
        conn.connect()
        console.print(
            f"[green]Connected to {device_name}[/green]. "
            "Type commands, Ctrl-C to exit."
        )
        _interactive_session(conn)
    except KeyboardInterrupt:
        console.print("\n[yellow]Disconnected[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
    finally:
        conn.disconnect()


@cli.command()
@click.option(
    "--devices",
    "-d",
    default="configs/devices.yaml",
    help="Device config file",
)
def list_devices(devices):
    """List all configured devices."""
    device_path = Path(devices)
    if not device_path.exists():
        console.print(f"[red]Device config not found: {devices}[/red]")
        sys.exit(1)

    device_configs = ConfigLoader.load_devices(device_path)
    table = Table(title="Configured Devices")
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Host")
    table.add_column("Tags")

    for name, cfg in device_configs.items():
        table.add_row(
            name,
            cfg.connection.type,
            f"{cfg.connection.host}:{cfg.connection.port}",
            ", ".join(cfg.tags) if cfg.tags else "-",
        )
    console.print(table)


@cli.command()
@click.argument("test_path")
def check(test_path):
    """Validate a YAML test case file without running it."""
    path = Path(test_path)
    if not path.exists():
        console.print(f"[red]File not found: {test_path}[/red]")
        sys.exit(1)

    if path.suffix not in (".yaml", ".yml"):
        console.print("[red]Only YAML files can be checked[/red]")
        sys.exit(1)

    import yaml

    try:
        with open(path) as f:
            spec = yaml.safe_load(f)

        test_spec = spec.get("test")
        if not test_spec:
            console.print("[red]Missing 'test' root key[/red]")
            sys.exit(1)

        name = test_spec.get("name", "<unnamed>")
        phases = test_spec.get("phases", [])

        console.print(f"[green]Valid:[/green] {name}")
        console.print(f"  Phases: {len(phases)}")
        for phase in phases:
            steps = phase.get("steps", [])
            console.print(f"    {phase.get('name', 'unnamed')}: {len(steps)} step(s)")

    except yaml.YAMLError as e:
        console.print(f"[red]YAML parse error: {e}[/red]")
        sys.exit(1)


@cli.command()
def init():
    """Initialize project directory with example configs and test cases."""
    base = Path(".")

    # Create directories
    for d in ["configs", "testcases/yaml", "testcases/python", "logs"]:
        (base / d).mkdir(parents=True, exist_ok=True)
        console.print(f"Created: {d}/")

    # Create example device config
    devices_path = base / "configs" / "devices.yaml"
    if not devices_path.exists():
        devices_path.write_text(
            """# Device definitions
devices:
  evb_board_1:
    description: "ARM64 EVB board via Talent serial"
    tags: ["arm64", "serial"]
    connection:
      type: serial_tcp
      host: 192.168.1.200
      port: 5001
      timeout: 30.0
    prompt_pattern: "[#\\\\$>]\\\\s*$"
    uboot_prompt: "=>"
    login_prompt: "login:"

  linux_server:
    description: "Linux server via SSH"
    tags: ["x86", "ssh"]
    connection:
      type: ssh
      host: 192.168.1.10
      port: 22
      username: root
      key_filename: ~/.ssh/id_rsa
    prompt_pattern: "[#\\\\$]\\\\s*$"
"""
        )
        console.print("Created: configs/devices.yaml")

    console.print("\n[green]Project initialized![/green]")
    console.print("Edit configs/devices.yaml with your device info,")
    console.print("then create test cases in testcases/yaml/ or testcases/python/")


def _discover_tests(test_args: tuple[str, ...]) -> list[Path]:
    """Discover test files from arguments (files or directories)."""
    files = []
    for arg in test_args:
        path = Path(arg)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("*.yaml"))
            files.extend(path.rglob("*.yml"))
            files.extend(path.rglob("*.py"))
    return sorted(files)


def _interactive_session(conn) -> None:
    """Run an interactive terminal session with the device."""
    import sys
    import termios
    import tty

    old_settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setraw(sys.stdin.fileno())
        while True:
            # Check stdin for user input
            if select.select([sys.stdin], [], [], 0.05)[0]:
                char = sys.stdin.read(1)
                if char == "\x03":  # Ctrl-C
                    break
                conn.send(char)

            # Read device output
            output = conn.read(timeout=0.05)
            if output:
                sys.stdout.write(output)
                sys.stdout.flush()
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


def main():
    cli()


if __name__ == "__main__":
    main()

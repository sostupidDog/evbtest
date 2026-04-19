"""Configuration data models."""

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class ConnectionConfig:
    """Base connection parameters."""

    type: Literal["ssh", "serial_tcp"]
    timeout: float = 30.0


@dataclass
class SSHConfig(ConnectionConfig):
    """SSH connection parameters."""

    type: Literal["ssh"] = "ssh"
    host: str = ""
    port: int = 22
    username: str = "root"
    password: Optional[str] = None
    key_filename: Optional[str] = None


@dataclass
class SerialTCPConfig(ConnectionConfig):
    """Talent TCP serial port server connection parameters."""

    type: Literal["serial_tcp"] = "serial_tcp"
    host: str = ""
    port: int = 5000
    baud_rate: int = 115200  # Info only; configured on hardware side


@dataclass
class DeviceConfig:
    """Complete device definition."""

    name: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    connection: SSHConfig | SerialTCPConfig = field(default_factory=SSHConfig)
    prompt_pattern: str = r"[#\$>]\s*$"
    login_prompt: str = "login:"
    uboot_prompt: str = "=>"
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class TestSuiteConfig:
    """Top-level test run configuration."""

    name: str = "default"
    devices: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    max_concurrent: int = 5
    output_dir: str = "logs/"
    log_level: str = "INFO"
    fail_fast: bool = False
    global_timeout: float = 3600.0

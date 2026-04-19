"""Configuration file loader."""

from pathlib import Path

import yaml

from evbtest.config.schema import (
    ConnectionConfig,
    DeviceConfig,
    SerialTCPConfig,
    SSHConfig,
    TestSuiteConfig,
)


class ConfigLoader:
    """Load and merge configuration from YAML files."""

    @staticmethod
    def load_devices(path: str | Path) -> dict[str, DeviceConfig]:
        """Load device definitions from YAML file."""
        with open(path) as f:
            raw = yaml.safe_load(f)

        devices = {}
        for name, spec in raw.get("devices", {}).items():
            conn_spec = spec.get("connection", {})
            conn_type = conn_spec.get("type", "ssh")

            if conn_type == "ssh":
                conn = SSHConfig(
                    type="ssh",
                    host=conn_spec.get("host", ""),
                    port=conn_spec.get("port", 22),
                    username=conn_spec.get("username", "root"),
                    password=conn_spec.get("password"),
                    key_filename=conn_spec.get("key_filename"),
                    timeout=conn_spec.get("timeout", 30.0),
                )
            elif conn_type == "serial_tcp":
                conn = SerialTCPConfig(
                    type="serial_tcp",
                    host=conn_spec.get("host", ""),
                    port=conn_spec.get("port", 5000),
                    baud_rate=conn_spec.get("baud_rate", 115200),
                    timeout=conn_spec.get("timeout", 30.0),
                )
            else:
                raise ValueError(f"Unknown connection type: {conn_type}")

            devices[name] = DeviceConfig(
                name=name,
                description=spec.get("description", ""),
                tags=spec.get("tags", []),
                connection=conn,
                prompt_pattern=spec.get("prompt_pattern", r"[#\$>]\s*$"),
                login_prompt=spec.get("login_prompt", "login:"),
                uboot_prompt=spec.get("uboot_prompt", "=>"),
                env=spec.get("env", {}),
            )
        return devices

    @staticmethod
    def load_test_suite(path: str | Path) -> TestSuiteConfig:
        """Load test suite configuration."""
        with open(path) as f:
            raw = yaml.safe_load(f)

        suite = raw.get("suite", {})
        return TestSuiteConfig(
            name=suite.get("name", "default"),
            devices=suite.get("devices", []),
            tests=suite.get("tests", []),
            max_concurrent=suite.get("max_concurrent", 5),
            fail_fast=suite.get("fail_fast", False),
            log_level=suite.get("log_level", "INFO"),
            output_dir=suite.get("output_dir", "logs/"),
            global_timeout=suite.get("global_timeout", 3600.0),
        )

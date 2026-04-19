"""Connection module — factory function and re-exports."""

from evbtest.config.schema import DeviceConfig, SerialTCPConfig, SSHConfig
from evbtest.connection.base import ConnectionBase, ConnectionState
from evbtest.connection.exceptions import (
    ConnectionClosedError,
    ConnectionError,
    ConnectionTimeoutError,
    PatternTimeoutError,
)
from evbtest.connection.output_buffer import OutputBuffer
from evbtest.connection.serial_tcp import SerialTCPConnection
from evbtest.connection.ssh import SSHConnection

__all__ = [
    "ConnectionBase",
    "ConnectionClosedError",
    "ConnectionError",
    "ConnectionState",
    "ConnectionTimeoutError",
    "OutputBuffer",
    "PatternTimeoutError",
    "SSHConnection",
    "SerialTCPConnection",
    "create_connection",
]


def create_connection(config: DeviceConfig) -> ConnectionBase:
    """Factory: create the appropriate connection from device config."""
    conn_cfg = config.connection
    if isinstance(conn_cfg, SSHConfig):
        return SSHConnection(
            connection_id=config.name,
            host=conn_cfg.host,
            port=conn_cfg.port,
            username=conn_cfg.username,
            password=conn_cfg.password,
            key_filename=conn_cfg.key_filename,
            timeout=conn_cfg.timeout,
        )
    elif isinstance(conn_cfg, SerialTCPConfig):
        return SerialTCPConnection(
            connection_id=config.name,
            host=conn_cfg.host,
            port=conn_cfg.port,
            timeout=conn_cfg.timeout,
        )
    else:
        raise ValueError(f"Unsupported connection type: {type(conn_cfg)}")

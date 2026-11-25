from typing import (
    Annotated,
    Optional,
)

from pydantic import BeforeValidator, Field, FilePath, NonNegativeInt, PositiveInt
from qjazz_core.config import ConfBuilder, ConfigBase

from .config import QgisConfig


# Parse list from string
def _parse_list(value: list[str] | str) -> list[str]:
    if isinstance(value, str):
        # Parse comma separated list
        value = value.split(",") if value else []
    return value


class Listen(ConfigBase):
    """Socket configuration"""

    address: str = Field(
        "127.0.0.1:23456",
        title="Socket address",
    )
    enable_tls: bool = Field(
        False,
        title="Enable TLS",
        description="Enable TLS, require certificat and key",
    )
    tls_key_file: Optional[FilePath] = Field(
        None,
        title="Path to TLS key file",
    )
    tls_cert_file: Optional[FilePath] = Field(
        None,
        title="Path to TLS cert PEM file",
    )
    tls_client_cafile: Optional[FilePath] = Field(
        None,
        title="Path ho TLS client CA file",
    )


class Rpc(ConfigBase):
    listen: Listen = Field(Listen())
    enable_admin_services: bool = Field(
        True,
        title="Use admin services",
    )
    timeout: int = Field(
        20,
        title="Timeout for requests in seconds",
    )
    shutdown_grace_period: int = Field(
        10,
        title="Request timeout",
        description=(
            "The maximum amount of time to wait in seconds before\n"
            "closing connections. During this period,\n"
            "no new connections are allowed."
        ),
    )
    max_failure_pressure: float = Field(
        0.9,
        description=(
            "The maximum allowed failure pressure.\n"
            "If the failure pressure exceed this value then\n"
            "the service will exit with critical error condition,"
        ),
    )
    high_water_mark: float = Field(
        0.9,
        description=(
            "Set memory high water mark as fraction of total memory.\n"
            "Workers are restarted if total memory percent usage of workers\n"
            "exceed that value."
        ),
    )
    oom_period: int = Field(
        5,
        description=("Interval in seconds between two check the out-of-memory\nhandler."),
    )
    keepalive: int = Field(
        60,
        description=(
            "Interval in seconds for sending keepalive probes\n"
            "(TCP keepalive and HTTP2 PING) to clients.\n"
            "Connections from unresponsive clients are closed.\n"
            "Set to 0 to disable keepalive."
        ),
    )


class Worker(ConfigBase):
    name: str = Field("", title="Name of the worker instance")
    num_processes: PositiveInt = Field(
        default=1,
        title="Number of simultanous workers",
        description=(
            "This is the initial number of workers when the number\n"
            "of workers is adjusted dynamically between `min_processes`\n"
            "and `max_processes`."
        ),
    )
    min_processes: Optional[PositiveInt] = Field(
        default=None,
        title="Minimum number of workers",
        description="Lower bound of the number of workers.\nDefaults to `num_processes`.",
    )
    max_processes: Optional[PositiveInt] = Field(
        default=None,
        title="Maximum number of workers",
        description="Upper bound of the number of workers.\nDefaults to `num_processes`.",
    )
    qgis: QgisConfig = Field(
        QgisConfig(),
        title="Qgis configuration",
    )
    process_start_timeout: int = Field(
        default=5,
        title="Timeout for starting child process",
    )
    cancel_timeout: int = Field(
        default=3,
        title="Cancel timeout",
        description=(
            "The grace period to apply on worker timeout\n"
            "when attempting to cancel the actual request\n"
            "This number should be kept small (a few seconds) since it\n"
            "will be used after the response timeout.\n"
        ),
    )
    max_waiting_requests: int = Field(
        default=50,
        title="Maximum queued requests",
        description=(
            "The maximum number of requests that can be\n"
            "queued. If the number of waiting requests reach the limit,\n"
            "the subsequent requests will be returned with a `service unavailable`\n"
            "error."
        ),
    )
    max_life_cycles: NonNegativeInt = Field(
        default=0,
        title="Maximum worker life cycles",
        description=(
            "The maximum number of life cycles of a worker.\n"
            "When a worker reaches this number of life cycles, it is\n"
            "terminated at recycling time and replaced by a new one.\n"
            "Set to 0 to disable the limit."
        ),
    )
    max_chunk_size: PositiveInt = Field(
        default=1024 * 1024,
        title="Max chunk size",
    )
    restore_projects: Annotated[
        list[str],
        BeforeValidator(_parse_list),
    ] = Field(
        default=[],
        title="Startup projects",
        description="Projects to restore at startup",
    )


if __name__ == "__main__":
    import sys

    import click

    @click.group("commands")
    def cli_commands():
        pass

    @cli_commands.command("schema")
    @click.option(
        "--format",
        "out_fmt",
        type=click.Choice(("json", "yaml", "toml")),
        default="json",
        help="Output format (--schema only)",
    )
    @click.option("--pretty", is_flag=True, help="Pretty format")
    def print_schema(
        out_fmt: str,
        pretty: bool = False,
    ):
        """Print configuration as json and exit"""
        import json

        confservice = ConfBuilder()

        confservice.add_section("rpc", Rpc)
        confservice.add_section("worker", Worker)

        indent = 4 if pretty else None
        match out_fmt:
            case "json":
                json_schema = confservice.json_schema()
                indent = 4 if pretty else None
                click.echo(json.dumps(json_schema, indent=indent))
            case "yaml":
                from ruamel.yaml import YAML

                json_schema = confservice.json_schema()
                yaml = YAML()
                yaml.dump(json_schema, sys.stdout)
            case "toml":
                confservice.dump_toml_schema(sys.stdout)

    cli_commands()

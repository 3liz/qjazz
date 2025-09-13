#
#
#
from typing import (
    Annotated,
    Optional,
    Union,
)

from pydantic import BeforeValidator, Field, FilePath
from qjazz_core.config import ConfBuilder, ConfigBase

from .config import QgisConfig


# Parse list from string
def _parse_list(value: Union[list[str], str]) -> list[str]:
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


class Server(ConfigBase):
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


class Worker(ConfigBase):
    name: str = Field("", title="Name of the worker instance")
    num_processes: int = Field(
        default=1,
        title="Number of simultanous workers",
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
    max_failure_pressure: float = Field(
        default=0.5,
        title="Max failure pressure",
        description=(
            "The maximum allowed failure pressure.\n"
            "If the failure pressure exceed this value then\n"
            "the service will exit with critical error condition."
        ),
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

        confservice.add_section("server", Server)
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

"""Offline mobile dictionary package: SQLite schema + export from Postgres."""

from .export import export_mobile_package
from .schema import SCHEMA_VERSION

__all__ = ["SCHEMA_VERSION", "export_mobile_package"]

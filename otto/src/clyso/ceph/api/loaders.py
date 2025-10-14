"""Data loading functions for Ceph data from files and stdin."""

import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ._json_utils import parse_ceph_json
from .schemas import CephReport, OSDPerfDumpResponse, OSDTree, PGDump


class DataLoadingError(Exception):
    """Raised when data cannot be loaded or validated."""

    pass


def load_ceph_report(file_path: str) -> CephReport:
    """Load Ceph report from JSON file."""
    try:
        content = Path(file_path).read_text()
        raw_data = parse_ceph_json(content)
        return CephReport.model_validate(raw_data)
    except FileNotFoundError:
        raise DataLoadingError(f"Ceph report file '{file_path}' not found")
    except ValidationError as e:
        raise DataLoadingError(
            f"Invalid ceph report structure in '{file_path}': {e}"
        ) from e
    except Exception as e:
        raise DataLoadingError(
            f"Failed to parse ceph report from '{file_path}': {e}"
        ) from e


def load_osd_tree(file_path: str) -> OSDTree:
    """Load OSD tree from JSON file."""
    try:
        content = Path(file_path).read_text()
        raw_data = parse_ceph_json(content)
        return OSDTree.model_validate(raw_data)
    except FileNotFoundError:
        raise DataLoadingError(f"OSD tree file '{file_path}' not found")
    except ValidationError as e:
        raise DataLoadingError(
            f"Invalid OSD tree structure in '{file_path}': {e}"
        ) from e
    except Exception as e:
        raise DataLoadingError(
            f"Failed to parse OSD tree from '{file_path}': {e}"
        ) from e


def load_pg_dump(file_path: str) -> PGDump:
    """Load PG dump from JSON file."""
    try:
        content = Path(file_path).read_text()
        raw_data = parse_ceph_json(content)
        return PGDump.model_validate(raw_data)
    except FileNotFoundError:
        raise DataLoadingError(f"PG dump file '{file_path}' not found")
    except ValidationError as e:
        raise DataLoadingError(
            f"Invalid PG dump structure in '{file_path}': {e}"
        ) from e
    except Exception as e:
        raise DataLoadingError(
            f"Failed to parse PG dump from '{file_path}': {e}"
        ) from e


def load_config_dump(file_path: str) -> list[dict[str, Any]]:
    """Load config dump from JSON file."""
    try:
        content = Path(file_path).read_text()
        raw_data = parse_ceph_json(content)
        if not isinstance(raw_data, list):
            raise DataLoadingError(
                f"Expected list for config dump, got {type(raw_data).__name__}"
            )
        return raw_data
    except FileNotFoundError:
        raise DataLoadingError(f"Config dump file '{file_path}' not found")
    except Exception as e:
        raise DataLoadingError(
            f"Failed to parse config dump from '{file_path}': {e}"
        ) from e


def load_osd_perf_from_file(file_path: str) -> OSDPerfDumpResponse:
    """Load OSD performance dump from JSON file."""
    try:
        content = Path(file_path).read_text()
        return OSDPerfDumpResponse.model_validate_json(content)
    except FileNotFoundError:
        raise DataLoadingError(f"Performance data file '{file_path}' not found")
    except ValidationError as e:
        raise DataLoadingError(
            f"Invalid performance data structure in '{file_path}': {e}"
        ) from e


def load_osd_perf_from_stdin() -> OSDPerfDumpResponse:
    """Load OSD performance dump from stdin."""
    try:
        content = sys.stdin.read()
        return OSDPerfDumpResponse.model_validate_json(content)
    except ValidationError as e:
        raise DataLoadingError(
            f"Invalid performance data structure from stdin: {e}"
        ) from e

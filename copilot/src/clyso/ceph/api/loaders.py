"""
Data loading functions for Ceph data from files and stdin.
"""

import sys
from pathlib import Path
from pydantic import ValidationError

from .schemas import OSDPerfDumpResponse


class DataLoadingError(Exception):
    """Raised when performance data cannot be loaded or validated."""

    pass


def load_osd_perf_from_file(file_path: str) -> OSDPerfDumpResponse:
    """Load OSD performance dump from JSON file"""
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
    """Load OSD performance dump from stdin"""
    try:
        content = sys.stdin.read()
        return OSDPerfDumpResponse.model_validate_json(content)
    except ValidationError as e:
        raise DataLoadingError(
            f"Invalid performance data structure from stdin: {e}"
        ) from e

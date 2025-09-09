# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Data loading functions for Ceph data from files and stdin.
"""

import json
import sys
from typing import Any
from pydantic import ValidationError

from .schemas import OSDPerfDumpResponse


class DataLoadingError(Exception):
    """Raised when performance data cannot be loaded or validated."""

    pass


def load_osd_perf_from_file(file_path: str) -> OSDPerfDumpResponse:
    """Load OSD performance dump from JSON file"""
    try:
        with open(file_path, "r") as f:
            raw_data = json.load(f)
        return OSDPerfDumpResponse.model_validate(raw_data)
    except FileNotFoundError:
        raise DataLoadingError(f"Performance data file '{file_path}' not found")
    except json.JSONDecodeError as e:
        raise DataLoadingError(f"Invalid JSON in file '{file_path}': {e}") from e
    except ValidationError as e:
        raise DataLoadingError(
            f"Invalid performance data structure in '{file_path}': {e}"
        ) from e


def load_osd_perf_from_stdin() -> OSDPerfDumpResponse:
    """Load OSD performance dump from stdin"""
    try:
        content = sys.stdin.read()
        raw_data = json.loads(content)
        return OSDPerfDumpResponse.model_validate(raw_data)
    except json.JSONDecodeError as e:
        raise DataLoadingError(f"Invalid JSON from stdin: {e}") from e
    except ValidationError as e:
        raise DataLoadingError(
            f"Invalid performance data structure from stdin: {e}"
        ) from e

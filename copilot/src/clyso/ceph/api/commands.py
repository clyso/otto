"""
Typed wrapper functions for Ceph JSON commands.

This module provides strongly-typed wrapper functions for executing Ceph commands
and parsing their JSON output with proper validation using Pydantic models.
"""

import json
import subprocess
import os
import sys
import math
from typing import Any

from .schemas import (
    OSDTree,
    PGDump,
    OSDDFResponse,
    OSDDumpResponse,
    OSDPerfDumpResponse,
    MalformedCephDataError,
)


def _json_loads(json_data: str) -> Any:
    """Parse JSON data"""

    def parse_json_constants(arg):
        if arg == "Infinity":
            return math.inf
        elif arg == "-Infinity":
            return -math.inf
        elif arg == "NaN":
            return math.nan
        return None

    # some ceph data returns non-valid json
    # Replace " inf," with " Infinity," to avoid json parsing error:
    # python json module does not support "inf", "-inf", "nan" as valid
    # json constants
    json_data = json_data.replace(" inf,", " Infinity,")
    json_data = json_data.replace(" -inf,", " -Infinity,")
    json_data = json_data.replace(" nan,", " NaN,")

    return json.loads(json_data, parse_constant=parse_json_constants)


def _execute_ceph_command(
    command: str, timeout: int = 30, skip_confirmation: bool = True
) -> Any:
    if not skip_confirmation:
        try:
            response = input(f"+ {command} [y/n]: ").strip().lower()
            if response not in ("y", "yes"):
                print("Command execution cancelled by user.")
                sys.exit(1)
        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled by user.")
            sys.exit(1)

    try:
        with open(os.devnull, "w") as devnull:
            out = subprocess.check_output(
                command.split(), stderr=devnull, timeout=timeout
            ).decode("utf-8")
    except subprocess.CalledProcessError:
        print("ERROR: ceph command is no where to be found")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"ERROR: command '{command}' timed out after {timeout} seconds")
        sys.exit(1)
    return _json_loads(out)


def ceph_osd_tree(skip_confirmation: bool = True) -> OSDTree:
    try:
        raw_data = _execute_ceph_command(
            "ceph osd tree --format=json", skip_confirmation=skip_confirmation
        )
        return OSDTree.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get OSD tree: {e}") from e


def ceph_pg_dump(skip_confirmation: bool = True) -> PGDump:
    try:
        raw_data = _execute_ceph_command(
            "ceph pg dump --format=json", skip_confirmation=skip_confirmation
        )
        return PGDump.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get PG dump: {e}") from e


def ceph_osd_perf_dump(
    osd_id: int, skip_confirmation: bool = True
) -> OSDPerfDumpResponse:
    try:
        raw_data = _execute_ceph_command(
            f"ceph tell osd.{osd_id} perf dump", skip_confirmation=skip_confirmation
        )
        return OSDPerfDumpResponse(**raw_data)
    except Exception as e:
        raise MalformedCephDataError(
            f"Failed to get OSD {osd_id} perf dump: {e}"
        ) from e


def ceph_report(skip_confirmation: bool = True) -> dict[str, Any]:
    try:
        raw_data = _execute_ceph_command(
            "ceph report", skip_confirmation=skip_confirmation
        )
        return raw_data
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get cluster report: {e}") from e


def ceph_osd_df(skip_confirmation: bool = True) -> OSDDFResponse:
    try:
        raw_data = _execute_ceph_command(
            "ceph osd df --format=json", skip_confirmation=skip_confirmation
        )
        return OSDDFResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get OSD DF: {e}") from e


def ceph_osd_dump(skip_confirmation: bool = True) -> OSDDumpResponse:
    try:
        raw_data = _execute_ceph_command(
            "ceph osd dump --format=json", skip_confirmation=skip_confirmation
        )
        return OSDDumpResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get OSD dump: {e}") from e


def ceph_command(
    command: str, timeout: int = 30, skip_confirmation: bool = True
) -> dict[str, Any]:
    try:
        raw_data = _execute_ceph_command(
            command, timeout=timeout, skip_confirmation=skip_confirmation
        )
        return raw_data
    except Exception as e:
        raise MalformedCephDataError(
            f"Failed to execute command '{command}': {e}"
        ) from e

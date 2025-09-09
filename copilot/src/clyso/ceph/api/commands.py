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
from typing import Any, Dict

from .schemas import (
    OSDTree,
    PGDump,
    OSDDFResponse,
    OSDDumpResponse,
    OSDPerfDumpResponse,
    MalformedCephDataError,
)


def _json_loads(json_data: str) -> Any:
    """Parse JSON data with support for Ceph's non-standard constants."""

    def parse_json_constants(arg):
        if arg == "Infinity":
            return math.inf
        elif arg == "-Infinity":
            return -math.inf
        elif arg == "NaN":
            return math.nan
        return None

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
    """Execute a Ceph command and return JSON output with optional interactive confirmation.

    Args:
        command: The ceph command to execute
        timeout: Command timeout in seconds
        skip_confirmation: If True, skip interactive confirmation

    Returns:
        Parsed JSON output from the command
    """
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
    """
    Get OSD tree structure with proper typing and validation.

    Args:
        skip_confirmation: If True, skip interactive confirmation

    Returns:
        Validated OSD tree structure containing nodes and stray OSDs

    Raises:
        MalformedCephDataError: If the response cannot be parsed or validated
    """
    try:
        raw_data = _execute_ceph_command(
            "ceph osd tree --format=json", skip_confirmation=skip_confirmation
        )
        return OSDTree.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get OSD tree: {e}") from e


def ceph_pg_dump(skip_confirmation: bool = True) -> PGDump:
    """
    Get placement group dump with proper typing and validation.

    Args:
        skip_confirmation: If True, skip interactive confirmation

    Returns:
        Validated PG dump containing pg_map with statistics and state information

    Raises:
        MalformedCephDataError: If the response cannot be parsed or validated
    """
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
    """
    Get OSD performance dump for a specific OSD with proper typing and validation.

    Args:
        osd_id: The ID of the OSD to get performance data for
        skip_confirmation: If True, skip interactive confirmation

    Returns:
        Validated OSD performance dump containing BlueStore, BlueFS, and other metrics

    Raises:
        MalformedCephDataError: If the response cannot be parsed or validated
    """
    try:
        raw_data = _execute_ceph_command(
            f"ceph tell osd.{osd_id} perf dump", skip_confirmation=skip_confirmation
        )
        return OSDPerfDumpResponse(**raw_data)
    except Exception as e:
        raise MalformedCephDataError(
            f"Failed to get OSD {osd_id} perf dump: {e}"
        ) from e


def ceph_report(skip_confirmation: bool = True) -> Dict[str, Any]:
    """
    Get full Ceph cluster report.

    Args:
        skip_confirmation: If True, skip interactive confirmation

    Returns:
        Raw cluster report data as dictionary

    Raises:
        MalformedCephDataError: If the response cannot be parsed or validated
    """
    try:
        raw_data = _execute_ceph_command(
            "ceph report", skip_confirmation=skip_confirmation
        )
        return raw_data
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get cluster report: {e}") from e


def ceph_osd_df(skip_confirmation: bool = True) -> OSDDFResponse:
    """
    Get OSD disk usage information with proper typing and validation.

    Args:
        skip_confirmation: If True, skip interactive confirmation

    Returns:
        Validated OSD disk usage data containing utilization and capacity info

    Raises:
        MalformedCephDataError: If the response cannot be parsed or validated
    """
    try:
        raw_data = _execute_ceph_command(
            "ceph osd df --format=json", skip_confirmation=skip_confirmation
        )
        return OSDDFResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get OSD DF: {e}") from e


def ceph_osd_dump(skip_confirmation: bool = True) -> OSDDumpResponse:
    """
    Get comprehensive OSD configuration dump with proper typing and validation.

    Args:
        skip_confirmation: If True, skip interactive confirmation

    Returns:
        Validated OSD dump containing cluster configuration and pool settings

    Raises:
        MalformedCephDataError: If the response cannot be parsed or validated
    """
    try:
        raw_data = _execute_ceph_command(
            "ceph osd dump --format=json", skip_confirmation=skip_confirmation
        )
        return OSDDumpResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get OSD dump: {e}") from e


def ceph_command(
    command: str, timeout: int = 30, skip_confirmation: bool = True
) -> Dict[str, Any]:
    """
    Execute a generic Ceph command and return JSON output.

    Args:
        command: The ceph command to execute
        timeout: Command timeout in seconds
        skip_confirmation: If True, skip interactive confirmation

    Returns:
        Parsed JSON output from the command

    Raises:
        MalformedCephDataError: If the response cannot be parsed or validated
    """
    try:
        raw_data = _execute_ceph_command(
            command, timeout=timeout, skip_confirmation=skip_confirmation
        )
        return raw_data
    except Exception as e:
        raise MalformedCephDataError(
            f"Failed to execute command '{command}': {e}"
        ) from e

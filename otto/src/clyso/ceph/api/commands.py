# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Typed wrapper functions for Ceph JSON commands.

This module provides strongly-typed wrapper functions for executing Ceph commands
and parsing their JSON output with proper validation using Pydantic models.
"""

import subprocess
import sys
from typing import Any

from ._json_utils import parse_ceph_json
from .schemas import (
    CephReport,
    MalformedCephDataError,
    OSDDFResponse,
    OSDDumpResponse,
    OSDPerfDumpResponse,
    OSDTree,
    PGDump,
    CephfsStatusResponse,
    CephfsMDSStatResponse,
    CephfsSessionListResponse,
)


def _execute_ceph_command(command: str, timeout: int = 30) -> Any:
    try:
        out = subprocess.check_output(
            command.split(), stderr=subprocess.DEVNULL, timeout=timeout
        ).decode("utf-8")
    except subprocess.CalledProcessError:
        print("ERROR: ceph command is no where to be found")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"ERROR: command '{command}' timed out after {timeout} seconds")
        sys.exit(1)
    return parse_ceph_json(out)


def ceph_osd_tree() -> OSDTree:
    try:
        raw_data = _execute_ceph_command("ceph osd tree --format=json")
        return OSDTree.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get OSD tree: {e}") from e


def ceph_pg_dump() -> PGDump:
    try:
        raw_data = _execute_ceph_command("ceph pg dump --format=json")
        return PGDump.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get PG dump: {e}") from e


def ceph_osd_perf_dump(osd_id: int) -> OSDPerfDumpResponse:
    try:
        raw_data = _execute_ceph_command(f"ceph tell osd.{osd_id} perf dump")
        return OSDPerfDumpResponse(**raw_data)
    except Exception as e:
        raise MalformedCephDataError(
            f"Failed to get OSD {osd_id} perf dump: {e}"
        ) from e


def ceph_report() -> CephReport:
    try:
        raw_data = _execute_ceph_command("ceph report")
        return CephReport.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get cluster report: {e}") from e


def ceph_osd_df() -> OSDDFResponse:
    try:
        raw_data = _execute_ceph_command("ceph osd df --format=json")
        return OSDDFResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get OSD DF: {e}") from e


def ceph_osd_dump() -> OSDDumpResponse:
    try:
        raw_data = _execute_ceph_command("ceph osd dump --format=json")
        return OSDDumpResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get OSD dump: {e}") from e


def ceph_command(command: str, timeout: int = 30) -> dict[str, Any]:
    try:
        raw_data = _execute_ceph_command(command, timeout=timeout)
        return raw_data
    except Exception as e:
        raise MalformedCephDataError(
            f"Failed to execute command '{command}': {e}"
        ) from e


def ceph_fs_status(fs_name: str | None = None) -> CephfsStatusResponse:
    try:
        if fs_name:
            command = f"ceph fs status {fs_name} --format=json".strip()
        else:
            command = "ceph fs status --format=json".strip()

        raw_data = _execute_ceph_command(command)
        return CephfsStatusResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get CephFS status: {e}") from e


def ceph_mds_stat(mds_name: str = "") -> CephfsMDSStatResponse:
    try:
        command = f"ceph mds stat {mds_name} --format=json".strip()
        raw_data = _execute_ceph_command(command)
        return CephfsMDSStatResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get MDS stat: {e}") from e


def ceph_mds_session_ls(mds_name: str = "") -> CephfsSessionListResponse:
    """Get CephFS session list from MDS daemon."""
    try:
        raw_data = _execute_ceph_command(
            f"ceph tell mds.{mds_name} session ls --format=json"
        )
        return CephfsSessionListResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get MDS session list: {e}") from e

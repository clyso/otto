# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Typed wrapper functions for Ceph JSON commands.

This module provides strongly-typed wrapper functions for executing Ceph commands
and parsing their JSON output with proper validation using Pydantic models.
"""

import sys
from typing import Any
import subprocess
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
    RGWZoneResponse,
    RGWBucketListResponse,
    RGWBucketObjectListResponse,
    CrushMap,
    RGWZonegroupResponse,
    RGWBucketStatsResponse,
    RGWGlobalQuotaResponse,
    RGWUserListResponse,
    RGWUserInfoResponse,
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


def radosgw_admin_zone_get() -> RGWZoneResponse:
    try:
        raw_data = _execute_ceph_command("radosgw-admin zone get --format=json")
        return RGWZoneResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get RGW zone: {e}") from e


def radosgw_admin_bucket_list() -> RGWBucketListResponse:
    try:
        raw_data = _execute_ceph_command("radosgw-admin bucket list --format=json")
        return RGWBucketListResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get RGW bucket list: {e}") from e


def radosgw_admin_bucket_radoslist(bucket: str) -> list[str]:
    """
    Get list of RADOS object names for a bucket.

    Note: This command returns plain text (one object per line), not JSON.
    """
    try:
        cmd = f"radosgw-admin bucket radoslist --bucket {bucket}"
        out = subprocess.check_output(
            cmd.split(), stderr=subprocess.DEVNULL, timeout=30
        ).decode("utf-8")

        rados_objects = [line.strip() for line in out.splitlines() if line.strip()]
        return rados_objects

    except subprocess.CalledProcessError as e:
        raise MalformedCephDataError(
            f"Failed to get RADOS object list for bucket {bucket}: {e}"
        ) from e
    except subprocess.TimeoutExpired:
        raise MalformedCephDataError(
            f"Command 'radosgw-admin bucket radoslist' timed out for bucket {bucket}"
        )


def radosgw_admin_bucket_list_objects(bucket: str) -> RGWBucketObjectListResponse:
    """Get detailed object list for a specific bucket."""
    try:
        raw_data = _execute_ceph_command(
            f"radosgw-admin bucket list --bucket {bucket} --format=json"
        )
        return RGWBucketObjectListResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(
            f"Failed to get bucket object list for {bucket}: {e}"
        ) from e


def ceph_osd_crush_dump() -> CrushMap:
    """Get CRUSH map dump."""
    try:
        raw_data = _execute_ceph_command("ceph osd crush dump --format=json")
        return CrushMap.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get CRUSH map: {e}") from e


def radosgw_admin_zone_get_by_id(zone_id: str) -> RGWZoneResponse:
    """Get RGW zone configuration by zone ID."""
    try:
        raw_data = _execute_ceph_command(
            f"radosgw-admin zone get --zone-id {zone_id} --format=json"
        )
        return RGWZoneResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get RGW zone {zone_id}: {e}") from e


def radosgw_admin_zonegroup_get(zonegroup_id: str) -> RGWZonegroupResponse:
    """Get RGW zonegroup configuration."""
    try:
        raw_data = _execute_ceph_command(
            f"radosgw-admin zonegroup get --zonegroup-id {zonegroup_id} --format=json"
        )
        return RGWZonegroupResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(
            f"Failed to get RGW zonegroup {zonegroup_id}: {e}"
        ) from e


def radosgw_admin_bucket_stats(
    user: str, max_entries: int = 2147483647
) -> RGWBucketStatsResponse:
    """Get bucket statistics for a user."""
    try:
        raw_data = _execute_ceph_command(
            f"radosgw-admin bucket stats --uid {user} --max-entries {max_entries} --format=json"
        )
        return RGWBucketStatsResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(
            f"Failed to get bucket stats for user {user}: {e}"
        ) from e


def radosgw_admin_global_quota_get() -> RGWGlobalQuotaResponse:
    """Get global quota settings."""
    try:
        raw_data = _execute_ceph_command("radosgw-admin global quota get --format=json")
        return RGWGlobalQuotaResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get global quota: {e}") from e


def radosgw_admin_user_list() -> RGWUserListResponse:
    """Get list of all RGW users."""
    try:
        raw_data = _execute_ceph_command("radosgw-admin user list --format=json")
        return RGWUserListResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get user list: {e}") from e


def radosgw_admin_user_info(user: str) -> RGWUserInfoResponse:
    """Get user information."""
    try:
        raw_data = _execute_ceph_command(
            f"radosgw-admin user info --uid {user} --format=json"
        )
        return RGWUserInfoResponse.model_validate(raw_data)
    except Exception as e:
        raise MalformedCephDataError(f"Failed to get user info for {user}: {e}") from e

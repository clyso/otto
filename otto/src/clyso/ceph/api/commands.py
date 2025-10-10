# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Typed wrapper functions for Ceph JSON commands.

This module provides strongly-typed wrapper functions for executing Ceph commands
and parsing their JSON output with proper validation using Pydantic models.
"""

import json
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
    PGStat,
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

class CephConnection:
    """
    Connection wrapper for Ceph cluster commands.
    
    Supports both rados library (fast, direct) and shell commands (fallback).
    Automatically detects and uses rados if available.
    """

    def __init__(self, conffile: str = "/etc/ceph/ceph.conf"):
        """
        Initialize connection to Ceph cluster.
        
        Args:
            conffile: Path to ceph.conf file
        """
        self.use_rados = False
        self.cluster = None
        self.conffile = conffile

        try:
            import rados  # type: ignore

            self.cluster = rados.Rados(conffile=conffile)
            self.cluster.connect()
            self.use_rados = True
        except (ImportError, Exception):
            self.use_rados = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the connection if using rados."""
        if self.cluster:
            try:
                self.cluster.shutdown()
            except Exception:
                pass

    def _execute_mon_command(self, cmd: dict[str, Any], timeout: int = 5) -> str:
        """Execute a monitor command via rados or shell."""
        if self.use_rados and self.cluster:
            ret, output, errs = self.cluster.mon_command(
                json.dumps(cmd), b"", timeout=timeout
            )
            return output.decode("utf-8").strip()
        else:
            prefix = cmd.get("prefix", "")
            format_arg = cmd.get("format", "json")
            states = cmd.get("states", [])
            detail = cmd.get("detail", "")

            shell_cmd = f"ceph {prefix}"
            if states:
                shell_cmd += f" {' '.join(states)}"
            if detail:
                shell_cmd += f" {detail}"
            shell_cmd += f" -f {format_arg}"

            try:
                result = subprocess.getoutput(shell_cmd)
                return result
            except Exception as e:
                raise MalformedCephDataError(
                    f"Failed to execute shell command '{shell_cmd}': {e}"
                ) from e

    def get_osd_list(self) -> list[int]:
        """Get list of all OSD IDs."""
        cmd = {"prefix": "osd ls", "format": "json"}
        output = self._execute_mon_command(cmd)
        return json.loads(output)

    def get_osd_df(self) -> OSDDFResponse:
        """Get OSD disk usage information."""
        cmd = {"prefix": "osd df", "format": "json"}
        output = self._execute_mon_command(cmd)
        data = json.loads(output)
        return OSDDFResponse.model_validate(data)

    def get_osd_dump(self) -> OSDDumpResponse:
        """Get OSD map dump including pg_upmap_items."""
        cmd = {"prefix": "osd dump", "format": "json"}
        output = self._execute_mon_command(cmd)
        data = json.loads(output)
        return OSDDumpResponse.model_validate(data)

    def get_remapped_pgs(self) -> list[PGStat]:
        """Get list of PGs in remapped state."""
        cmd = {"prefix": "pg ls", "states": ["remapped"], "format": "json"}
        output = self._execute_mon_command(cmd)
        
        try:
            data = json.loads(output)
            pg_stats = data.get("pg_stats", [])
            if not pg_stats:
                return []
            return [PGStat.model_validate(pg) for pg in pg_stats]
        except (KeyError, json.JSONDecodeError):
            return []

    def get_pool_types(self) -> dict[str, str]:
        """
        Get mapping of pool name to pool type (replicated/erasure).
        
        Returns:
            Dict mapping pool name to "replicated" or "erasure"
        """
        if self.use_rados and self.cluster:
            cmd = {"prefix": "osd pool ls", "detail": "detail", "format": "plain"}
        else:
            cmd = {"prefix": "osd pool ls detail", "format": "plain"}

        output = self._execute_mon_command(cmd)
        
        pool_types = {}
        for line in output.split("
"):
            if "pool" in line:
                parts = line.split()
                if len(parts) >= 4:
                    pool_name = parts[1].strip("'")
                    pool_type = parts[3]
                    pool_types[pool_name] = pool_type
        
        return pool_types

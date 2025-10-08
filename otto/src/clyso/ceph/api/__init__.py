"""
Ceph API module providing typed wrapper functions for Ceph JSON commands.

This module exposes typed interfaces for common Ceph commands

Example usage:
    from clyso.ceph.api import ceph_osd_tree, ceph_pg_dump

    osd_tree = ceph_osd_tree()
    for node in osd_tree["nodes"]:
        if node["type"] == "osd":
            print(f"OSD {node['id']}: {node['status']}")

    or

    pg_dump = ceph_pg_dump()
    pg_stats = pg_dump["pg_map"]["pg_stats_sum"]
    print(f"Total objects: {pg_stats['stat_sum']['num_objects']}")
"""

from .commands import (
    ceph_osd_df,
    ceph_osd_dump,
    ceph_osd_tree,
    ceph_pg_dump,
    ceph_fs_status,
    ceph_mds_stat,
    ceph_mds_session_ls,
)
from .schemas import (
    OSDDFNode,
    OSDDFResponse,
    OSDDumpResponse,
    OSDNode,
    OSDTree,
    PGDump,
    PGMap,
    PGStat,
    PoolConfig,
    PoolStat,
    CephfsStatusResponse,
    CephfsMDSStatResponse,
    MDSInfo,
    FilesystemInfo,
    CephfsSession,
    CephfsSessionListResponse,
)

__all__ = [
    "OSDDFNode",
    "OSDDFResponse",
    "OSDDumpResponse",
    "OSDNode",
    # Schema classes
    "OSDTree",
    "PGDump",
    "PGMap",
    "PGStat",
    "PoolConfig",
    "PoolStat",
    "ceph_osd_df",
    "ceph_osd_dump",
    # Command functions
    "ceph_osd_tree",
    "ceph_pg_dump",
    "ceph_fs_status",
    "ceph_mds_stat",
    "ceph_mds_session_ls",
    "CephfsStatusResponse",
    "CephfsMDSStatResponse",
    "MDSInfo",
    "FilesystemInfo",
    "CephfsSession",
    "CephfsSessionListResponse",
]

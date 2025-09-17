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

from .commands import ceph_osd_tree, ceph_pg_dump, ceph_osd_df, ceph_osd_dump
from .schemas import (
    OSDTree,
    PGDump,
    OSDNode,
    PGMap,
    PGStat,
    PoolStat,
    OSDDFResponse,
    OSDDFNode,
    OSDDumpResponse,
    PoolConfig,
)

__all__ = [
    # Command functions
    "ceph_osd_tree",
    "ceph_pg_dump",
    "ceph_osd_df",
    "ceph_osd_dump",
    # Schema classes
    "OSDTree",
    "PGDump",
    "OSDNode",
    "PGMap",
    "PGStat",
    "PoolStat",
    "OSDDFResponse",
    "OSDDFNode",
    "OSDDumpResponse",
    "PoolConfig",
]

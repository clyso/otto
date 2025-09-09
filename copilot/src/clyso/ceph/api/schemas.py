"""
Pydantic schemas for Ceph JSON API responses.

This module provides typed interfaces for Ceph command JSON outputs,
enabling better type checking and IntelliSense support with validation.
"""
# NOTE: pydantic makes basedpyright complain about 'Any' when using Field
# defaults. Disable 'reportAny' temporarily.
#
# pyright: reportAny=false
# pyright: reportExplicitAny=false

from __future__ import annotations

import pathlib
from typing import Any

from pydantic import BaseModel, Field


class MalformedCephDataError(Exception):
    """Raised when Ceph JSON data cannot be parsed or validated."""

    pass


class OpQueueAgeHist(BaseModel):
    """Schema for operation queue age histogram"""

    histogram: list[int]
    upper_bound: int


class PerfStat(BaseModel):
    """Schema for OSD performance statistics"""

    commit_latency_ms: int = 0
    apply_latency_ms: int = 0
    commit_latency_ns: int = 0
    apply_latency_ns: int = 0


class OSDNode(BaseModel):
    """Schema for an OSD node in the OSD tree"""

    id: int
    name: str
    type: str  # "root", "host", "osd"
    type_id: int
    children: list[int] = Field(default_factory=list)  # root and host nodes
    device_class: str | None = None  # osd nodes
    crush_weight: float | None = None  # osd nodes
    depth: int | None = None  # osd nodes
    pool_weights: dict[str, float] = Field(default_factory=dict)
    exists: int | None = None  # osd nodes (0 or 1)
    status: str | None = None  # osd nodes ("up", "down")
    reweight: float | None = None  # osd nodes
    primary_affinity: float | None = None  # osd nodes


class OSDTree(BaseModel):
    """Schema for 'ceph osd tree --format=json' response"""

    nodes: list[OSDNode]
    stray: list[Any] = Field(default_factory=list)

    @classmethod
    def loads(cls, raw: str) -> OSDTree:
        """Parse OSD tree from JSON string"""
        try:
            return cls.model_validate_json(raw)
        except Exception as e:
            raise MalformedCephDataError(f"Failed to parse OSD tree: {e}") from e

    @classmethod
    def load(cls, path: pathlib.Path) -> OSDTree:
        """Load and parse OSD tree from file"""
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        raw = path.read_text()
        return cls.loads(raw)


class PGStatSum(BaseModel):
    """Schema for PG statistics summary"""

    num_bytes: int = 0
    num_objects: int = 0
    num_object_clones: int = 0
    num_object_copies: int = 0
    num_objects_missing_on_primary: int = 0
    num_objects_missing: int = 0
    num_objects_degraded: int = 0
    num_objects_misplaced: int = 0
    num_objects_unfound: int = 0
    num_objects_dirty: int = 0
    num_whiteouts: int = 0
    num_read: int = 0
    num_read_kb: int = 0
    num_write: int = 0
    num_write_kb: int = 0
    num_scrub_errors: int = 0
    num_shallow_scrub_errors: int = 0
    num_deep_scrub_errors: int = 0
    num_objects_recovered: int = 0
    num_bytes_recovered: int = 0
    num_keys_recovered: int = 0
    num_objects_omap: int = 0
    num_objects_hit_set_archive: int = 0
    num_bytes_hit_set_archive: int = 0
    num_flush: int = 0
    num_flush_kb: int = 0
    num_evict: int = 0
    num_evict_kb: int = 0
    num_promote: int = 0
    num_flush_mode_high: int = 0
    num_flush_mode_low: int = 0
    num_evict_mode_some: int = 0
    num_evict_mode_full: int = 0
    num_objects_pinned: int = 0
    num_legacy_snapsets: int = 0
    num_large_omap_objects: int = 0
    num_objects_manifest: int = 0
    num_omap_bytes: int = 0
    num_omap_keys: int = 0
    num_objects_repaired: int = 0


class PGStoreStats(BaseModel):
    """Schema for PG store statistics"""

    total: int = 0
    available: int = 0
    internally_reserved: int = 0
    allocated: int = 0
    data_stored: int = 0
    data_compressed: int = 0
    data_compressed_allocated: int = 0
    data_compressed_original: int = 0
    omap_allocated: int = 0
    internal_metadata: int = 0


class PGStatsSum(BaseModel):
    """Schema for PG stats summary"""

    stat_sum: PGStatSum
    store_stats: PGStoreStats
    log_size: int = 0
    ondisk_log_size: int = 0
    up: int = 0
    acting: int = 0
    num_store_stats: int = 0


class PGStatsDelta(BaseModel):
    """Schema for PG stats delta"""

    stat_sum: PGStatSum
    store_stats: PGStoreStats
    log_size: int = 0
    ondisk_log_size: int = 0
    up: int = 0
    acting: int = 0
    num_store_stats: int = 0
    stamp_delta: str


class PGStat(BaseModel):
    """Schema for individual PG statistics"""

    pgid: str
    version: str
    reported_seq: int
    reported_epoch: int
    state: str
    last_fresh: str
    last_change: str
    last_active: str
    last_peered: str
    last_clean: str
    last_became_active: str
    last_became_peered: str
    last_unstale: str
    last_undegraded: str
    last_fullsized: str
    mapping_epoch: int
    log_start: str
    ondisk_log_start: str
    created: int
    last_epoch_clean: int
    parent: str
    parent_split_bits: int
    last_scrub: str
    last_scrub_stamp: str
    last_deep_scrub: str
    last_deep_scrub_stamp: str
    last_clean_scrub_stamp: str
    objects_scrubbed: int
    log_size: int
    log_dups_size: int
    ondisk_log_size: int
    stats_invalid: bool
    dirty_stats_invalid: bool
    omap_stats_invalid: bool
    hitset_stats_invalid: bool
    hitset_bytes_stats_invalid: bool
    pin_stats_invalid: bool
    manifest_stats_invalid: bool
    snaptrimq_len: int
    last_scrub_duration: int
    scrub_schedule: str
    scrub_duration: float
    objects_trimmed: int
    snaptrim_duration: int
    stat_sum: PGStatSum
    up: list[int]
    acting: list[int]
    avail_no_missing: list[Any] = Field(default_factory=list)
    object_location_counts: list[Any] = Field(default_factory=list)
    blocked_by: list[Any] = Field(default_factory=list)
    up_primary: int
    acting_primary: int
    purged_snaps: list[Any] = Field(default_factory=list)


class OSDStat(BaseModel):
    """Schema for individual OSD statistics"""

    osd: int
    up_from: int = 0
    seq: int = 0
    num_pgs: int = 0
    num_osds: int = 1  # this appears to always be 1 for individual OSD stats
    num_per_pool_osds: int = 0
    num_per_pool_omap_osds: int = 0
    kb: int = 0
    kb_used: int = 0
    kb_used_data: int = 0
    kb_used_omap: int = 0
    kb_used_meta: int = 0
    kb_avail: int = 0
    statfs: dict[str, int] = Field(default_factory=dict)
    hb_peers: list[int] = Field(default_factory=list)
    snap_trim_queue_len: int = 0
    num_snap_trimming: int = 0
    num_shards_repaired: int = 0
    op_queue_age_hist: OpQueueAgeHist
    perf_stat: PerfStat
    alerts: list[Any] = Field(default_factory=list)
    network_ping_times: list[Any] = Field(default_factory=list)


class OSDStatsSum(BaseModel):
    """Schema for aggregated OSD statistics summary"""

    up_from: int = 0
    seq: int = 0
    num_pgs: int = 0
    num_osds: int = 0
    num_per_pool_osds: int = 0
    num_per_pool_omap_osds: int = 0
    kb: int = 0
    kb_used: int = 0
    kb_used_data: int = 0
    kb_used_omap: int = 0
    kb_used_meta: int = 0
    kb_avail: int = 0
    statfs: dict[str, int] = Field(default_factory=dict)
    hb_peers: list[int] = Field(default_factory=list)
    snap_trim_queue_len: int = 0
    num_snap_trimming: int = 0
    num_shards_repaired: int = 0
    op_queue_age_hist: OpQueueAgeHist
    perf_stat: PerfStat
    alerts: list[Any] = Field(default_factory=list)
    network_ping_times: list[Any] = Field(default_factory=list)


class PoolStatfs(BaseModel):
    """Schema for pool statfs entries"""

    poolid: int
    osd: int
    total: int = 0
    available: int = 0
    internally_reserved: int = 0
    allocated: int = 0
    data_stored: int = 0
    data_compressed: int = 0
    data_compressed_allocated: int = 0
    data_compressed_original: int = 0
    omap_allocated: int = 0
    internal_metadata: int = 0


class PoolStat(BaseModel):
    """Schema for pool statistics"""

    poolid: int
    num_pg: int = 0
    stat_sum: PGStatSum
    store_stats: PGStoreStats | None = None
    log_size: int = 0
    ondisk_log_size: int = 0
    up: int = 0
    acting: int = 0
    num_store_stats: int = 0


class PGMap(BaseModel):
    """Schema for PG map"""

    version: int
    stamp: str
    last_osdmap_epoch: int = 0
    last_pg_scan: int = 0
    pg_stats_sum: PGStatsSum
    osd_stats_sum: OSDStatsSum
    pg_stats_delta: PGStatsDelta
    pg_stats: list[PGStat] = Field(default_factory=list)
    pool_stats: list[PoolStat] = Field(default_factory=list)
    osd_stats: list[OSDStat] = Field(default_factory=list)
    pool_statfs: list[PoolStatfs] = Field(default_factory=list)


class PGDump(BaseModel):
    """Schema for 'ceph pg dump --format=json' response"""

    pg_ready: bool
    pg_map: PGMap

    @classmethod
    def loads(cls, raw: str) -> PGDump:
        """Parse PG dump from JSON string"""
        try:
            return cls.model_validate_json(raw)
        except Exception as e:
            raise MalformedCephDataError(f"Failed to parse PG dump: {e}") from e

    @classmethod
    def load(cls, path: pathlib.Path) -> PGDump:
        """Load and parse PG dump from file"""
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        raw = path.read_text()
        return cls.loads(raw)


# Rebuild models to resolve forward references
OSDTree.model_rebuild()
PGDump.model_rebuild()

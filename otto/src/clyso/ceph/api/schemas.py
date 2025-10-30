# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Pydantic schemas for Ceph JSON API responses.

This module provides typed interfaces for Ceph command JSON outputs,
enabling better type checking and IntelliSense support with validation.

This schema handles different ceph versions

Older Ceph versions may not have newer metrics/fields so we put | None
- field: Type | None = None

Newer Ceph versions may add metrics not yet in our schema and allows parsing to succeed even when fields are missing
so we add this option
model_config = {"extra": "allow"}
"""
# Basedpyright Any type warnings are suppressed for this file
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportExplicitAny=false

from __future__ import annotations

import pathlib
from typing import Any, Optional

from pydantic import BaseModel, Field, RootModel


class MalformedCephDataError(Exception):
    """Raised when Ceph JSON data cannot be parsed or validated."""

    pass


class OpQueueAgeHist(BaseModel):
    """Schema for operation queue age histogram."""

    histogram: list[int]
    upper_bound: int = Field(default=0)


class PerfStat(BaseModel):
    """Schema for OSD performance statistics."""

    commit_latency_ms: int = Field(default=0)
    apply_latency_ms: int = Field(default=0)
    commit_latency_ns: int = Field(default=0)
    apply_latency_ns: int = Field(default=0)


class OSDNode(BaseModel):
    """Schema for an OSD node in the OSD tree."""

    id: int = Field(default=0)
    name: str = Field(default="")
    type: str = Field(default="")
    type_id: int = Field(default=0)
    children: list[int] = Field(default_factory=list)
    device_class: str | None = Field(default=None)
    crush_weight: float | None = Field(default=None)
    depth: int | None = Field(default=None)
    pool_weights: dict[str, float] = Field(default_factory=dict)
    exists: int | None = Field(default=None)
    status: str | None = Field(default=None)
    reweight: float | None = Field(default=None)
    primary_affinity: float | None = Field(default=None)


class OSDTree(BaseModel):
    """Schema for `ceph osd tree --format=json` response."""

    model_config = {"extra": "allow"}

    nodes: list[OSDNode]
    stray: list[Any] = Field(default_factory=list)

    @classmethod
    def loads(cls, raw: str) -> OSDTree:
        """Parse OSD tree from JSON string."""
        try:
            return cls.model_validate_json(raw)
        except Exception as e:
            raise MalformedCephDataError(f"Failed to parse OSD tree: {e}") from e

    @classmethod
    def load(cls, path: pathlib.Path) -> OSDTree:
        """Load and parse OSD tree from file."""
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        raw = path.read_text()
        return cls.loads(raw)


class PGStatSum(BaseModel):
    """Schema for PG statistics summary."""

    num_bytes: int = Field(default=0)
    num_objects: int = Field(default=0)
    num_object_clones: int = Field(default=0)
    num_object_copies: int = Field(default=0)
    num_objects_missing_on_primary: int = Field(default=0)
    num_objects_missing: int = Field(default=0)
    num_objects_degraded: int = Field(default=0)
    num_objects_misplaced: int = Field(default=0)
    num_objects_unfound: int = Field(default=0)
    num_objects_dirty: int = Field(default=0)
    num_whiteouts: int = Field(default=0)
    num_read: int = Field(default=0)
    num_read_kb: int = Field(default=0)
    num_write: int = Field(default=0)
    num_write_kb: int = Field(default=0)
    num_scrub_errors: int = Field(default=0)
    num_shallow_scrub_errors: int = Field(default=0)
    num_deep_scrub_errors: int = Field(default=0)
    num_objects_recovered: int = Field(default=0)
    num_bytes_recovered: int = Field(default=0)
    num_keys_recovered: int = Field(default=0)
    num_objects_omap: int = Field(default=0)
    num_objects_hit_set_archive: int = Field(default=0)
    num_bytes_hit_set_archive: int = Field(default=0)
    num_flush: int = Field(default=0)
    num_flush_kb: int = Field(default=0)
    num_evict: int = Field(default=0)
    num_evict_kb: int = Field(default=0)
    num_promote: int = Field(default=0)
    num_flush_mode_high: int = Field(default=0)
    num_flush_mode_low: int = Field(default=0)
    num_evict_mode_some: int = Field(default=0)
    num_evict_mode_full: int = Field(default=0)
    num_objects_pinned: int = Field(default=0)
    num_legacy_snapsets: int = Field(default=0)
    num_large_omap_objects: int = Field(default=0)
    num_objects_manifest: int = Field(default=0)
    num_omap_bytes: int = Field(default=0)
    num_omap_keys: int = Field(default=0)
    num_objects_repaired: int = Field(default=0)


class PGStoreStats(BaseModel):
    """Schema for PG store statistics."""

    total: int = Field(default=0)
    available: int = Field(default=0)
    internally_reserved: int = Field(default=0)
    allocated: int = Field(default=0)
    data_stored: int = Field(default=0)
    data_compressed: int = Field(default=0)
    data_compressed_allocated: int = Field(default=0)
    data_compressed_original: int = Field(default=0)
    omap_allocated: int = Field(default=0)
    internal_metadata: int = Field(default=0)


class PGStatsSum(BaseModel):
    """Schema for PG stats summary."""

    stat_sum: PGStatSum
    store_stats: PGStoreStats | None = None
    log_size: int = Field(default=0)
    ondisk_log_size: int = Field(default=0)
    up: int = Field(default=0)
    acting: int = Field(default=0)
    num_store_stats: int = Field(default=0)


class PGStatsDelta(BaseModel):
    """Schema for PG stats delta."""

    stat_sum: PGStatSum
    store_stats: PGStoreStats | None = None
    log_size: int = Field(default=0)
    ondisk_log_size: int = Field(default=0)
    up: int = Field(default=0)
    acting: int = Field(default=0)
    num_store_stats: int = Field(default=0)
    stamp_delta: str = Field(default="")


class PGStat(BaseModel):
    """Schema for individual PG statistics."""

    pgid: str = Field(default="")
    version: str = Field(default="")
    reported_seq: int = Field(default=0)
    reported_epoch: int = Field(default=0)
    state: str = Field(default="")
    last_fresh: str = Field(default="")
    last_change: str = Field(default="")
    last_active: str = Field(default="")
    last_peered: str = Field(default="")
    last_clean: str = Field(default="")
    last_became_active: str = Field(default="")
    last_became_peered: str = Field(default="")
    last_unstale: str = Field(default="")
    last_undegraded: str = Field(default="")
    last_fullsized: str = Field(default="")
    mapping_epoch: int = Field(default=0)
    log_start: str = Field(default="")
    ondisk_log_start: str = Field(default="")
    created: int = Field(default=0)
    last_epoch_clean: int = Field(default=0)
    parent: str = Field(default="")
    parent_split_bits: int = Field(default=0)
    last_scrub: str = Field(default="")
    last_scrub_stamp: str = Field(default="")
    last_deep_scrub: str = Field(default="")
    last_deep_scrub_stamp: str = Field(default="")
    last_clean_scrub_stamp: str = Field(default="")
    objects_scrubbed: int = Field(default=0)
    log_size: int = Field(default=0)
    log_dups_size: int = Field(default=0)
    ondisk_log_size: int = Field(default=0)
    stats_invalid: bool
    dirty_stats_invalid: bool
    omap_stats_invalid: bool
    hitset_stats_invalid: bool
    hitset_bytes_stats_invalid: bool
    pin_stats_invalid: bool
    manifest_stats_invalid: bool
    snaptrimq_len: int = Field(default=0)
    last_scrub_duration: int = Field(default=0)
    scrub_schedule: str = Field(default="")
    scrub_duration: float = Field(default=0.0)
    objects_trimmed: int = Field(default=0)
    snaptrim_duration: float = Field(default=0)
    stat_sum: PGStatSum
    up: list[int]
    acting: list[int]
    avail_no_missing: list[Any] = Field(default_factory=list)
    object_location_counts: list[Any] = Field(default_factory=list)
    blocked_by: list[Any] = Field(default_factory=list)
    up_primary: int = Field(default=0)
    acting_primary: int = Field(default=0)
    purged_snaps: list[Any] = Field(default_factory=list)


class OSDStat(BaseModel):
    """Schema for individual OSD statistics."""

    osd: int = Field(default=0)
    up_from: int = Field(default=0)
    seq: int = Field(default=0)
    num_pgs: int = Field(default=0)
    num_osds: int = Field(
        default=1
    )  # this appears to always be 1 for individual OSD stats
    num_per_pool_osds: int = Field(default=0)
    num_per_pool_omap_osds: int = Field(default=0)
    kb: int = Field(default=0)
    kb_used: int = Field(default=0)
    kb_used_data: int = Field(default=0)
    kb_used_omap: int = Field(default=0)
    kb_used_meta: int = Field(default=0)
    kb_avail: int = Field(default=0)
    statfs: dict[str, int] = Field(default_factory=dict)
    hb_peers: list[int] = Field(default_factory=list)
    snap_trim_queue_len: int = Field(default=0)
    num_snap_trimming: int = Field(default=0)
    num_shards_repaired: int = Field(default=0)
    op_queue_age_hist: OpQueueAgeHist | None = None
    perf_stat: PerfStat | None = None
    alerts: list[Any] = Field(default_factory=list)
    network_ping_times: list[Any] = Field(default_factory=list)


class OSDStatsSum(BaseModel):
    """Schema for aggregated OSD statistics summary."""

    up_from: int = Field(default=0)
    seq: int = Field(default=0)
    num_pgs: int = Field(default=0)
    num_osds: int = Field(default=0)
    num_per_pool_osds: int = Field(default=0)
    num_per_pool_omap_osds: int = Field(default=0)
    kb: int = Field(default=0)
    kb_used: int = Field(default=0)
    kb_used_data: int = Field(default=0)
    kb_used_omap: int = Field(default=0)
    kb_used_meta: int = Field(default=0)
    kb_avail: int = Field(default=0)
    statfs: dict[str, int] = Field(default_factory=dict)
    hb_peers: list[int] = Field(default_factory=list)
    snap_trim_queue_len: int = Field(default=0)
    num_snap_trimming: int = Field(default=0)
    num_shards_repaired: int = Field(default=0)
    op_queue_age_hist: OpQueueAgeHist | None = None
    perf_stat: PerfStat | None = None
    alerts: list[Any] = Field(default_factory=list)
    network_ping_times: list[Any] = Field(default_factory=list)


class PoolStatfs(BaseModel):
    """Schema for pool statfs entries."""

    poolid: int = Field(default=0)
    osd: int = Field(default=0)
    total: int = Field(default=0)
    available: int = Field(default=0)
    internally_reserved: int = Field(default=0)
    allocated: int = Field(default=0)
    data_stored: int = Field(default=0)
    data_compressed: int = Field(default=0)
    data_compressed_allocated: int = Field(default=0)
    data_compressed_original: int = Field(default=0)
    omap_allocated: int = Field(default=0)
    internal_metadata: int = Field(default=0)


class PoolStat(BaseModel):
    """Schema for pool statistics."""

    poolid: int = Field(default=0)
    num_pg: int = Field(default=0)
    stat_sum: PGStatSum
    store_stats: PGStoreStats | None = Field(default=None)
    log_size: int = Field(default=0)
    ondisk_log_size: int = Field(default=0)
    up: int = Field(default=0)
    acting: int = Field(default=0)
    num_store_stats: int = Field(default=0)


class PGMap(BaseModel):
    """Schema for PG map."""

    version: int = Field(default=0)
    stamp: str = Field(default="")
    last_osdmap_epoch: int = Field(default=0)
    last_pg_scan: int = Field(default=0)
    pg_stats_sum: PGStatsSum
    osd_stats_sum: OSDStatsSum
    pg_stats_delta: PGStatsDelta
    pg_stats: list[PGStat] = Field(default_factory=list)
    pool_stats: list[PoolStat] = Field(default_factory=list)
    osd_stats: list[OSDStat] = Field(default_factory=list)
    pool_statfs: list[PoolStatfs] = Field(default_factory=list)


class PGDump(BaseModel):
    """Schema for `ceph pg dump --format=json` response."""

    pg_ready: bool
    pg_map: PGMap

    @classmethod
    def loads(cls, raw: str) -> PGDump:
        """Parse PG dump from JSON string."""
        try:
            return cls.model_validate_json(raw)
        except Exception as e:
            raise MalformedCephDataError(f"Failed to parse PG dump: {e}") from e

    @classmethod
    def load(cls, path: pathlib.Path) -> PGDump:
        """Load and parse PG dump from file."""
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        raw = path.read_text()
        return cls.loads(raw)


class OSDDFNode(BaseModel):
    """Schema for OSD disk usage node from `ceph osd df --format=json`."""

    id: int = Field(default=0)
    device_class: str = Field(default="")
    name: str = Field(default="")
    type: str = Field(default="")
    type_id: int = Field(default=0)
    crush_weight: float = Field(default=0.0)
    depth: int = Field(default=0)
    pool_weights: dict[str, Any] = Field(default_factory=dict)
    reweight: float = Field(default=0.0)
    kb: int = Field(default=0)
    kb_used: int = Field(default=0)
    kb_used_data: int = Field(default=0)
    kb_used_omap: int = Field(default=0)
    kb_used_meta: int = Field(default=0)
    kb_avail: int = Field(default=0)
    utilization: float = Field(default=0.0)
    var: float = Field(default=0.0)
    pgs: int = Field(default=0)
    status: str = Field(default="")


class OSDDFResponse(BaseModel):
    """Schema for `ceph osd df --format=json` response."""

    model_config = {"extra": "allow"}

    nodes: list[OSDDFNode]

    @classmethod
    def loads(cls, raw: str) -> OSDDFResponse:
        """Parse OSD DF from JSON string."""
        try:
            return cls.model_validate_json(raw)
        except Exception as e:
            raise MalformedCephDataError(f"Failed to parse OSD DF: {e}") from e

    @classmethod
    def load(cls, path: pathlib.Path) -> OSDDFResponse:
        """Load and parse OSD DF from file."""
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        raw = path.read_text()
        return cls.loads(raw)


class LastPGMergeMeta(BaseModel):
    """Schema for last PG merge metadata."""

    source_pgid: str = Field(default="")
    ready_epoch: int = Field(default=0)
    last_epoch_started: int = Field(default=0)
    last_epoch_clean: int = Field(default=0)
    source_version: str = Field(default="")
    target_version: str = Field(default="")


class HitSetParams(BaseModel):
    """Schema for hit set parameters."""

    type: str = Field(default="")


class PoolConfig(BaseModel):
    """Schema for pool configuration from osd dump."""

    pool: int = Field(default=0)
    pool_name: str = Field(default="")
    create_time: str = Field(default="")
    flags: int = Field(default=0)
    flags_names: str = Field(default="")
    type: int = Field(default=0)
    size: int = Field(default=0)
    min_size: int = Field(default=0)
    crush_rule: int = Field(default=0)
    peering_crush_bucket_count: int = Field(default=0)
    peering_crush_bucket_target: int = Field(default=0)
    peering_crush_bucket_barrier: int = Field(default=0)
    peering_crush_bucket_mandatory_member: int = Field(default=2147483647)
    object_hash: int = Field(default=0)
    pg_autoscale_mode: str = Field(default="")
    pg_num: int = Field(default=0)
    pg_placement_num: int = Field(default=0)
    pg_placement_num_target: int = Field(default=0)
    pg_num_target: int = Field(default=0)
    pg_num_pending: int = Field(default=0)
    last_pg_merge_meta: LastPGMergeMeta | None = None
    last_change: str = Field(default="")
    last_force_op_resend: str = Field(default="")
    last_force_op_resend_prenautilus: str = Field(default="")
    last_force_op_resend_preluminous: str = Field(default="")
    auid: int = Field(default=0)
    snap_mode: str = Field(default="")
    snap_seq: int = Field(default=0)
    snap_epoch: int = Field(default=0)
    pool_snaps: list[Any] = Field(default_factory=list)
    removed_snaps: str = Field(default="")
    quota_max_bytes: int = Field(default=0)
    quota_max_objects: int = Field(default=0)
    tiers: list[Any] = Field(default_factory=list)
    tier_of: int = Field(default=0)
    read_tier: int = Field(default=0)
    write_tier: int = Field(default=0)
    cache_mode: str = Field(default="")
    target_max_bytes: int = Field(default=0)
    target_max_objects: int = Field(default=0)
    cache_target_dirty_ratio_micro: int = Field(default=0)
    cache_target_dirty_high_ratio_micro: int = Field(default=0)
    cache_target_full_ratio_micro: int = Field(default=0)
    cache_min_flush_age: int = Field(default=0)
    cache_min_evict_age: int = Field(default=0)
    erasure_code_profile: str = Field(default="")
    hit_set_params: HitSetParams
    hit_set_period: int = Field(default=0)
    hit_set_count: int = Field(default=0)
    # Optional fields - may be present in some Ceph versions
    hit_set_archive: bool = Field(default=False)
    min_read_recency_for_promote: int = Field(default=0)
    min_write_recency_for_promote: int = Field(default=0)
    fast_read: bool = Field(default=False)
    hit_set_grade_decay_rate: int = Field(default=0)
    hit_set_search_last_n: int = Field(default=0)
    grade_table: list[Any] = Field(default_factory=list)
    stripe_width: int = Field(default=0)
    expected_num_objects: int = Field(default=0)
    compression_algorithm: str = Field(default="")
    compression_mode: str = Field(default="")
    compression_required_ratio: float = Field(default=0.0)
    compression_max_blob_size: int = Field(default=0)
    compression_min_blob_size: int = Field(default=0)
    is_stretch_pool: bool = Field(default=False)
    stretch_rule_id: int = Field(default=0)
    pg_autoscale_bias: float = Field(default=1.0)
    pg_num_min: int = Field(default=0)
    recovery_priority: int = Field(default=0)
    recovery_op_priority: int = Field(default=0)
    scrub_min_interval: int = Field(default=0)
    scrub_max_interval: int = Field(default=0)
    deep_scrub_interval: int = Field(default=0)
    recovery_deletes: bool = Field(default=False)
    auto_repair: bool = Field(default=False)
    bulk: bool = Field(default=False)
    fingerprint_algorithm: str | None = Field(default=None)
    pg_autoscale_max_growth: float | None = Field(default=None)
    target_size_bytes: int | None = Field(default=None)
    target_size_ratio: float | None = Field(default=None)
    pg_num_max: int | None = Field(default=None)
    # Additional fields that may be present
    nodelete: bool = Field(default=False)
    nopgchange: bool = Field(default=False)
    nosizechange: bool = Field(default=False)
    write_fadvise_dontneed: bool = Field(default=False)
    noscrub: bool = Field(default=False)
    nodeep_scrub: bool = Field(default=False)
    use_gmt_hitset: bool = Field(default=False)
    debug_fake_ec_pool: bool = Field(default=False)
    debug_pool: bool = Field(default=False)
    hashpspool: bool = Field(default=False)
    backfillfull: bool = Field(default=False)
    selfmanaged_snaps: bool = Field(default=False)
    pool_metadata: dict[str, Any] = Field(default_factory=dict)
    read_balance_score: int = Field(default=0)
    pg_autoscale_max_objects: int = Field(default=0)
    application_metadata: dict[str, Any] = Field(default_factory=dict)


class OSDDumpResponse(BaseModel):
    """Schema for `ceph osd dump --format=json` response."""

    model_config = {"extra": "allow"}

    epoch: int = Field(default=0)
    fsid: str = Field(default="")
    created: str = Field(default="")
    modified: str = Field(default="")
    last_up_change: str = Field(default="")
    last_in_change: str = Field(default="")
    flags: str = Field(default="")
    flags_num: int = Field(default=0)
    flags_set: list[str] = Field(default_factory=list)
    crush_version: int = Field(default=0)
    full_ratio: float = Field(default=0.0)
    backfillfull_ratio: float = Field(default=0.0)
    nearfull_ratio: float = Field(default=0.0)
    cluster_snapshot: str = Field(default="")
    pool_max: int = Field(default=0)
    max_osd: int = Field(default=0)
    require_min_compat_client: str = Field(default="")
    min_compat_client: str = Field(default="")
    require_osd_release: str = Field(default="")
    allow_crimson: bool = Field(default=False)
    pools: list[PoolConfig]
    osds: list[dict[str, Any]] = Field(default_factory=list)
    pg_upmap: list[Any] = Field(default_factory=list)
    pg_upmap_items: list[Any] = Field(default_factory=list)
    pg_temp: list[Any] = Field(default_factory=list)
    primary_temp: list[Any] = Field(default_factory=list)
    blacklist: dict[str, Any] = Field(default_factory=dict)
    erasure_code_profiles: dict[str, Any] = Field(default_factory=dict)
    removed_snaps_queue: list[Any] = Field(default_factory=list)
    new_removed_snaps: list[Any] = Field(default_factory=list)
    new_purged_snaps: list[Any] = Field(default_factory=list)
    crush_node_flags: dict[str, Any] = Field(default_factory=dict)
    device_class_flags: dict[str, Any] = Field(default_factory=dict)
    stretch_mode: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def loads(cls, raw: str) -> OSDDumpResponse:
        """Parse OSD dump from JSON string."""
        try:
            return cls.model_validate_json(raw)
        except Exception as e:
            raise MalformedCephDataError(f"Failed to parse OSD dump: {e}") from e

    @classmethod
    def load(cls, path: pathlib.Path) -> OSDDumpResponse:
        """Load and parse OSD dump from file."""
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        raw = path.read_text()
        return cls.loads(raw)


class LatencyHistogram(BaseModel):
    """Schema for latency histogram with count, sum and average time."""

    avgcount: int = Field(default=0)
    sum: float = Field(default=0.0)
    avgtime: float = Field(default=0.0)


class AsyncMessengerWorker(BaseModel):
    """Schema for AsyncMessenger worker performance metrics."""

    msgr_recv_messages: int = Field(default=0)
    msgr_send_messages: int = Field(default=0)
    msgr_recv_bytes: int = Field(default=0)
    msgr_send_bytes: int = Field(default=0)
    msgr_created_connections: int = Field(default=0)
    msgr_active_connections: int = Field(default=0)
    msgr_running_total_time: float = Field(default=0.0)
    msgr_running_send_time: float = Field(default=0.0)
    msgr_running_recv_time: float = Field(default=0.0)
    msgr_running_fast_dispatch_time: float = Field(default=0.0)
    msgr_send_messages_queue_lat: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    msgr_handle_ack_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    msgr_recv_encrypted_bytes: int = Field(default=0)
    msgr_send_encrypted_bytes: int = Field(default=0)


class BlueFS(BaseModel):
    """Schema for BlueFS performance metrics."""

    db_total_bytes: int = Field(default=0)
    db_used_bytes: int = Field(default=0)
    wal_total_bytes: int = Field(default=0)
    wal_used_bytes: int = Field(default=0)
    slow_total_bytes: int = Field(default=0)
    slow_used_bytes: int = Field(default=0)
    num_files: int = Field(default=0)
    log_bytes: int = Field(default=0)
    log_compactions: int = Field(default=0)
    log_write_count: int = Field(default=0)
    logged_bytes: int = Field(default=0)
    files_written_wal: int = Field(default=0)
    files_written_sst: int = Field(default=0)
    write_count_wal: int = Field(default=0)
    write_count_sst: int = Field(default=0)
    bytes_written_wal: int = Field(default=0)
    bytes_written_sst: int = Field(default=0)
    bytes_written_slow: int = Field(default=0)
    max_bytes_wal: int = Field(default=0)
    max_bytes_db: int = Field(default=0)
    max_bytes_slow: int = Field(default=0)
    alloc_unit_slow: int = Field(default=0)
    alloc_unit_db: int = Field(default=0)
    alloc_unit_wal: int = Field(default=0)
    read_random_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    read_random_count: int = Field(default=0)
    read_random_bytes: int = Field(default=0)
    read_random_disk_count: int = Field(default=0)
    read_random_disk_bytes: int = Field(default=0)
    read_random_disk_bytes_wal: int = Field(default=0)
    read_random_disk_bytes_db: int = Field(default=0)
    read_random_disk_bytes_slow: int = Field(default=0)
    read_random_buffer_count: int = Field(default=0)
    read_random_buffer_bytes: int = Field(default=0)
    read_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    read_count: int = Field(default=0)
    read_bytes: int = Field(default=0)
    read_disk_count: int = Field(default=0)
    read_disk_bytes: int = Field(default=0)
    read_disk_bytes_wal: int = Field(default=0)
    read_disk_bytes_db: int = Field(default=0)
    read_disk_bytes_slow: int = Field(default=0)
    read_prefetch_count: int = Field(default=0)
    read_prefetch_bytes: int = Field(default=0)
    write_count: int = Field(default=0)
    write_disk_count: int = Field(default=0)
    write_bytes: int = Field(default=0)
    compact_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    compact_lock_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    fsync_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    flush_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    unlink_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    truncate_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    alloc_slow_fallback: int = Field(default=0)
    alloc_slow_size_fallback: int = Field(default=0)
    read_zeros_candidate: int = Field(default=0)
    read_zeros_errors: int = Field(default=0)
    wal_alloc_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    db_alloc_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    slow_alloc_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    alloc_wal_max_lat: float = Field(default=0.0)
    alloc_db_max_lat: float = Field(default=0.0)
    alloc_slow_max_lat: float = Field(default=0.0)


class BlueStore(BaseModel):
    """Schema for BlueStore performance metrics."""

    allocated: int = Field(default=0)
    stored: int = Field(default=0)
    fragmentation_micros: int = Field(default=0)
    alloc_unit: int = Field(default=0)
    state_prepare_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    state_aio_wait_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    state_io_done_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    state_kv_queued_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    state_kv_commiting_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    state_kv_done_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    state_finishing_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    state_done_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    state_deferred_queued_lat: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    state_deferred_aio_wait_lat: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    state_deferred_cleanup_lat: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    txc_commit_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    txc_throttle_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    txc_submit_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    txc_count: int = Field(default=0)
    read_onode_meta_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    read_wait_aio_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    csum_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    read_eio: int = Field(default=0)
    reads_with_retries: int = Field(default=0)
    read_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    kv_flush_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    kv_commit_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    kv_sync_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    kv_final_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    write_big: int = Field(default=0)
    write_big_bytes: int = Field(default=0)
    write_big_blobs: int = Field(default=0)
    write_big_deferred: int = Field(default=0)
    write_small: int = Field(default=0)
    write_small_bytes: int = Field(default=0)
    write_small_unused: int = Field(default=0)
    write_small_pre_read: int = Field(default=0)
    write_pad_bytes: int = Field(default=0)
    write_penalty_read_ops: int = Field(default=0)
    write_new: int = Field(default=0)
    issued_deferred_writes: int = Field(default=0)
    issued_deferred_write_bytes: int = Field(default=0)
    submitted_deferred_writes: int = Field(default=0)
    submitted_deferred_write_bytes: int = Field(default=0)
    write_big_skipped_blobs: int = Field(default=0)
    write_big_skipped_bytes: int = Field(default=0)
    write_small_skipped: int = Field(default=0)
    write_small_skipped_bytes: int = Field(default=0)
    compressed: int = Field(default=0)
    compressed_allocated: int = Field(default=0)
    compressed_original: int = Field(default=0)
    compress_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    decompress_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    compress_success_count: int = Field(default=0)
    compress_rejected_count: int = Field(default=0)
    onodes: int = Field(default=0)
    onodes_pinned: int = Field(default=0)
    onode_hits: int = Field(default=0)
    onode_misses: int = Field(default=0)
    onode_shard_hits: int = Field(default=0)
    onode_shard_misses: int = Field(default=0)
    onode_extents: int = Field(default=0)
    onode_blobs: int = Field(default=0)
    buffers: int = Field(default=0)
    buffer_bytes: int = Field(default=0)
    buffer_hit_bytes: int = Field(default=0)
    buffer_miss_bytes: int = Field(default=0)
    onode_reshard: int = Field(default=0)
    blob_split: int = Field(default=0)
    extent_compress: int = Field(default=0)
    gc_merged: int = Field(default=0)
    omap_iterator_count: int = Field(default=0)
    omap_rmkeys_count: int = Field(default=0)
    omap_rmkey_range_count: int = Field(default=0)
    omap_seek_to_first_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    omap_upper_bound_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    omap_lower_bound_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    omap_next_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    omap_get_keys_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    omap_get_values_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    omap_clear_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    clist_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    remove_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    truncate_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    allocator_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    slow_aio_wait_count: int = Field(default=0)
    slow_committed_kv_count: int = Field(default=0)
    slow_read_onode_meta_count: int = Field(default=0)
    slow_read_wait_aio_count: int = Field(default=0)


class BlueStorePriCache(BaseModel):
    """Schema for BlueStore priority cache metrics."""

    target_bytes: int = Field(default=0)
    mapped_bytes: int = Field(default=0)
    unmapped_bytes: int = Field(default=0)
    heap_bytes: int = Field(default=0)
    cache_bytes: int = Field(default=0)


class BlueStorePriCachePool(BaseModel):
    """Schema for BlueStore priority cache pool (data/kv/meta/onode)."""

    pri0_bytes: int = Field(default=0)
    pri1_bytes: int = Field(default=0)
    pri2_bytes: int = Field(default=0)
    pri3_bytes: int = Field(default=0)
    pri4_bytes: int = Field(default=0)
    pri5_bytes: int = Field(default=0)
    pri6_bytes: int = Field(default=0)
    pri7_bytes: int = Field(default=0)
    pri8_bytes: int = Field(default=0)
    pri9_bytes: int = Field(default=0)
    pri10_bytes: int = Field(default=0)
    pri11_bytes: int = Field(default=0)
    reserved_bytes: int = Field(default=0)
    committed_bytes: int = Field(default=0)


class CCT(BaseModel):
    """Schema for Ceph Context Tracker metrics."""

    total_workers: int = Field(default=0)
    unhealthy_workers: int = Field(default=0)


class FinisherMetrics(BaseModel):
    """Schema for finisher queue metrics."""

    queue_len: int = Field(default=0)
    complete_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)


class MemPoolMetrics(BaseModel):
    """Schema for memory pool metrics."""

    bloom_filter_bytes: int = Field(default=0)
    bloom_filter_items: int = Field(default=0)

    bluestore_alloc_bytes: int = Field(default=0)
    bluestore_alloc_items: int = Field(default=0)

    bluestore_cache_data_bytes: int = Field(default=0)
    bluestore_cache_data_items: int = Field(default=0)
    bluestore_cache_onode_bytes: int = Field(default=0)
    bluestore_cache_onode_items: int = Field(default=0)
    bluestore_cache_meta_bytes: int = Field(default=0)
    bluestore_cache_meta_items: int = Field(default=0)
    bluestore_cache_other_bytes: int = Field(default=0)
    bluestore_cache_other_items: int = Field(default=0)
    bluestore_cache_buffer_bytes: int = Field(default=0)
    bluestore_cache_buffer_items: int = Field(default=0)

    bluestore_extent_bytes: int = Field(default=0)
    bluestore_extent_items: int = Field(default=0)
    bluestore_blob_bytes: int = Field(default=0)
    bluestore_blob_items: int = Field(default=0)
    bluestore_shared_blob_bytes: int = Field(default=0)
    bluestore_shared_blob_items: int = Field(default=0)
    bluestore_inline_bl_bytes: int = Field(default=0)
    bluestore_inline_bl_items: int = Field(default=0)
    bluestore_fsck_bytes: int = Field(default=0)
    bluestore_fsck_items: int = Field(default=0)
    bluestore_txc_bytes: int = Field(default=0)
    bluestore_txc_items: int = Field(default=0)
    bluestore_writing_deferred_bytes: int = Field(default=0)
    bluestore_writing_deferred_items: int = Field(default=0)
    bluestore_writing_bytes: int = Field(default=0)
    bluestore_writing_items: int = Field(default=0)

    bluefs_bytes: int = Field(default=0)
    bluefs_items: int = Field(default=0)
    bluefs_file_reader_bytes: int = Field(default=0)
    bluefs_file_reader_items: int = Field(default=0)
    bluefs_file_writer_bytes: int = Field(default=0)
    bluefs_file_writer_items: int = Field(default=0)

    buffer_anon_bytes: int = Field(default=0)
    buffer_anon_items: int = Field(default=0)
    buffer_meta_bytes: int = Field(default=0)
    buffer_meta_items: int = Field(default=0)

    osd_bytes: int = Field(default=0)
    osd_items: int = Field(default=0)
    osd_mapbl_bytes: int = Field(default=0)
    osd_mapbl_items: int = Field(default=0)
    osd_pglog_bytes: int = Field(default=0)
    osd_pglog_items: int = Field(default=0)

    osdmap_bytes: int = Field(default=0)
    osdmap_items: int = Field(default=0)
    osdmap_mapping_bytes: int = Field(default=0)
    osdmap_mapping_items: int = Field(default=0)

    pgmap_bytes: int = Field(default=0)
    pgmap_items: int = Field(default=0)

    mds_co_bytes: int = Field(default=0)
    mds_co_items: int = Field(default=0)

    unittest_1_bytes: int = Field(default=0)
    unittest_1_items: int = Field(default=0)
    unittest_2_bytes: int = Field(default=0)
    unittest_2_items: int = Field(default=0)


class ObjecterMetrics(BaseModel):
    """Schema for Objecter client metrics."""

    op_active: int = Field(default=0)
    op_laggy: int = Field(default=0)
    op_send: int = Field(default=0)
    op_send_bytes: int = Field(default=0)
    op_resend: int = Field(default=0)
    op_reply: int = Field(default=0)
    op_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    op_inflight: int = Field(default=0)
    oplen_avg: dict[str, int] = Field(default_factory=dict)
    op: int = Field(default=0)
    op_r: int = Field(default=0)
    op_w: int = Field(default=0)
    op_rmw: int = Field(default=0)
    op_pg: int = Field(default=0)

    osdop_stat: int = Field(default=0)
    osdop_create: int = Field(default=0)
    osdop_read: int = Field(default=0)
    osdop_write: int = Field(default=0)
    osdop_writefull: int = Field(default=0)
    osdop_writesame: int = Field(default=0)
    osdop_append: int = Field(default=0)
    osdop_zero: int = Field(default=0)
    osdop_truncate: int = Field(default=0)
    osdop_delete: int = Field(default=0)
    osdop_mapext: int = Field(default=0)
    osdop_sparse_read: int = Field(default=0)
    osdop_clonerange: int = Field(default=0)
    osdop_getxattr: int = Field(default=0)
    osdop_setxattr: int = Field(default=0)
    osdop_cmpxattr: int = Field(default=0)
    osdop_rmxattr: int = Field(default=0)
    osdop_resetxattrs: int = Field(default=0)
    osdop_call: int = Field(default=0)
    osdop_watch: int = Field(default=0)
    osdop_notify: int = Field(default=0)
    osdop_src_cmpxattr: int = Field(default=0)
    osdop_pgls: int = Field(default=0)
    osdop_pgls_filter: int = Field(default=0)
    osdop_other: int = Field(default=0)

    linger_active: int = Field(default=0)
    linger_send: int = Field(default=0)
    linger_resend: int = Field(default=0)
    linger_ping: int = Field(default=0)

    poolop_active: int = Field(default=0)
    poolop_send: int = Field(default=0)
    poolop_resend: int = Field(default=0)
    poolstat_active: int = Field(default=0)
    poolstat_send: int = Field(default=0)
    poolstat_resend: int = Field(default=0)
    statfs_active: int = Field(default=0)
    statfs_send: int = Field(default=0)
    statfs_resend: int = Field(default=0)
    command_active: int = Field(default=0)
    command_send: int = Field(default=0)
    command_resend: int = Field(default=0)

    map_epoch: int = Field(default=0)
    map_full: int = Field(default=0)
    map_inc: int = Field(default=0)
    osd_sessions: int = Field(default=0)
    osd_session_open: int = Field(default=0)
    osd_session_close: int = Field(default=0)
    osd_laggy: int = Field(default=0)

    omap_wr: int = Field(default=0)
    omap_rd: int = Field(default=0)
    omap_del: int = Field(default=0)


class OSDMetrics(BaseModel):
    """Schema for OSD daemon performance metrics."""

    op_wip: int = Field(default=0)
    op: int = Field(default=0)
    op_in_bytes: int = Field(default=0)
    op_out_bytes: int = Field(default=0)
    op_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    op_process_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    op_prepare_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)

    op_r: int = Field(default=0)
    op_r_out_bytes: int = Field(default=0)
    op_r_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    op_r_process_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    op_r_prepare_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)

    op_w: int = Field(default=0)
    op_w_in_bytes: int = Field(default=0)
    op_w_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    op_w_process_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    op_w_prepare_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)

    op_rw: int = Field(default=0)
    op_rw_in_bytes: int = Field(default=0)
    op_rw_out_bytes: int = Field(default=0)
    op_rw_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    op_rw_process_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    op_rw_prepare_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)

    op_delayed_unreadable: int = Field(default=0)
    op_delayed_degraded: int = Field(default=0)
    op_before_queue_op_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    op_before_dequeue_op_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)

    subop: int = Field(default=0)
    subop_in_bytes: int = Field(default=0)
    subop_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    subop_w: int = Field(default=0)
    subop_w_in_bytes: int = Field(default=0)
    subop_w_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    subop_pull: int = Field(default=0)
    subop_pull_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    subop_push: int = Field(default=0)
    subop_push_in_bytes: int = Field(default=0)
    subop_push_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)

    pull: int = Field(default=0)
    push: int = Field(default=0)
    push_out_bytes: int = Field(default=0)
    recovery_ops: int = Field(default=0)
    recovery_bytes: int = Field(default=0)
    l_osd_recovery_push_queue_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    l_osd_recovery_push_reply_queue_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    l_osd_recovery_pull_queue_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    l_osd_recovery_backfill_queue_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    l_osd_recovery_backfill_remove_queue_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    l_osd_recovery_scan_queue_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    l_osd_recovery_queue_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    l_osd_recovery_context_queue_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )

    loadavg: int = Field(default=0)
    cached_crc: int = Field(default=0)
    cached_crc_adjusted: int = Field(default=0)
    missed_crc: int = Field(default=0)

    numpg: int = Field(default=0)
    numpg_primary: int = Field(default=0)
    numpg_replica: int = Field(default=0)
    numpg_stray: int = Field(default=0)
    numpg_removing: int = Field(default=0)

    heartbeat_to_peers: int = Field(default=0)
    map_messages: int = Field(default=0)
    map_message_epochs: int = Field(default=0)
    map_message_epoch_dups: int = Field(default=0)
    messages_delayed_for_map: int = Field(default=0)
    osd_map_cache_hit: int = Field(default=0)
    osd_map_cache_miss: int = Field(default=0)
    osd_map_cache_miss_low: int = Field(default=0)
    osd_map_cache_miss_low_avg: dict[str, int] = Field(
        default_factory=dict
    )  # avgcount, sum
    osd_map_bl_cache_hit: int = Field(default=0)
    osd_map_bl_cache_miss: int = Field(default=0)

    stat_bytes: int = Field(default=0)
    stat_bytes_used: int = Field(default=0)
    stat_bytes_avail: int = Field(default=0)

    copyfrom: int = Field(default=0)
    tier_promote: int = Field(default=0)
    tier_flush: int = Field(default=0)
    tier_flush_fail: int = Field(default=0)
    tier_try_flush: int = Field(default=0)
    tier_try_flush_fail: int = Field(default=0)
    tier_evict: int = Field(default=0)
    tier_whiteout: int = Field(default=0)
    tier_dirty: int = Field(default=0)
    tier_clean: int = Field(default=0)
    tier_delay: int = Field(default=0)
    tier_proxy_read: int = Field(default=0)
    tier_proxy_write: int = Field(default=0)
    agent_wake: int = Field(default=0)
    agent_skip: int = Field(default=0)
    agent_flush: int = Field(default=0)
    agent_evict: int = Field(default=0)

    object_ctx_cache_hit: int = Field(default=0)
    object_ctx_cache_total: int = Field(default=0)
    op_cache_hit: int = Field(default=0)

    osd_tier_flush_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    osd_tier_promote_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)
    osd_tier_r_lat: LatencyHistogram = Field(default_factory=LatencyHistogram)

    osd_pg_info: int = Field(default=0)
    osd_pg_fastinfo: int = Field(default=0)
    osd_pg_biginfo: int = Field(default=0)


class OSDSlowOps(BaseModel):
    """Schema for OSD slow operations metrics."""

    slow_ops_count: int = Field(default=0)


class RecoveryStatePerf(BaseModel):
    """Schema for recovery state performance metrics."""

    initial_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    started_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    reset_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    start_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    primary_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    peering_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    backfilling_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    waitremotebackfillreserved_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    waitlocalbackfillreserved_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    notbackfilling_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    repnotrecovering_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    repwaitrecoveryreserved_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    repwaitbackfillreserved_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    reprecovering_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    activating_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    waitlocalrecoveryreserved_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    waitremoterecoveryreserved_latency: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    recovering_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    recovered_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    clean_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    active_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    replicaactive_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    stray_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    getinfo_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    getlog_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    waitactingchange_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    incomplete_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    down_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    getmissing_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    waitupthru_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    notrecovering_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)


class RocksDBMetrics(BaseModel):
    """Schema for RocksDB performance metrics."""

    get_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    submit_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    submit_sync_latency: LatencyHistogram = Field(default_factory=LatencyHistogram)
    compact: int = Field(default=0)
    compact_range: int = Field(default=0)
    compact_queue_merge: int = Field(default=0)
    compact_queue_len: int = Field(default=0)
    rocksdb_write_wal_time: LatencyHistogram = Field(default_factory=LatencyHistogram)
    rocksdb_write_memtable_time: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )
    rocksdb_write_delay_time: LatencyHistogram = Field(default_factory=LatencyHistogram)
    rocksdb_write_pre_and_post_time: LatencyHistogram = Field(
        default_factory=LatencyHistogram
    )


class ThrottleMetrics(BaseModel):
    """Schema for throttling metrics."""

    val: int = Field(default=0)
    max: int = Field(default=0)
    get_started: int = Field(default=0)
    get: int = Field(default=0)
    get_sum: int = Field(default=0)
    get_or_fail_fail: int = Field(default=0)
    get_or_fail_success: int = Field(default=0)
    take: int = Field(default=0)
    take_sum: int = Field(default=0)
    put: int = Field(default=0)
    put_sum: int = Field(default=0)
    wait: LatencyHistogram = Field(default_factory=LatencyHistogram)


class OSDPerfDumpResponse(BaseModel):
    """Schema for `ceph tell osd.X perf dump` response."""

    model_config = {"extra": "allow"}

    # AsyncMessenger workers - dynamic field names
    # Use a more flexible approach for dynamic worker names
    def __init__(self, **data):
        # Extract AsyncMessenger workers
        async_workers = {}
        regular_fields = {}

        for key, value in data.items():
            if key.startswith("AsyncMessenger::Worker-"):
                async_workers[key] = value
            else:
                regular_fields[key] = value

        # Store async workers separately
        self._async_workers = {
            k: AsyncMessengerWorker(**v) for k, v in async_workers.items()
        }

        super().__init__(**regular_fields)

    @property
    def async_messenger_workers(self) -> dict[str, AsyncMessengerWorker]:
        """Get all AsyncMessenger workers."""
        return getattr(self, "_async_workers", {})

    bluefs: BlueFS = Field(default_factory=BlueFS)
    bluestore: BlueStore = Field(default_factory=BlueStore)

    bluestore_pricache: BlueStorePriCache = Field(alias="bluestore-pricache")
    bluestore_pricache_data: BlueStorePriCachePool = Field(
        alias="bluestore-pricache:data"
    )
    bluestore_pricache_kv: BlueStorePriCachePool = Field(alias="bluestore-pricache:kv")
    bluestore_pricache_kv_onode: BlueStorePriCachePool = Field(
        alias="bluestore-pricache:kv_onode"
    )
    bluestore_pricache_meta: BlueStorePriCachePool = Field(
        alias="bluestore-pricache:meta"
    )

    cct: CCT = Field(default_factory=CCT)

    finisher_commit_finisher: FinisherMetrics = Field(alias="finisher-commit_finisher")
    finisher_objecter_finisher_0: FinisherMetrics = Field(
        alias="finisher-objecter-finisher-0"
    )

    mempool: MemPoolMetrics = Field(default_factory=MemPoolMetrics)

    objecter: ObjecterMetrics = Field(default_factory=ObjecterMetrics)
    osd: OSDMetrics = Field(default_factory=OSDMetrics)
    osd_slow_ops: Optional[OSDSlowOps] = Field(alias="trackedop")

    recoverystate_perf: RecoveryStatePerf = Field(default_factory=RecoveryStatePerf)

    rocksdb: RocksDBMetrics = Field(default_factory=RocksDBMetrics)

    # Throttling metrics - multiple throttle instances with dynamic names
    throttle_bluestore_throttle_bytes: ThrottleMetrics = Field(
        alias="throttle-bluestore_throttle_bytes"
    )
    throttle_bluestore_throttle_deferred_bytes: ThrottleMetrics = Field(
        alias="throttle-bluestore_throttle_deferred_bytes"
    )
    throttle_msgr_dispatch_throttler_client: ThrottleMetrics = Field(
        alias="throttle-msgr_dispatch_throttler-client"
    )
    throttle_msgr_dispatch_throttler_cluster: ThrottleMetrics = Field(
        alias="throttle-msgr_dispatch_throttler-cluster"
    )
    throttle_msgr_dispatch_throttler_hb_back_client: ThrottleMetrics = Field(
        alias="throttle-msgr_dispatch_throttler-hb_back_client"
    )
    throttle_msgr_dispatch_throttler_hb_back_server: ThrottleMetrics = Field(
        alias="throttle-msgr_dispatch_throttler-hb_back_server"
    )
    throttle_msgr_dispatch_throttler_hb_front_client: ThrottleMetrics = Field(
        alias="throttle-msgr_dispatch_throttler-hb_front_client"
    )
    throttle_msgr_dispatch_throttler_hb_front_server: ThrottleMetrics = Field(
        alias="throttle-msgr_dispatch_throttler-hb_front_server"
    )
    throttle_msgr_dispatch_throttler_ms_objecter: ThrottleMetrics = Field(
        alias="throttle-msgr_dispatch_throttler-ms_objecter"
    )
    throttle_objecter_bytes: ThrottleMetrics = Field(alias="throttle-objecter_bytes")
    throttle_objecter_ops: ThrottleMetrics = Field(alias="throttle-objecter_ops")
    throttle_osd_client_bytes: ThrottleMetrics = Field(
        alias="throttle-osd_client_bytes"
    )
    throttle_osd_client_messages: ThrottleMetrics = Field(
        alias="throttle-osd_client_messages"
    )

    @classmethod
    def loads(cls, raw: str) -> OSDPerfDumpResponse:
        """Parse OSD performance dump from JSON string."""
        try:
            return cls.model_validate_json(raw)
        except Exception as e:
            raise MalformedCephDataError(f"Failed to parse OSD perf dump: {e}") from e

    @classmethod
    def load(cls, path: pathlib.Path) -> OSDPerfDumpResponse:
        """Load and parse OSD performance dump from file."""
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        raw = path.read_text()
        return cls.loads(raw)


class CephfsClient(BaseModel):
    """Schema for CephFS client information from fs status."""

    clients: int = Field(default=0)
    fs: str = Field(default="")


class CephfsMDSVersion(BaseModel):
    """Schema for MDS version information from fs status."""

    daemon: list[str] = Field(default_factory=list)
    version: str = Field(default="")


class CephfsMDSMapEntry(BaseModel):
    """Schema for MDS map entry from fs status."""

    caps: int = Field(default=0)
    dirs: int = Field(default=0)
    dns: int = Field(default=0)
    inos: int = Field(default=0)
    name: str = Field(default="")
    rank: int = Field(default=-1)
    rate: int = Field(default=0)
    state: str = Field(default="")

    # Optional field for source
    file: Optional[str] = Field(
        default=None
    )  # This field is present for the source logic in cephfs session top command


class CephfsPool(BaseModel):
    """Schema for CephFS pool information from fs status."""

    avail: int = Field(default=0)
    pool_id: int = Field(default=0, alias="id")
    name: str = Field(default="")
    pool_type: str = Field(default="", alias="type")
    used: int = Field(default=0)


class CephfsStatusResponse(BaseModel):
    """Schema for `ceph fs status --format=json` response."""

    model_config = {"extra": "allow"}

    clients: list[CephfsClient] = Field(default_factory=list)
    mds_version: list[CephfsMDSVersion] = Field(default_factory=list)
    mdsmap: list[CephfsMDSMapEntry] = Field(default_factory=list)
    pools: list[CephfsPool] = Field(default_factory=list)

    @classmethod
    def loads(cls, raw: str) -> CephfsStatusResponse:
        """Parse CephFS status from JSON string."""
        try:
            return cls.model_validate_json(raw)
        except Exception as e:
            raise MalformedCephDataError(f"Failed to parse CephFS status: {e}") from e

    @classmethod
    def load(cls, path: pathlib.Path) -> CephfsStatusResponse:
        """Load and parse CephFS status from file."""
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        raw = path.read_text()
        return cls.loads(raw)


class MDSAddressVector(BaseModel):
    """Schema for MDS address vector."""

    type: str = Field(default="")
    addr: str = Field(default="")
    nonce: int = Field(default=0)


class MDSAddresses(BaseModel):
    """Schema for MDS addresses."""

    addrvec: list[MDSAddressVector] = Field(default_factory=list)


class MDSCompatibility(BaseModel):
    """Schema for MDS compatibility features."""

    model_config = {"extra": "allow"}

    compat: dict[str, str] = Field(default_factory=dict)
    ro_compat: dict[str, str] = Field(default_factory=dict)
    incompat: dict[str, str] = Field(default_factory=dict)


class MDSInfo(BaseModel):
    """Schema for individual MDS daemon information."""

    model_config = {"extra": "allow"}

    gid: int = Field(default=0)
    name: str = Field(default="")
    rank: int = Field(default=-1)
    incarnation: int = Field(default=0)
    state: str = Field(default="")
    state_seq: int = Field(default=0)
    addr: str = Field(default="")
    addrs: MDSAddresses = Field(default_factory=MDSAddresses)
    join_fscid: int = Field(default=-1)
    export_targets: list[int] = Field(default_factory=list)
    features: int = Field(default=0)
    flags: int = Field(default=0)
    compat: MDSCompatibility = Field(default_factory=MDSCompatibility)
    epoch: int = Field(default=0)  # Only present for standbys


class MDSFlagsState(BaseModel):
    """Schema for MDS flags state."""

    joinable: bool = Field(default=True)
    allow_snaps: bool = Field(default=True)
    allow_multimds_snaps: bool = Field(default=True)
    allow_standby_replay: bool = Field(default=False)
    refuse_client_session: bool = Field(default=False)
    refuse_standby_for_another_fs: bool = Field(default=False)
    balance_automate: bool = Field(default=False)


class MDSMap(BaseModel):
    """Schema for MDS map within a filesystem."""

    model_config = {"extra": "allow"}

    epoch: int = Field(default=0)
    flags: int = Field(default=0)
    flags_state: MDSFlagsState = Field(default_factory=MDSFlagsState)
    ever_allowed_features: int = Field(default=0)
    explicitly_allowed_features: int = Field(default=0)
    created: str = Field(default="")
    modified: str = Field(default="")
    tableserver: int = Field(default=0)
    root: int = Field(default=0)
    session_timeout: int = Field(default=60)
    session_autoclose: int = Field(default=300)
    required_client_features: dict[str, Any] = Field(default_factory=dict)
    max_file_size: int = Field(default=0)
    max_xattr_size: int = Field(default=0)
    last_failure: int = Field(default=0)
    last_failure_osd_epoch: int = Field(default=0)
    compat: MDSCompatibility = Field(default_factory=MDSCompatibility)
    max_mds: int = Field(default=1)
    # "in" is a Python keyword
    in_ranks: list[int] = Field(default_factory=list, alias="in")
    up: dict[str, int] = Field(default_factory=dict)
    failed: list[int] = Field(default_factory=list)
    damaged: list[int] = Field(default_factory=list)
    stopped: list[int] = Field(default_factory=list)
    info: dict[str, MDSInfo] = Field(default_factory=dict)
    data_pools: list[int] = Field(default_factory=list)
    metadata_pool: int = Field(default=0)
    enabled: bool = Field(default=True)
    fs_name: str = Field(default="")
    balancer: str = Field(default="")
    bal_rank_mask: str = Field(default="")
    standby_count_wanted: int = Field(default=1)


class FilesystemInfo(BaseModel):
    """Schema for filesystem information from mds stat."""

    mdsmap: MDSMap = Field(default_factory=MDSMap)
    filesystem_id: int = Field(default=0, alias="id")


class FSMapCompatibility(BaseModel):
    """Schema for fsmap compatibility."""

    compat: dict[str, str] = Field(default_factory=dict)
    ro_compat: dict[str, str] = Field(default_factory=dict)
    incompat: dict[str, str] = Field(default_factory=dict)


class FSMapFeatureFlags(BaseModel):
    """Schema for fsmap feature flags."""

    enable_multiple: bool = Field(default=False)
    ever_enabled_multiple: bool = Field(default=False)


class FSMap(BaseModel):
    """Schema for the fsmap section of mds stat (detailed MDS map)."""

    model_config = {"extra": "allow"}

    epoch: int = Field(default=0)
    default_fscid: int = Field(default=0)
    compat: FSMapCompatibility = Field(default_factory=FSMapCompatibility)
    feature_flags: FSMapFeatureFlags = Field(default_factory=FSMapFeatureFlags)
    standbys: list[MDSInfo] = Field(default_factory=list)
    filesystems: list[FilesystemInfo] = Field(default_factory=list)


class CephfsMDSStatResponse(BaseModel):
    """Schema for `ceph mds stat --format=json` response."""

    model_config = {"extra": "allow"}

    fsmap: FSMap = Field(default_factory=FSMap)
    mdsmap_first_committed: int = Field(default=0)
    mdsmap_last_committed: int = Field(default=0)

    @property
    def standbys(self) -> list[MDSInfo]:
        """Get standby MDS daemons."""
        return self.fsmap.standbys

    @property
    def filesystems(self) -> list[FilesystemInfo]:
        """Get all filesystems."""
        return self.fsmap.filesystems

    @classmethod
    def loads(cls, raw: str) -> CephfsMDSStatResponse:
        """Parse MDS stat from JSON string."""
        try:
            return cls.model_validate_json(raw)
        except Exception as e:
            raise MalformedCephDataError(f"Failed to parse MDS stat: {e}") from e

    @classmethod
    def load(cls, path: pathlib.Path) -> CephfsMDSStatResponse:
        """Load and parse MDS stat from file."""
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        raw = path.read_text()
        return cls.loads(raw)


class CephfsSessionEntityName(BaseModel):
    """Schema for CephFS session entity name."""

    entity_type: str = Field(default="client", alias="type")
    num: int = Field(default=0)


class CephfsSessionEntityAddr(BaseModel):
    """Schema for CephFS session entity address."""

    addr_type: str = Field(default="v1", alias="type")
    addr: str = Field(default="")
    nonce: int = Field(default=0)


class CephfsSessionEntity(BaseModel):
    """Schema for CephFS session entity."""

    name: CephfsSessionEntityName = Field(default_factory=CephfsSessionEntityName)
    addr: CephfsSessionEntityAddr = Field(default_factory=CephfsSessionEntityAddr)


class CephfsSessionMetricValue(BaseModel):
    """Schema for CephFS session metric with value and halflife."""

    value: float = Field(default=0.0)
    halflife: float = Field(default=0.0)


class CephfsSessionClientFeatures(BaseModel):
    """Schema for CephFS session client features."""

    feature_bits: str = Field(default="0x0")


class CephfsSessionMetricFlags(BaseModel):
    """Schema for CephFS session metric flags."""

    feature_bits: str = Field(default="0x0")


class CephfsSessionMetricSpec(BaseModel):
    """Schema for CephFS session metric specification."""

    metric_flags: CephfsSessionMetricFlags = Field(
        default_factory=CephfsSessionMetricFlags
    )


class CephfsSessionClientMetadata(BaseModel):
    """Schema for CephFS session client metadata."""

    model_config = {"extra": "allow"}

    client_features: CephfsSessionClientFeatures = Field(
        default_factory=CephfsSessionClientFeatures
    )
    metric_spec: CephfsSessionMetricSpec = Field(
        default_factory=CephfsSessionMetricSpec
    )
    entity_id: str = Field(default="")
    hostname: str = Field(default="")
    kernel_version: str = Field(default="")
    root: str = Field(default="")


class CephfsSessionCompletedRequest(BaseModel):
    """Schema for CephFS session completed request."""

    tid: int = Field(default=0)
    created_ino: str = Field(default="")


class CephfsSessionPreallocIno(BaseModel):
    """Schema for CephFS session preallocated inode range."""

    start: str = Field(default="")
    length: int = Field(default=0)


class CephfsSession(BaseModel):
    """Schema for individual CephFS session."""

    model_config = {"extra": "allow"}

    session_id: int = Field(default=0, alias="id")
    entity: CephfsSessionEntity = Field(default_factory=CephfsSessionEntity)
    state: str = Field(default="")
    num_leases: int = Field(default=0)
    num_caps: int = Field(default=0)
    request_load_avg: float = Field(default=0.0)
    uptime: float = Field(default=0.0)
    requests_in_flight: int = Field(default=0)
    num_completed_requests: int = Field(default=0)
    num_completed_flushes: int = Field(default=0)
    reconnecting: bool = Field(default=False)
    recall_caps: CephfsSessionMetricValue = Field(
        default_factory=CephfsSessionMetricValue
    )
    release_caps: CephfsSessionMetricValue = Field(
        default_factory=CephfsSessionMetricValue
    )
    recall_caps_throttle: CephfsSessionMetricValue = Field(
        default_factory=CephfsSessionMetricValue
    )
    recall_caps_throttle2o: CephfsSessionMetricValue = Field(
        default_factory=CephfsSessionMetricValue
    )
    session_cache_liveness: CephfsSessionMetricValue = Field(
        default_factory=CephfsSessionMetricValue
    )
    cap_acquisition: CephfsSessionMetricValue = Field(
        default_factory=CephfsSessionMetricValue
    )
    last_trim_completed_requests_tid: int = Field(default=0)
    last_trim_completed_flushes_tid: int = Field(default=0)
    delegated_inos: list[int] = Field(default_factory=list)
    inst: str = Field(default="")
    completed_requests: list[CephfsSessionCompletedRequest] = Field(
        default_factory=list
    )
    prealloc_inos: list[CephfsSessionPreallocIno] = Field(default_factory=list)
    client_metadata: CephfsSessionClientMetadata = Field(
        default_factory=CephfsSessionClientMetadata
    )


class CephfsSessionListResponse(RootModel[list[CephfsSession]]):
    """Schema for `ceph tell mds.X session ls` response."""

    def __iter__(self):
        return iter(self.root)

    def __len__(self):
        return len(self.root)

    def __getitem__(self, item):
        return self.root[item]

    @property
    def sessions(self) -> list[CephfsSession]:
        """Get the sessions list for compatibility."""
        return self.root

    @classmethod
    def loads(cls, raw: str) -> CephfsSessionListResponse:
        """Parse CephFS session list from JSON string."""
        try:
            return cls.model_validate_json(raw)
        except Exception as e:
            raise MalformedCephDataError(
                f"Failed to parse CephFS session list: {e}"
            ) from e

    @classmethod
    def load(cls, path: pathlib.Path) -> CephfsSessionListResponse:
        """Load and parse CephFS session list from file."""
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        raw = path.read_text()
        return cls.loads(raw)


class HealthCheckSummary(BaseModel):
    """Schema for health check summary."""

    model_config = {"extra": "allow"}

    message: str = Field(default="")
    count: int = Field(default=0)


class HealthCheckDetail(BaseModel):
    """Schema for health check detail."""

    model_config = {"extra": "allow"}

    message: str = Field(default="")


class HealthCheck(BaseModel):
    """Schema for individual health check."""

    model_config = {"extra": "allow"}

    severity: str = Field(default="")
    summary: HealthCheckSummary = Field(default_factory=HealthCheckSummary)
    detail: list[HealthCheckDetail] = Field(default_factory=list)
    muted: bool = Field(default=False)


class Health(BaseModel):
    """Schema for cluster health status."""

    model_config = {"extra": "allow"}

    status: str = Field(default="")
    checks: dict[str, HealthCheck] = Field(default_factory=dict)
    mutes: list[dict[str, Any]] = Field(default_factory=list)


class MonMapFeatures(BaseModel):
    """Schema for monitor map features."""

    model_config = {"extra": "allow"}

    persistent: list[str] = Field(default_factory=list)
    optional: list[str] = Field(default_factory=list)


class MonInfo(BaseModel):
    """Schema for monitor information."""

    model_config = {"extra": "allow"}

    rank: int = Field(default=0)
    name: str = Field(default="")
    public_addrs: dict[str, Any] = Field(default_factory=dict)
    public_addr: str = Field(default="")
    addr: str = Field(default="")
    priority: int = Field(default=0)
    weight: int = Field(default=0)
    crush_location: str = Field(default="")


class MonMap(BaseModel):
    """Schema for monitor map."""

    model_config = {"extra": "allow"}

    epoch: int = Field(default=0)
    fsid: str = Field(default="")
    modified: str = Field(default="")
    created: str = Field(default="")
    min_mon_release: int = Field(default=0)
    min_mon_release_name: str = Field(default="")
    election_strategy: int = Field(default=0)
    stretch_mode: bool = Field(default=False)
    tiebreaker_mon: str = Field(default="")
    disallowed_leaders: str = Field(default="", alias="disallowed_leaders: ")
    features: MonMapFeatures = Field(default_factory=MonMapFeatures)
    mons: list[MonInfo] = Field(default_factory=list)


class OSDInfo(BaseModel):
    """Schema for OSD information in osdmap."""

    model_config = {"extra": "allow"}

    osd: int = Field(default=0)
    uuid: str = Field(default="")
    up: int = Field(default=0)
    in_field: int = Field(default=0, alias="in")
    weight: float = Field(default=0.0)
    primary_affinity: float = Field(default=1.0)
    last_clean_begin: int = Field(default=0)
    last_clean_end: int = Field(default=0)
    up_from: int = Field(default=0)
    up_thru: int = Field(default=0)
    down_at: int = Field(default=0)
    lost_at: int = Field(default=0)
    public_addrs: dict[str, Any] = Field(default_factory=dict)
    cluster_addrs: dict[str, Any] = Field(default_factory=dict)
    heartbeat_back_addrs: dict[str, Any] = Field(default_factory=dict)
    heartbeat_front_addrs: dict[str, Any] = Field(default_factory=dict)
    public_addr: str = Field(default="")
    cluster_addr: str = Field(default="")
    heartbeat_back_addr: str = Field(default="")
    heartbeat_front_addr: str = Field(default="")
    state: list[str] = Field(default_factory=list)


class OSDMap(BaseModel):
    """Schema for OSD map."""

    model_config = {"extra": "allow"}

    epoch: int = Field(default=0)
    fsid: str = Field(default="")
    created: str = Field(default="")
    modified: str = Field(default="")
    flags: str = Field(default="")
    flags_num: int = Field(default=0)
    flags_set: list[str] = Field(default_factory=list)
    crush_version: int = Field(default=0)
    full_ratio: float = Field(default=0.0)
    backfillfull_ratio: float = Field(default=0.0)
    nearfull_ratio: float = Field(default=0.0)
    min_compat_client: str = Field(default="")
    require_min_compat_client: str = Field(default="")
    require_osd_release: str = Field(default="")
    pools: list[PoolConfig] = Field(default_factory=list)
    osds: list[OSDInfo] = Field(default_factory=list)
    pg_upmap: list[Any] = Field(default_factory=list)
    pg_upmap_items: list[Any] = Field(default_factory=list)
    pg_temp: list[Any] = Field(default_factory=list)
    primary_temp: list[Any] = Field(default_factory=list)
    blacklist: dict[str, Any] = Field(default_factory=dict)
    erasure_code_profiles: dict[str, Any] = Field(default_factory=dict)


class CrushTunables(BaseModel):
    """Schema for CRUSH tunables."""

    choose_local_tries: int = Field(default=0)
    choose_local_fallback_tries: int = Field(default=0)
    choose_total_tries: int = Field(default=0)
    chooseleaf_descend_once: int = Field(default=0)
    chooseleaf_vary_r: int = Field(default=0)
    chooseleaf_stable: int = Field(default=0)
    straw_calc_version: int = Field(default=0)
    allowed_bucket_algs: int = Field(default=0)
    profile: str = Field(default="")
    optimal_tunables: int = Field(default=0)
    legacy_tunables: int = Field(default=0)
    minimum_required_version: str = Field(default="")
    require_feature_tunables: int = Field(default=0)
    require_feature_tunables2: int = Field(default=0)
    has_v2_rules: int = Field(default=0)
    require_feature_tunables3: int = Field(default=0)
    has_v3_rules: int = Field(default=0)
    has_v4_buckets: int = Field(default=0)
    require_feature_tunables5: int = Field(default=0)
    has_v5_rules: int = Field(default=0)


class CrushMap(BaseModel):
    """Schema for CRUSH map."""

    model_config = {"extra": "allow"}

    devices: list[dict[str, Any]] = Field(default_factory=list)
    types: list[dict[str, Any]] = Field(default_factory=list)
    buckets: list[dict[str, Any]] = Field(default_factory=list)
    rules: list[dict[str, Any]] = Field(default_factory=list)
    tunables: CrushTunables = Field(default_factory=CrushTunables)
    choose_args: dict[str, Any] = Field(default_factory=dict)


class OSDMetadata(BaseModel):
    """Schema for OSD metadata."""

    model_config = {"extra": "allow"}

    id: int = Field(default=0)
    arch: str = Field(default="")
    back_addr: str = Field(default="")
    back_iface: str = Field(default="")
    bluefs: str = Field(default="")
    bluefs_db_access_mode: str = Field(default="")
    bluefs_db_block_size: str = Field(default="")
    bluefs_db_dev: str = Field(default="")
    bluefs_db_dev_node: str = Field(default="")
    bluefs_db_driver: str = Field(default="")
    bluefs_db_model: str = Field(default="")
    bluefs_db_partition_path: str = Field(default="")
    bluefs_db_rotational: str = Field(default="")
    bluefs_db_serial: str = Field(default="")
    bluefs_db_size: str = Field(default="")
    bluefs_db_type: str = Field(default="")
    bluefs_dedicated_db: str = Field(default="")
    bluefs_dedicated_wal: str = Field(default="")
    bluefs_single_shared_device: str = Field(default="")
    bluestore_bdev_access_mode: str = Field(default="")
    bluestore_bdev_block_size: str = Field(default="")
    bluestore_bdev_dev: str = Field(default="")
    bluestore_bdev_dev_node: str = Field(default="")
    bluestore_bdev_driver: str = Field(default="")
    bluestore_bdev_model: str = Field(default="")
    bluestore_bdev_partition_path: str = Field(default="")
    bluestore_bdev_rotational: str = Field(default="")
    bluestore_bdev_serial: str = Field(default="")
    bluestore_bdev_size: str = Field(default="")
    bluestore_bdev_type: str = Field(default="")
    ceph_release: str = Field(default="")
    ceph_version: str = Field(default="")
    ceph_version_short: str = Field(default="")
    cpu: str = Field(default="")
    default_device_class: str = Field(default="")
    devices: str = Field(default="")
    distro: str = Field(default="")
    distro_description: str = Field(default="")
    distro_version: str = Field(default="")
    front_addr: str = Field(default="")
    front_iface: str = Field(default="")
    hb_back_addr: str = Field(default="")
    hb_front_addr: str = Field(default="")
    hostname: str = Field(default="")
    journal_rotational: str = Field(default="")
    kernel_description: str = Field(default="")
    kernel_version: str = Field(default="")
    mem_swap_kb: str = Field(default="")
    mem_total_kb: str = Field(default="")
    objectstore: str = Field(default="")
    os: str = Field(default="")
    osd_data: str = Field(default="")
    osd_objectstore: str = Field(default="")
    rotational: str = Field(default="")


class CephReport(BaseModel):
    """Schema for Ceph cluster diagnostic report."""

    model_config = {"extra": "allow"}

    cluster_fingerprint: str = Field(default="")
    version: str = Field(default="")
    commit: str = Field(default="")
    timestamp: str = Field(default="")
    tag: str = Field(default="")
    health: Health = Field(default_factory=Health)
    monmap: MonMap = Field(default_factory=MonMap)
    monmap_first_committed: int = Field(default=0)
    monmap_last_committed: int = Field(default=0)
    osdmap: OSDMap = Field(default_factory=OSDMap)
    osdmap_first_committed: int = Field(default=0)
    osdmap_last_committed: int = Field(default=0)
    osdmap_clean_epochs: dict[str, Any] = Field(default_factory=dict)
    crushmap: CrushMap = Field(default_factory=CrushMap)
    fsmap: FSMap = Field(default_factory=FSMap)
    mdsmap_first_committed: int = Field(default=0)
    mdsmap_last_committed: int = Field(default=0)
    osd_metadata: list[OSDMetadata] = Field(default_factory=list)
    osd_stats: list[OSDStat] = Field(default_factory=list)
    osd_sum: OSDStatsSum = Field(default_factory=OSDStatsSum)
    osd_sum_by_class: dict[str, OSDStatsSum] = Field(default_factory=dict)
    pool_stats: list[PoolStat] = Field(default_factory=list)
    pool_sum: PGStatsSum = Field(default_factory=PGStatsSum)
    num_osd: int = Field(default=0)
    num_pg: int = Field(default=0)
    num_pg_active: int = Field(default=0)
    num_pg_unknown: int = Field(default=0)
    num_pg_by_state: list[dict[str, Any]] = Field(default_factory=list)
    num_pg_by_osd: list[dict[str, Any]] = Field(default_factory=list)
    purged_snaps: list[Any] = Field(default_factory=list)
    quorum: list[int] = Field(default_factory=list)
    paxos: dict[str, Any] = Field(default_factory=dict)
    servicemap: dict[str, Any] = Field(default_factory=dict)
    auth: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def loads(cls, raw: str) -> CephReport:
        """Parse Ceph report from JSON string."""
        try:
            return cls.model_validate_json(raw)
        except Exception as e:
            raise MalformedCephDataError(f"Failed to parse Ceph report: {e}") from e

    @classmethod
    def load(cls, path: pathlib.Path) -> CephReport:
        """Load and parse Ceph report from file."""
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        raw = path.read_text()
        return cls.loads(raw)


# to resolve forward references
_ = OSDTree.model_rebuild()
_ = PGDump.model_rebuild()
_ = OSDDFResponse.model_rebuild()
_ = OSDDumpResponse.model_rebuild()
_ = OSDPerfDumpResponse.model_rebuild()
_ = CephReport.model_rebuild()


# to resolve forward references
_ = OSDTree.model_rebuild()
_ = PGDump.model_rebuild()
_ = OSDDFResponse.model_rebuild()
_ = OSDDumpResponse.model_rebuild()
_ = OSDPerfDumpResponse.model_rebuild()
_ = CephfsStatusResponse.model_rebuild()
_ = CephfsMDSStatResponse.model_rebuild()
_ = CephReport.model_rebuild()

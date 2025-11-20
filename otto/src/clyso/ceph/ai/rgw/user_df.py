# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import sys
from typing import Any, Optional, TextIO

from clyso.ceph.api.commands import (
    ceph_osd_dump,
    ceph_osd_crush_dump,
    radosgw_admin_zone_get_by_id,
    radosgw_admin_zonegroup_get,
    radosgw_admin_bucket_stats,
    radosgw_admin_bucket_list_objects,
)
from clyso.ceph.api.schemas import (
    MalformedCephDataError,
    OSDDumpResponse,
    CrushMap,
    RGWZoneResponse,
    RGWZonegroupResponse,
)


CATEGORIES = {
    0: "rgw.none",
    1: "rgw.main",  # b-i entries for standard objs
    2: "rgw.shadow",  # presumably intended for multipart shadow uploads; not currently used
    3: "rgw.multimeta",  # b-i entries for multipart upload metadata objs
    4: "rgw.cloudtiered",  # b-i entries which are tiered to external cloud
}


class RGWUserDF:
    """Calculate user's disk usage statistics accounting for replication/EC."""

    def __init__(
        self,
        users: list[str],
        verbose: bool = False,
        process_objects: bool = False,
        output_stream: TextIO = sys.stdout,
        error_stream: TextIO = sys.stderr,
    ) -> None:
        self.users = users
        self.verbose = verbose
        self.process_objects = process_objects
        self.output_stream = output_stream
        self.error_stream = error_stream

        # Caches
        self.osdmap: Optional[OSDDumpResponse] = None
        self.crushmap: Optional[CrushMap] = None
        self.pools: dict[str, Any] = {}
        self.ec_profiles: dict[str, Any] = {}
        self.zones: dict[str, RGWZoneResponse] = {}
        self.zonegroups: dict[str, RGWZonegroupResponse] = {}
        self.pool_osd_class: Optional[dict[str, str]] = None

    def _error(self, msg: str) -> None:
        """Print error message to stderr."""
        print(f"ERROR: {msg}", file=self.error_stream)

    def _debug(self, msg: str) -> None:
        """Print debug message to stderr if verbose mode is enabled."""
        if self.verbose:
            print(f"DEBUG: {msg}", file=self.error_stream)

    def _category_name(self, category_id: int) -> str:
        """Convert category ID to name."""
        return CATEGORIES.get(category_id, "unknown")

    def _get_osdmap(self) -> OSDDumpResponse:
        """Get OSD map from Ceph."""
        if not self.osdmap:
            try:
                self.osdmap = ceph_osd_dump()
                for pool in self.osdmap.pools:
                    self.pools[pool.pool_name] = pool.model_dump()
                self.ec_profiles = self.osdmap.erasure_code_profiles
            except MalformedCephDataError as e:
                self._error(f"Failed to get OSD map: {e}")
                raise ValueError(f"Failed to get OSD map: {e}")
        return self.osdmap

    def _get_pools(self) -> dict[str, Any]:
        """Get pools dictionary"""
        if not self.osdmap:
            self._get_osdmap()
        return self.pools

    def _get_pool(self, pool_name: str) -> dict[str, Any]:
        """Get pool configuration."""
        return self._get_pools()[pool_name]

    def _get_ec_profile(self, profile_name: str) -> dict[str, Any]:
        """Get erasure coding profile."""
        if not self.ec_profiles:
            self._get_osdmap()
        return self.ec_profiles[profile_name]

    def _get_storage_amplification(self, pool_name: str) -> float:
        """Calculate storage amplification factor for a pool."""
        pool = self._get_pool(pool_name)
        if pool["type"] == 3:  # Erasure coded
            profile_name = pool["erasure_code_profile"]
            profile = self._get_ec_profile(profile_name)
            k = int(profile["k"])
            m = int(profile["m"])
        else:  # Replicated
            k = 1
            m = pool["size"] - 1
        return (k + m) / k

    def _get_crushmap(self) -> CrushMap:
        """Get CRUSH map from Ceph."""
        if not self.crushmap:
            try:
                self.crushmap = ceph_osd_crush_dump()
            except MalformedCephDataError as e:
                self._error(f"Failed to get CRUSH map: {e}")
                raise ValueError(f"Failed to get CRUSH map: {e}")
        return self.crushmap

    def _get_crush_rule_by_id(self, crushmap: CrushMap, rule_id: int) -> Optional[Any]:
        """Find CRUSH rule by ID."""
        for rule in crushmap.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def _get_crush_rule_root(self, crushmap: CrushMap, rule_id: int) -> Optional[int]:
        """Get root bucket ID for a CRUSH rule."""
        rule = self._get_crush_rule_by_id(crushmap, rule_id)
        if not rule:
            return None
        for step in rule.steps:
            if step.op == "take":
                root_name = step.item_name
                for bucket in crushmap.buckets:
                    if bucket.name == root_name:
                        return bucket.bucket_id
        return None

    def _get_osds_under_crush_root(self, crushmap: CrushMap, root_id: int) -> list[int]:
        """Recursively get all OSDs under a CRUSH root."""
        osds = []
        for bucket in crushmap.buckets:
            if bucket.bucket_id != root_id:
                continue
            for item in bucket.items:
                if item.item_id < 0:
                    osds += self._get_osds_under_crush_root(crushmap, item.item_id)
                else:
                    osds.append(item.item_id)
        return osds

    def _get_pool_osd_class_map(self) -> dict[str, str]:
        """Build map of pool names to OSD device classes (SSD/HDD)."""
        crushmap = self._get_crushmap()
        pool_osd_class = {}
        crush_rule_class = {}
        pools = self._get_pools()

        for name, pool in pools.items():
            if pool["crush_rule"] in crush_rule_class:
                osd_class = crush_rule_class[pool["crush_rule"]]
            else:
                root_id = self._get_crush_rule_root(crushmap, pool["crush_rule"])
                if not root_id:
                    self._error(f"Pool {name} has no crush rule root")
                    continue
                osds = self._get_osds_under_crush_root(crushmap, root_id)
                osd_class = None
                for osd in osds:
                    for device in crushmap.devices:
                        if device.device_id == osd:
                            osd_class = device.device_class
                            break
                    if osd_class:
                        break
                if not osd_class:
                    osd_class = "unknown"
                crush_rule_class[pool["crush_rule"]] = osd_class

            pool_osd_class[name] = osd_class

        return pool_osd_class

    def _get_pool_osd_class(self, pool_name: str) -> str:
        """Get OSD device class for a pool."""
        if self.pool_osd_class is None:
            self.pool_osd_class = self._get_pool_osd_class_map()
        return self.pool_osd_class.get(pool_name, "unknown")

    def _get_zone(self, zone_id: str) -> RGWZoneResponse:
        """Get zone configuration with caching."""
        if zone_id not in self.zones:
            try:
                self.zones[zone_id] = radosgw_admin_zone_get_by_id(zone_id)
            except MalformedCephDataError as e:
                self._error(f"Failed to get zone {zone_id}: {e}")
                raise ValueError(f"Failed to get zone: {e}")
        return self.zones[zone_id]

    def _get_zonegroup(self, zonegroup_id: str) -> RGWZonegroupResponse:
        """Get zonegroup configuration with caching."""
        if zonegroup_id not in self.zonegroups:
            try:
                self.zonegroups[zonegroup_id] = radosgw_admin_zonegroup_get(
                    zonegroup_id
                )
            except MalformedCephDataError as e:
                self._error(f"Failed to get zonegroup {zonegroup_id}: {e}")
                raise ValueError(f"Failed to get zonegroup: {e}")
        return self.zonegroups[zonegroup_id]

    def _get_buckets(self, user: str) -> list[dict[str, Any]]:
        """Get all buckets for a user with statistics."""
        try:
            bucket_stats = radosgw_admin_bucket_stats(user)
            return [bucket.model_dump() for bucket in bucket_stats]
        except MalformedCephDataError as e:
            self._error(f"Failed to get buckets for user {user}: {e}")
            return []

    def _get_bucket_objects(self, bucket: str) -> list[dict[str, Any]]:
        """Get all objects in a bucket."""
        try:
            objects = radosgw_admin_bucket_list_objects(bucket)
            return [obj.model_dump() for obj in objects]
        except MalformedCephDataError as e:
            self._error(f"Failed to list objects in bucket {bucket}: {e}")
            return []

    def _process_user(self, user: str) -> dict[str, Any]:
        """Process a single user and return usage statistics."""
        self._debug(f"Processing user: {user}")
        usage = {"from_stats": {}, "from_objects": {}}

        buckets = self._get_buckets(user)
        for bucket in buckets:
            name = bucket["bucket"]
            if bucket.get("tenant"):
                name = f"{bucket['tenant']}/{name}"
            self._debug(f"Bucket: {name}")

            # Get placement info - using Pydantic objects
            placement_rule = bucket["placement_rule"]
            zonegroup = self._get_zonegroup(bucket["zonegroup"])
            zone = self._get_zone(zonegroup.master_zone)

            # Find the placement pool configuration
            placement_pool_config = None
            for pp in zone.placement_pools:
                if pp.key == placement_rule:
                    placement_pool_config = pp.val
                    break

            # Access storage classes and data pool
            data_pool = placement_pool_config.storage_classes["STANDARD"].data_pool

            # Accumulate stats from bucket metadata
            if data_pool not in usage["from_stats"]:
                usage["from_stats"][data_pool] = {}
            u = usage["from_stats"][data_pool]

            for category, stats in bucket.get("usage", {}).items():
                if category not in u:
                    u[category] = {"size": 0, "num_objects": 0}
                u[category]["size"] += stats["size"]
                u[category]["num_objects"] += stats["num_objects"]

            # Optionally process objects
            if not self.process_objects:
                continue

            self._debug(f"Processing objects for bucket: {name}")
            objects = self._get_bucket_objects(name)
            self._debug(f"Got {len(objects)} objects for bucket: {name}")

            for obj in objects:
                storage_class = obj.get("meta", {}).get("storage_class")
                if not storage_class:
                    storage_class = "STANDARD"

                data_pool = placement_pool_config.storage_classes[
                    storage_class
                ].data_pool

                if data_pool not in usage["from_objects"]:
                    usage["from_objects"][data_pool] = {}
                u = usage["from_objects"][data_pool]

                category = self._category_name(obj.get("meta", {}).get("category", 1))
                if category not in u:
                    u[category] = {"size": 0, "num_objects": 0}
                u[category]["size"] += obj["meta"]["size"]
                u[category]["num_objects"] += 1

        self._debug(f"User: {user}: Usage: {usage}")
        return usage

    def _print_stats(
        self, usage: dict[str, Any], stats_type: str, stats_name: Optional[str] = None
    ) -> None:
        """Print usage statistics."""
        prefix = ""
        if stats_name:
            print(f"  {stats_name}:", file=self.output_stream)
            prefix = "  "

        for pool_name, s in usage[stats_type].items():
            osd_class = self._get_pool_osd_class(pool_name)
            print(f"{prefix}  Pool: {pool_name} ({osd_class})", file=self.output_stream)

            stats = s.get("rgw.main", {"size": 0, "num_objects": 0})
            amplification = self._get_storage_amplification(pool_name)
            stored_size = int(stats["size"] * amplification)

            print(
                f"{prefix}    Bytes: {stats['size']} (stored {stored_size})",
                file=self.output_stream,
            )
            print(
                f"{prefix}    Num objects: {stats['num_objects']}",
                file=self.output_stream,
            )

    def run(self) -> None:
        """Execute the complete user-df workflow."""
        for user in self.users:
            usage = self._process_user(user)

            print(f"User: {user}", file=self.output_stream)
            if self.process_objects:
                self._print_stats(usage, "from_stats", "From bucket stats")
                self._print_stats(usage, "from_objects", "From bucket object listing")
            else:
                self._print_stats(usage, "from_stats")

# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

from clyso.ceph.ai.data import CephData
from clyso.ceph.ai.pg.histogram import histogram, calculate_histogram, DataPoint, median
from collections import defaultdict
from types import SimpleNamespace


class PGHistogram:
    def __init__(self, osd_tree: dict, pg_dump: dict, flags):
        self.data = CephData()
        self.data.add_ceph_osd_tree(osd_tree)
        self.data.add_ceph_pg_dump(pg_dump)
        self.flags = flags

        # interface
        self.osd_weights = self.get_weights()
        self.osds = self.get_pg_stats()

    def print_ascii_histogram(self):
        if self.flags.normalize:
            self.values = [
                DataPoint(self.osds[osd] / self.osd_weights[osd]["crush_weight"], 1)
                for osd in self.osds
            ]
        else:
            self.values = [DataPoint(self.osds[osd], 1) for osd in self.osds]
        histogram(self.values, self.flags)

    def get_weights(self):
        osd_weights = dict()
        # https://github.com/cernceph/ceph-scripts/blob/master/tools/ceph-pg-histogram
        for osd in self.data.ceph_osd_tree["nodes"]:
            if osd["type"] == "osd":
                osd_id = osd["id"]
                reweight = float(osd["reweight"])
                crush_weight = float(osd["crush_weight"])
                osd_weights[osd_id] = dict()
                osd_weights[osd_id]["crush_weight"] = crush_weight
                osd_weights[osd_id]["reweight"] = reweight

        # print(osd_weights)
        return osd_weights

    def get_pg_stats(self):
        pg_data = (
            self.data.ceph_pg_dump["pg_map"]
            if "pg_map" in self.data.ceph_pg_dump
            else self.data.ceph_pg_dump
        )
        ceph_pg_stats = pg_data["pg_stats"]
        osds = defaultdict(int)
        for pg in ceph_pg_stats:
            poolid = pg["pgid"].split(".")[0]
            if self.flags.pools and poolid not in self.flags.pools:
                continue
            for osd in pg["acting"]:
                if osd >= 0 and osd < 1000000:
                    osds[osd] += 1

        return osds

    ## Histogram Json logic for CES UI

    def _get_per_pool_pg_stats(self, pool_id=None):
        """
        Extract PG counts per OSD grouped by pool from PG dump data.

        Args:
            pool_id: Optional pool ID filter

        Transforms:
            Input: [{"pgid": "37.1a", "acting": [0,1,2]}, {"pgid": "42.5c", "acting": [1,3]}]
            Output: {"37": {"osds": {0:1, 1:1, 2:1}, "total_pgs": 1}, "42": {"osds": {1:1, 3:1}, "total_pgs": 1}}

        Returns:
            If pool_id: (osds_dict, total_pgs) for single pool
            If None: pools_data dict with all pools
        """
        pg_data = (
            self.data.ceph_pg_dump["pg_map"]
            if "pg_map" in self.data.ceph_pg_dump
            else self.data.ceph_pg_dump
        )
        ceph_pg_stats = pg_data["pg_stats"]

        # Always collect all data first (single pass through PGs)
        pools_data = defaultdict(lambda: {"osds": defaultdict(int), "total_pgs": 0})

        for pg in ceph_pg_stats:
            poolid = pg["pgid"].split(".")[0]
            pools_data[poolid]["total_pgs"] += 1

            for osd in pg["acting"]:
                if osd >= 0 and osd < 1000000:
                    pools_data[poolid]["osds"][osd] += 1

        if pool_id is not None:
            pool_str = str(pool_id)
            return pools_data[pool_str]["osds"], pools_data[pool_str]["total_pgs"]
        else:
            return pools_data

    def _create_datapoints_for_osds(self, osds_dict, normalize=False):
        """
        Convert OSD PG counts to DataPoint objects for histogram calculation.

        Args:
            osds_dict: PG count per OSD like {0: 85, 1: 92}
            normalize: Apply crush weight normalization

        Transforms:
            Input: {0: 85, 1: 92}
            Output: [DataPoint(85, 1), DataPoint(92, 1)] or normalized values

        Returns:
            List of DataPoint(value, count=1) objects
        """
        if normalize:
            values = [
                DataPoint(osds_dict[osd] / self.osd_weights[osd]["crush_weight"], 1)
                for osd in osds_dict
            ]
        else:
            values = [DataPoint(osds_dict[osd], 1) for osd in osds_dict]

        return values

    def get_pg_distribution_json(self, pool_id=None, normalize=False, bins=10):
        """
        Core function behind the CES UI API to get PG distribution histogram as JSON.

        Args:
            pool_id: Optional single pool filter
            normalize: Apply crush weight normalization
            bins: Number of histogram bins

        Returns:
            Single pool: {"summary": {...}, "bins": [...], "totalPGs": int}
            All pools: {"pools": {"37": {summary: {...}, "bins": [...], "totalPGs": int}, "42": {summary: {...}, "bins": [...], "totalPGs": int}}}
        """
        if pool_id is not None:
            # Single pool case
            osds_dict, total_pgs = self._get_per_pool_pg_stats(pool_id)
            pool_json = self._generate_histogram_json(
                osds_dict, total_pgs, normalize, bins
            )
            return {"pools": {str(pool_id): pool_json}}
        else:
            # All pools case
            pools_data = self._get_per_pool_pg_stats()

            result = {"pools": {}}

            # Create individual pool summaries
            for pool_id, pool_data in pools_data.items():
                pool_json = self._generate_histogram_json(
                    pool_data["osds"], pool_data["total_pgs"], normalize, bins
                )
                result["pools"][pool_id] = pool_json

            return result

    def _generate_histogram_json(self, osds_dict, total_pgs, normalize, bins):
        """
        Generate histogram data in JSON format.
        Args:
            osds_dict: PG count per OSD like {0: 85, 1: 92}
            total_pgs: Total number of PGs
            normalize: Apply crush weight normalization
            bins: Number of histogram bins
        Returns:
            JSON object with summary, bins, and metadata
        """
        values = self._create_datapoints_for_osds(osds_dict, normalize)
        options = SimpleNamespace(
            bins=bins,
            min=None,
            max=None,
            custom_bins=None,
            logscale=False,
            no_mvsd=True,
        )
        histogram_data = calculate_histogram(values, options)
        return self._convert_histogram_data_to_json(histogram_data, total_pgs)

    def _convert_histogram_data_to_json(self, histogram_data, total_pgs):
        """
        Convert histogram data to JSON format.
        Args:
            histogram_data: Dictionary containing histogram data
            total_pgs: Total number of PGs
        Returns:
            JSON object with summary, bins, and metadata
        """
        min_v = float(histogram_data["min_v"])
        max_v = float(histogram_data["max_v"])
        boundaries = histogram_data["boundaries"]
        bucket_counts = histogram_data["bucket_counts"]
        samples = histogram_data["samples"]
        mvsd = histogram_data["mvsd"]
        accepted_data = histogram_data["accepted_data"]
        skipped = histogram_data["skipped"]

        bins = []
        bucket_min = min_v

        for i, boundary in enumerate(boundaries):
            bucket_max = float(boundary)
            count = bucket_counts[i]
            percentage = round((count / samples * 100), 2) if samples > 0 else 0

            bins.append(
                {
                    "rangeStart": float(f"{bucket_min:.4f}"),
                    "rangeEnd": float(f"{bucket_max:.4f}"),
                    "count": count,
                    "percentage": percentage,
                }
            )
            bucket_min = bucket_max

        summary = {
            "numSamples": samples,
            "min": float(f"{min_v:.2f}"),
            "max": float(f"{max_v:.2f}"),
            "skipped": skipped,
            "totalPGs": total_pgs,
        }

        if accepted_data and mvsd.is_started:
            summary.update(
                {
                    "mean": float(mvsd.mean()),
                    "variance": float(mvsd.var()),
                    "standardDeviation": float(mvsd.sd()),
                    "median": float(median(accepted_data, key=lambda x: x.value)),
                }
            )

        return {"summary": summary, "bins": bins}

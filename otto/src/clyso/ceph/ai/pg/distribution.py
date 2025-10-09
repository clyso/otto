from clyso.ceph.ai.data import CephData
from clyso.ceph.ai.pg.histogram import histogram, calculate_histogram, DataPoint, median
from clyso.ceph.api.schemas import OSDTree, PGDump
from collections import defaultdict
from types import SimpleNamespace
from typing import TypedDict, overload
import json


class PoolPGInfo(TypedDict):
    osds: dict[int, int]
    total_pgs: int


class PGHistogram:
    def __init__(self, osd_tree: dict, pg_dump: dict, flags):
        self.data = CephData()
        self.data.ceph_osd_tree = OSDTree.model_validate(osd_tree)
        self.data.ceph_pg_dump = PGDump.model_validate(pg_dump)
        self.flags = flags

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
        if self.data.ceph_osd_tree:
            for osd in self.data.ceph_osd_tree.nodes:
                if osd.type == "osd":
                    osd_id = osd.id
                    reweight = float(osd.reweight) if osd.reweight is not None else 1.0
                    crush_weight = (
                        float(osd.crush_weight) if osd.crush_weight is not None else 0.0
                    )
                    osd_weights[osd_id] = dict()
                    osd_weights[osd_id]["crush_weight"] = crush_weight
                    osd_weights[osd_id]["reweight"] = reweight

        return osd_weights

    def get_pg_stats(self):
        if not self.data.ceph_pg_dump:
            return defaultdict(int)

        ceph_pg_stats = self.data.ceph_pg_dump.pg_map.pg_stats
        osds = defaultdict(int)
        for pg in ceph_pg_stats:
            poolid = pg.pgid.split(".")[0]
            if self.flags.pools and poolid not in self.flags.pools:
                continue
            for osd in pg.acting:
                if osd >= 0 and osd < 1000000:
                    osds[osd] += 1

        return osds

    ## Histogram Json logic for CES UI

    @overload
    def _get_per_pool_pg_stats(self, pool_id: int) -> tuple[dict[int, int], int]: ...

    @overload
    def _get_per_pool_pg_stats(self, pool_id: None = None) -> dict[str, PoolPGInfo]: ...

    def _get_per_pool_pg_stats(
        self, pool_id: int | None = None
    ) -> tuple[dict[int, int], int] | dict[str, PoolPGInfo]:
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
        if not self.data.ceph_pg_dump:
            if pool_id is not None:
                return {}, 0
            else:
                return {}

        ceph_pg_stats = self.data.ceph_pg_dump.pg_map.pg_stats

        pools_data: dict[str, PoolPGInfo] = {}

        for pg in ceph_pg_stats:
            poolid = pg.pgid.split(".")[0]
            if poolid not in pools_data:
                pools_data[poolid] = {"osds": defaultdict(int), "total_pgs": 0}

            pools_data[poolid]["total_pgs"] += 1

            for osd in pg.acting:
                if osd >= 0 and osd < 1000000:
                    pools_data[poolid]["osds"][osd] += 1

        if pool_id is not None:
            pool_str = str(pool_id)
            if pool_str in pools_data:
                return pools_data[pool_str]["osds"], pools_data[pool_str]["total_pgs"]
            else:
                return {}, 0
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
            osds_dict, total_pgs = self._get_per_pool_pg_stats(pool_id)
            pool_data = self._generate_histogram_dict(
                osds_dict, total_pgs, normalize, bins
            )
            result = {"pools": {str(pool_id): pool_data}}
            return json.dumps(result, indent=2)
        else:
            pools_data = self._get_per_pool_pg_stats()

            result = {"pools": {}}

            for pool_id_str, pool_info in pools_data.items():
                pool_data_dict = self._generate_histogram_dict(
                    pool_info["osds"], pool_info["total_pgs"], normalize, bins
                )
                result["pools"][pool_id_str] = pool_data_dict

            return json.dumps(result, indent=2)

    def _generate_histogram_dict(self, osds_dict, total_pgs, normalize, bins):
        """
        Generate histogram data and get the resulting   dictionary.
        Args:
            osds_dict: PG count per OSD like {0: 85, 1: 92}
            total_pgs: Total number of PGs
            normalize: Apply crush weight normalization
            bins: Number of histogram bins
        Returns:
            Dictionary with summary, bins, and metadata
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
        return self._convert_histogram_data_to_dict(histogram_data, total_pgs)

    def _convert_histogram_data_to_dict(self, histogram_data, total_pgs):
        """
        Convert histogram data to dictionary format.
        Args:
            histogram_data: Dictionary containing histogram data
            total_pgs: Total number of PGs
        Returns:
            Dictionary with summary, bins, and metadata
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

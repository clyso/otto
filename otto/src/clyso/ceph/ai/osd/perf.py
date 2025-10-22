# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations
import statistics
from pydantic import BaseModel

from clyso.ceph.api.loaders import (
    load_osd_perf_from_file,
    load_osd_perf_from_stdin,
)
from clyso.ceph.api.commands import ceph_osd_perf_dump
from clyso.ceph.api.schemas import OSDPerfDumpResponse


class OSDMetric(BaseModel):
    """Schema for OSD performance metric data"""

    osd_id: int | str
    host: str
    device_class: str
    onode_hits: int
    onode_misses: int
    onode_hitrate: float


class OnodeDistributionAnalysis(BaseModel):
    """Schema for onode cache hit rate distribution analysis results"""

    total_osds: int
    mean_hitrate: float
    median_hitrate: float
    min_hitrate: float
    max_hitrate: float
    stdev_hitrate: float | None = None


class OSDPerf:
    """Handles OSD perf data
    Example:

    osd_perf = OSDPerf.from_subprocess(osd_id=5)

    or
    osd_perf = OSDPerf.from_file("/path/to/osd_perf_dump.json")

    or
    osd_perf = OSDPerf.from_stdin()

    # can be used it the same way:
    metrics = osd_perf.get_onode_metrics()
    print(f"OSD Hit Rate: {metrics.onode_hitrate:.2%}")
    print(f"Cache Hits: {metrics.onode_hits}")
    print(f"Cache Misses: {metrics.onode_misses}")
    """

    perf_dump: OSDPerfDumpResponse
    onode_hits: int
    onode_misses: int
    onode_hitrate: float

    def __init__(self, perf_dump: OSDPerfDumpResponse):
        self.perf_dump = perf_dump
        self._extract_onode_metrics()

    @classmethod
    def from_file(cls, file_path: str) -> OSDPerf:
        perf_dump = load_osd_perf_from_file(file_path)
        return cls(perf_dump)

    @classmethod
    def from_subprocess(cls, osd_id: int) -> OSDPerf:
        perf_dump = ceph_osd_perf_dump(osd_id)
        return cls(perf_dump)

    @classmethod
    def from_stdin(cls) -> OSDPerf:
        perf_dump = load_osd_perf_from_stdin()
        return cls(perf_dump)

    @classmethod
    def from_data(cls, perf_data: object) -> OSDPerf:
        perf_dump = OSDPerfDumpResponse.model_validate(perf_data)
        return cls(perf_dump)

    def _extract_onode_metrics(self) -> None:
        self.onode_hits = self.perf_dump.bluestore.onode_hits
        self.onode_misses = self.perf_dump.bluestore.onode_misses

        assert self.onode_hits is not None
        assert self.onode_misses is not None

        self.onode_hitrate = (
            (self.onode_hits / (self.onode_hits + self.onode_misses))
            if (self.onode_hits + self.onode_misses) > 0
            else 0.0
        )

    def get_onode_metrics(self) -> OSDMetric:
        return OSDMetric(
            osd_id="unknown",
            host="unknown",
            device_class="unknown",
            onode_hits=self.onode_hits,
            onode_misses=self.onode_misses,
            onode_hitrate=self.onode_hitrate,
        )

    def process(self) -> list[OSDMetric]:
        """Process performance data and return list of OSD metrics"""
        return [self.get_onode_metrics()]

    @classmethod
    def collect_single_osd_metrics(cls, osd_id: int) -> list[OSDMetric]:
        """Collect metrics from a single OSD"""
        perf_instance = cls.from_subprocess(osd_id)
        return perf_instance.process()

    @classmethod
    def process_perf_dump_file(cls, perf_data: object) -> list[OSDMetric]:
        """Process performance dump data from file"""
        perf_instance = cls.from_data(perf_data)
        return perf_instance.process()

    @classmethod
    def collect_osd_performance_metrics(
        cls,
        osd_ids: list[int],
        osd_metadata: dict[int, dict[str, str]],
    ) -> tuple[list[OSDMetric], list[int]]:
        """Collect performance metrics from multiple OSDs"""
        osd_metrics: list[OSDMetric] = []
        failed_osds: list[int] = []

        for osd_id in osd_ids:
            try:
                metrics = cls.collect_single_osd_metrics(osd_id)
                for metric in metrics:
                    if osd_id in osd_metadata:
                        metadata = osd_metadata[osd_id]
                        metric.osd_id = osd_id
                        metric.host = metadata.get("hostname", "unknown")
                        metric.device_class = metadata.get("device_class", "unknown")
                    osd_metrics.extend(metrics)
            except Exception as e:
                print(f"Failed to collect metrics for OSD {osd_id}: {e}")
                failed_osds.append(osd_id)

        return osd_metrics, failed_osds

    @classmethod
    def analyze_onode_distribution(
        cls, osd_metrics: list[OSDMetric]
    ) -> OnodeDistributionAnalysis:
        """Analyze onode cache hit rate distribution across OSDs"""
        return analyze_onode_distribution(osd_metrics)


def analyze_onode_distribution(
    osd_metrics: list[OSDMetric],
) -> OnodeDistributionAnalysis:
    """Analyze onode cache hit rate distribution across OSDs"""
    hit_rates = [osd.onode_hitrate for osd in osd_metrics]

    if not hit_rates:
        raise ValueError("No valid hit rate data found")

    result = OnodeDistributionAnalysis(
        total_osds=len(hit_rates),
        mean_hitrate=statistics.mean(hit_rates),
        median_hitrate=statistics.median(hit_rates),
        min_hitrate=min(hit_rates),
        max_hitrate=max(hit_rates),
        stdev_hitrate=statistics.stdev(hit_rates) if len(hit_rates) > 1 else None,
    )

    return result


def display_results(
    osd_metrics: list[OSDMetric], analysis: OnodeDistributionAnalysis
) -> None:
    """Display formatted results of OSD performance analysis"""
    print("\n" + "=" * 60)
    print("OSD ONODE CACHE PERFORMANCE ANALYSIS")
    print("=" * 60)

    print(f"\nTotal OSDs analyzed: {analysis.total_osds}")
    print(f"Mean hit rate: {analysis.mean_hitrate:.3f}")
    print(f"Median hit rate: {analysis.median_hitrate:.3f}")
    print(f"Hit rate range: {analysis.min_hitrate:.3f} - {analysis.max_hitrate:.3f}")

    if analysis.stdev_hitrate is not None:
        print(f"Standard deviation: {analysis.stdev_hitrate:.3f}")

    print("\nDetailed OSD Metrics:")
    print(
        f"{'OSD':<6} {'Host':<15} {'Class':<10} {'Hits':<12} {'Misses':<12} {'Hit Rate':<10}"
    )
    print("-" * 70)

    for osd in osd_metrics:
        print(
            f"{str(osd.osd_id):<6} {osd.host:<15} {osd.device_class:<10} "
            + f"{osd.onode_hits:<12} {osd.onode_misses:<12} {osd.onode_hitrate:<10.3f}"
        )


class OSDPerfFormatter:
    """Formatter class for OSD performance analysis results"""

    @staticmethod
    def display_results(
        analysis: OnodeDistributionAnalysis,
        osd_metrics: list[OSDMetric],
        failed_osds: list[int],
    ) -> None:
        """Display formatted analysis results"""
        display_results(osd_metrics, analysis)

        if failed_osds:
            print(f"\nFailed OSDs: {sorted(failed_osds)}")

# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import sys
from pathlib import Path
from typing import Any

from .perf import OSDPerf, OSDPerfFormatter
from clyso.ceph.ai.osd.topology import OSDTopology
from clyso.ceph.ai.osd.sampler import stratified_sample_osds


class OSDPerfCommand:
    """Command class that orchestrates OSD performance analysis workflow"""

    def __init__(self, args: Any):
        self.args = args
        self.osd_metrics: list[dict[str, Any]] = []
        self.failed_osds: list[int] = []
        self.analysis_results: dict[str, Any] = {}
        self.perf_class = OSDPerf
        self.formatter_class = OSDPerfFormatter

    def execute(self) -> None:
        """Execute the complete OSD performance analysis workflow"""
        print("Analyzing OSD onode performance...")

        if not self._validate_args():
            return

        if not self._collect_data():
            return

        self._run_analysis()

        self._display_results()

    def _validate_args(self) -> bool:
        """Validate argument combinations"""
        if self.args.osd_id and self.args.file:
            print("Error: Cannot specify both OSD ID and file input", file=sys.stderr)
            return False
        return True

    def _collect_data(self) -> bool:
        """Collect OSD performance data based on command arguments"""
        try:
            if self.args.osd_id:
                print(f"Analyzing OSD {self.args.osd_id}...")
                try:
                    topology = OSDTopology()
                    osd_metadata = topology.osd_metadata.get(self.args.osd_id, {})
                except Exception as e:
                    print(f"Warning: Could not get topology info: {e}")
                    osd_metadata = {}
                self.osd_metrics = self.perf_class.collect_single_osd_metrics(
                    self.args.osd_id
                )
                for metric in self.osd_metrics:
                    metric.osd_id = self.args.osd_id
                    metric.host = osd_metadata.get("hostname", "unknown")
                    metric.device_class = osd_metadata.get("device_class", "unknown")
                self.failed_osds = []

            elif self.args.file:
                self.osd_metrics = self._collect_from_file()
                self.failed_osds = []

            else:
                print("across cluster...")
                self.osd_metrics, self.failed_osds = self._collect_from_cluster()

            return len(self.osd_metrics) > 0

        except Exception as e:
            print(f"Error collecting OSD data: {e}", file=sys.stderr)
            return False

    def _collect_from_file(self) -> list[dict[str, Any]]:
        """Collect data from file input"""
        try:
            perf_data = json.loads(Path(self.args.file).read_text())
            return self.perf_class.process_perf_dump_file(perf_data)
        except FileNotFoundError:
            print(f"Error: Input file '{self.args.file}' not found", file=sys.stderr)
            return []
        except json.JSONDecodeError as e:
            print(
                f"Error: Invalid JSON in input file '{self.args.file}': {e}",
                file=sys.stderr,
            )
            return []

    def _collect_from_cluster(self) -> tuple[list[dict[str, Any]], list[int]]:
        """Collect data from cluster sampling"""

        try:
            topology = OSDTopology()
            (
                host_to_osds,
                device_class_to_osds,
                up_osds,
                osd_metadata,
            ) = topology.get_topology_info()
        except Exception as e:
            print(f"Error loading cluster information: {e}")
            return [], []

        sample_size: int = self.args.num_osds
        print(f"Cluster has {len(up_osds)} UP OSDs, sampling {sample_size} OSDs")

        sampled_osds = stratified_sample_osds(
            device_class_to_osds, up_osds, sample_size
        )
        print(f"Sampled OSDs: {sorted(sampled_osds)}")

        print("Collecting onode performance metrics...")
        return self.perf_class.collect_osd_performance_metrics(
            sampled_osds, osd_metadata
        )

    # use this function to extend the osd perf metrics
    def _run_analysis(self) -> None:
        """Run analysis on collected OSD metrics"""
        if not self.osd_metrics:
            print("No performance metrics collected")
            return

        self.analysis_results["onode"] = self.perf_class.analyze_onode_distribution(
            self.osd_metrics
        )

        # TODO: Future extension point:
        # self.analysis_results["rocksdb"] = OSDPerf.analyze_rocksdb_distribution(self.osd_metrics)
        # self.analysis_results["bluestore"] = OSDPerf.analyze_bluestore_distribution(self.osd_metrics)

    def _display_results(self) -> None:
        """Display analysis results"""
        if not self.osd_metrics:
            print("No performance metrics to display")
            return

        onode_analysis: dict[str, Any] = self.analysis_results.get("onode", {})
        self.formatter_class.display_results(
            onode_analysis, self.osd_metrics, self.failed_osds
        )

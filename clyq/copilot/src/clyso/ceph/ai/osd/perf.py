import json
import math
import random
import statistics
from typing import Optional, Tuple
from collections import defaultdict
from clyso.ceph.ai.common import jsoncmd


class OSDPerf:
    def __init__(self, osd_id: int):
        self.osd_id = osd_id
        self.perf_dump = self._collect_perf_data()
        bluestore = self.perf_dump["bluestore"]
        self.onode_hits = bluestore.get("onode_hits", 0)
        self.onode_misses = bluestore.get("onode_misses", 0)
        self.onode_hitrate = (
            (self.onode_hits / (self.onode_hits + self.onode_misses))
            if (self.onode_hits + self.onode_misses) > 0
            else 0
        )

    def _collect_perf_data(self) -> dict:
        try:
            return jsoncmd(f"ceph tell osd.{self.osd_id} perf dump")
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON response from OSD {self.osd_id} perf dump command: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error collecting perf data for OSD {self.osd_id}: {e}"
            ) from e

    def get_onode_metrics_json(self) -> str:
        onode_metrics = {
            "onode_hits": self.onode_hits,
            "onode_misses": self.onode_misses,
            "onode_hitrate": self.onode_hitrate,
        }
        return json.dumps(onode_metrics)

    @classmethod
    def collect_osd_performance_metrics(
        cls, sampled_osds: list, osd_metadata: dict
    ) -> Tuple[list, list]:
        """Collect onode performance metrics from sampled OSDs"""
        osd_metrics = []
        failed_osds = []

        for osd_id in sampled_osds:
            try:
                osd_perf = cls(osd_id)
                metadata = osd_metadata[osd_id]

                osd_metrics.append(
                    {
                        "osd_id": osd_id,
                        "host": metadata["host"],
                        "device_class": metadata["device_class"],
                        "onode_hits": osd_perf.onode_hits,
                        "onode_misses": osd_perf.onode_misses,
                        "onode_hitrate": osd_perf.onode_hitrate,
                    }
                )

            except Exception as e:
                failed_osds.append(osd_id)

        return osd_metrics, failed_osds

    @staticmethod
    def analyze_onode_distribution(osd_metrics: list) -> dict:
        """Analyze onode hit rate distribution"""
        if not osd_metrics:
            return {}

        hitrates = [m["onode_hitrate"] for m in osd_metrics]

        analysis = {
            "overall": {
                "count": len(osd_metrics),
                "mean": statistics.mean(hitrates),
                "median": statistics.median(hitrates),
                "min": min(hitrates),
                "max": max(hitrates),
                "std_dev": statistics.stdev(hitrates) if len(hitrates) > 1 else 0.0,
            }
        }

        return analysis

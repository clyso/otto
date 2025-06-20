# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
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

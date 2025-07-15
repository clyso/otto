# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

from collections import defaultdict
from clyso.ceph.ai.common import jsoncmd
from typing import Optional, Tuple, List, Dict


class OSDTopology:
    """Manages OSD cluster topology information"""

    def __init__(self):
        self.osd_tree = jsoncmd("ceph osd tree --format=json")
        self.nodes = self.osd_tree.get("nodes", [])
        self._host_to_osds = None
        self._device_class_to_osds = None
        self._up_osds = None
        self._osd_metadata = None
        self._parse_topology()

    def _find_osd_host(self, osd_id: int) -> Optional[str]:
        """Find the host name for a given OSD ID"""
        for node in self.nodes:
            if node["type"] == "host" and osd_id in node.get("children", []):
                return node["name"]
        return None

    def _parse_topology(self):
        """Parse OSD tree and build topology mappings"""
        host_to_osds = defaultdict(list)
        device_class_to_osds = defaultdict(list)
        up_osds = []
        osd_metadata = {}

        for node in self.nodes:
            if node["type"] == "osd" and node.get("status") == "up":
                osd_id = node["id"]
                up_osds.append(osd_id)

                host_name = self._find_osd_host(osd_id)
                if host_name:
                    host_to_osds[host_name].append(osd_id)

                device_class = node.get("device_class", "unknown")
                device_class_to_osds[device_class].append(osd_id)

                osd_metadata[osd_id] = {
                    "host": host_name,
                    "device_class": device_class,
                }

        self._host_to_osds = dict(host_to_osds)
        self._device_class_to_osds = dict(device_class_to_osds)
        self._up_osds = up_osds
        self._osd_metadata = osd_metadata

    def get_topology_info(
        self,
    ) -> Tuple[
        Dict[str, List[int]], Dict[str, List[int]], List[int], Dict[int, Dict[str, str]]
    ]:
        return (
            self.host_to_osds,
            self.device_class_to_osds,
            self.up_osds,
            self.osd_metadata,
        )

    @property
    def host_to_osds(self) -> Dict[str, List[int]]:
        return self._host_to_osds

    @property
    def device_class_to_osds(self) -> Dict[str, List[int]]:
        return self._device_class_to_osds

    @property
    def up_osds(self) -> List[int]:
        return self._up_osds

    @property
    def osd_metadata(self) -> Dict[int, Dict[str, str]]:
        return self._osd_metadata

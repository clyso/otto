# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

from collections import defaultdict

from clyso.ceph.api.commands import ceph_osd_tree
from clyso.ceph.api.schemas import OSDTree, OSDNode


class OSDTopology:
    """Manages OSD cluster topology information"""

    def __init__(self):
        self.osd_tree: OSDTree = ceph_osd_tree()
        self.nodes: list[OSDNode] = self.osd_tree.nodes
        self._host_to_osds: dict[str, list[int]] | None = None
        self._device_class_to_osds: dict[str, list[int]] | None = None
        self._up_osds: list[int] | None = None
        self._osd_metadata: dict[int, dict[str, str]] | None = None
        self._host_lookup: dict[int, str] | None = None
        self._parse_topology()

    def _build_host_lookup(self) -> dict[int, str]:
        host_lookup: dict[int, str] = {}
        for node in self.nodes:
            if node.type == "host" and node.children:
                for child_id in node.children:
                    host_lookup[child_id] = node.name
        return host_lookup

    def _find_osd_host(self, osd_id: int) -> str | None:
        """Find the host name for a given OSD ID using efficient lookup"""
        if self._host_lookup is None:
            self._host_lookup = self._build_host_lookup()
        return self._host_lookup.get(osd_id)

    def _parse_topology(self):
        """Parse OSD tree and build topology mappings"""
        host_to_osds: dict[str, list[int]] = defaultdict(list)
        device_class_to_osds: dict[str,list[int]] = defaultdict(list)
        up_osds: list[int] = []
        osd_metadata: dict[int, dict[str,str]] = {}

        for node in self.nodes:
            if node.type == "osd" and node.status == "up":
                osd_id = node.id
                up_osds.append(osd_id)

                # if we can't find the host name an OSD belongs to we will skip this OSD
                host_name = self._find_osd_host(osd_id)
                if host_name:
                    host_to_osds[host_name].append(osd_id)

                    device_class = node.device_class or "unknown"
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
    ) -> tuple[
        dict[str, list[int]], dict[str, list[int]], list[int], dict[int, dict[str, str]]
    ]:
        return (
            self.host_to_osds,
            self.device_class_to_osds,
            self.up_osds,
            self.osd_metadata,
        )

    @property
    def host_to_osds(self) -> dict[str, list[int]]:
        if self._host_to_osds is None:
            return {}
        return self._host_to_osds

    @property
    def device_class_to_osds(self) -> dict[str, list[int]]:
        if self._device_class_to_osds is None:
            return {}
        return self._device_class_to_osds

    @property
    def up_osds(self) -> list[int]:
        if self._up_osds is None:
            return []
        return self._up_osds

    @property
    def osd_metadata(self) -> dict[int, dict[str, str]]:
        if self._osd_metadata is None:
            return {}
        return self._osd_metadata

# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

from clyso.ceph.api.schemas import CephReport, OSDTree, PGDump


class CephData:
    def __init__(self) -> None:
        self.ceph_report: CephReport | None = None
        self.ceph_config_dump: list | None = None
        self.ceph_osd_tree: OSDTree | None = None
        self.ceph_pg_dump: PGDump | None = None

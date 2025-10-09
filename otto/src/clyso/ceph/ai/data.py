from clyso.ceph.api.schemas import CephReport, OSDTree, PGDump


class CephData:
    def __init__(self) -> None:
        self.ceph_report: CephReport | None = None
        self.ceph_config_dump: list | None = None
        self.ceph_osd_tree: OSDTree | None = None
        self.ceph_pg_dump: PGDump | None = None

    def add_ceph_report(self, ceph_report: CephReport) -> None:
        self.ceph_report = ceph_report

    def add_ceph_config_dump(self, ceph_config_dump: list) -> None:
        self.ceph_config_dump = ceph_config_dump

    def add_ceph_osd_tree(self, ceph_osd_tree: OSDTree) -> None:
        self.ceph_osd_tree = ceph_osd_tree

    def add_ceph_pg_dump(self, ceph_pg_dump: PGDump) -> None:
        self.ceph_pg_dump = ceph_pg_dump

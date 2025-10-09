from clyso.ceph.api.schemas import CephReport, OSDTree, PGDump


class CephData:
    def __init__(self) -> None:
        self.ceph_report: CephReport | None = None
        self.ceph_config_dump: list | None = None
        self.ceph_osd_tree: OSDTree | None = None
        self.ceph_pg_dump: PGDump | None = None

    def add_ceph_report(self, ceph_report: dict | CephReport) -> None:
        if isinstance(ceph_report, dict):
            self.ceph_report = CephReport.model_validate(ceph_report)
        else:
            self.ceph_report = ceph_report

    def add_ceph_config_dump(self, ceph_config_dump: list) -> None:
        self.ceph_config_dump = ceph_config_dump

    def add_ceph_osd_tree(self, ceph_osd_tree: dict | OSDTree) -> None:
        if isinstance(ceph_osd_tree, dict):
            self.ceph_osd_tree = OSDTree.model_validate(ceph_osd_tree)
        else:
            self.ceph_osd_tree = ceph_osd_tree

    def add_ceph_pg_dump(self, ceph_pg_dump: dict | PGDump) -> None:
        if isinstance(ceph_pg_dump, dict):
            self.ceph_pg_dump = PGDump.model_validate(ceph_pg_dump)
        else:
            self.ceph_pg_dump = ceph_pg_dump

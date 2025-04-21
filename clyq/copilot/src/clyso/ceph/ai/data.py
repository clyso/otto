class CephData:
    def __init__(self) -> None:
        self.ceph_report = {}
        self.ceph_config_dump = {}
        self.ceph_osd_tree = {}
        self.ceph_pg_dump = {}

    # output from `ceph report -f json`
    def add_ceph_report(self, ceph_report: dict) -> None:
        self.ceph_report = ceph_report

    # output from `ceph config dump -f json`
    def add_ceph_config_dump(self, ceph_config_dump: dict) -> None:
        self.ceph_config_dump = dict(ceph_config_dump)

    # output from `ceph osd tree -f json`
    def add_ceph_osd_tree(self, ceph_osd_tree: dict) -> None:
        self.ceph_osd_tree = ceph_osd_tree

    def add_ceph_pg_dump(self, ceph_pg_dump: dict) -> None:
        self.ceph_pg_dump = ceph_pg_dump

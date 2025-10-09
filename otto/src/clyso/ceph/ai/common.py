import sys
import argparse

CEPH_FILES = {
    "ceph-report": "cluster_health-report",
    "config_dump": "ceph_cluster_info-config_dump.json",
    "osd_tree": "osd_info-tree.json",
    "pg_dump": "pg_info-dump.json",
}


class OttoParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super(OttoParser, self).__init__(*args, **kwargs)

    def error(self, message):
        otto_error = "{cluster, pool, toolkit}"

        if otto_error in message:
            print(f"{message}")
            self.print_help()
            sys.exit(2)

        self.print_usage()
        print(f"otto: error: {message}")
        sys.exit(2)

# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import sys
import argparse
import math
from pathlib import Path

CEPH_FILES = {
    "ceph-report": "cluster_health-report",
    "config_dump": "ceph_cluster_info-config_dump.json",
    "osd_tree": "osd_info-tree.json",
    "pg_dump": "pg_info-dump.json",
}


def json_loads(json_data):
    def parse_json_constants(arg):
        if arg == "Infinity":
            return math.inf
        elif arg == "-Infinity":
            return -math.inf
        elif arg == "NaN":
            return math.nan
        return None

    # Replace " inf," with " Infinity," to avoid json parsing error:
    # python json module does not support "inf", "-inf", "nan" as valid
    # json constants
    json_data = json_data.replace(" inf,", " Infinity,")
    json_data = json_data.replace(" -inf,", " -Infinity,")
    json_data = json_data.replace(" nan,", " NaN,")

    return json.loads(json_data, parse_constant=parse_json_constants)


def json_load(f):
    return json_loads(f.read())


def load_ceph_report_file(filepath):
    """Load and parse ceph report file"""
    try:
        content = Path(filepath).read_text()
        return json_loads(content)
    except Exception as e:
        print(
            f"Error: Failed to read ceph report from {filepath}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


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

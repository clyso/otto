# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import subprocess
import os
import sys
import argparse
import math

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


def jsoncmd(command, timeout=30):
    try:
        with open(os.devnull, "w") as devnull:
            out = subprocess.check_output(
                command.split(), stderr=devnull, timeout=timeout
            ).decode("utf-8")
    except subprocess.CalledProcessError:
        print("ERROR: ceph command is no where to be found")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"ERROR: command '{command}' timed out after {timeout} seconds")
        sys.exit(1)
    return json_loads(out)


def load_ceph_report_file(filepath):
    """Load and parse ceph report file"""
    try:
        with open(filepath, "r") as file:
            return json_load(file)
    except Exception as e:
        print(
            f"Error: Failed to read ceph report from {filepath}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

class CopilotParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super(CopilotParser, self).__init__(*args, **kwargs)
        self.print_help = self.add_extra_help_message(self.print_help)

    def error(self, message):
        copilot_error = "{cluster, pool, toolkit}"

        if copilot_error in message:
            print(f"{message}")
            self.print_help()
            sys.exit(2)

        self.print_usage()
        print(f"copilot: error: {message}")
        sys.exit(2)

    def add_extra_help_message(self, func):
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)  # Call the original function
            print(
                "
If you encounter any bugs, please report them at https://ticket.clyso.com/"
            )

        return wrapper

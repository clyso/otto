# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

from clyso.ceph.ai.data import CephData
from clyso.ceph.ai.result import AIResult

from . import config as aiconfig
from . import report as aireport


def generate_result(report_json=None, config_dump_json=None):
    if config_dump_json is None:
        config_dump_json = {}
    if report_json is None:
        report_json = {}
    data = CephData()
    data.add_ceph_report(report_json)
    data.add_ceph_config_dump(config_dump_json)

    res = AIResult()

    res.add_section("Cluster")  # Report on the cluster info and health
    res.add_section("Version")  # Check the running versions
    res.add_section("Operating System")  # Check the running versions
    res.add_section("Capacity")  # Check the cluster capacity
    res.add_section("Pools")  # Check the pools
    res.add_section("CephFS")  # Check the Filesystems
    res.add_section("MON Health")  # Check the MONs
    res.add_section("OSD Health")  # Check the OSDs

    aireport.update_result(res, data)
    aiconfig.update_result(res, data)

    return res

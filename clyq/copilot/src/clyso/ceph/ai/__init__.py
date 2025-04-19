# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

from . import config as aiconfig
from . import devices as aidevices
from . import perf as aiperf
from . import report as aireport
from clyso.ceph.ai.data import CephData
from clyso.ceph.ai.result import AIResult

def generate_result(report_json = {}, config_dump_json = {}):

    data = CephData()
    data.add_ceph_report(report_json)
    data.add_ceph_config_dump(config_dump_json)

    res = AIResult()

    res.add_section('Cluster')        # Report on the cluster info and health
    res.add_section('Version')        # Check the running versions
    res.add_section('Operating System') # Check the running versions
    res.add_section('Capacity')       # Check the cluster capacity
#    res.add_section('Config')         # Check the config and flags
    res.add_section('Pools')          # Check the pools
#    res.add_section('Block Storage')  # Check the Block Storage
#    res.add_section('Object Storage') # Check the Object Storage
    res.add_section('CephFS')         # Check the Filesystems
    res.add_section('MON Health')     # Check the MONs
    res.add_section('OSD Health')     # Check the OSDs
#    res.add_section('MDS Health')     # Check the MDSs
#    res.add_section('RGW Health')     # Check the RGWs

#    res.add_info_result('Config', 'Coming Soon!', 'Check again soon for improved analysis!', [])
#    res.add_info_result('Block Storage', 'Coming Soon!', 'Check again soon for an improved analysis!', [])
#    res.add_info_result('Object Storage', 'Coming Soon!', 'Check again soon for an improved analysis!', [])
#    res.add_info_result('MDS Health', 'Coming Soon!', 'Check again soon for an improved analysis!', [])
#    res.add_info_result('RGW Health', 'Coming Soon!', 'Check again soon for an improved analysis!', [])

    aireport.update_result(res, data)
    aiconfig.update_result(res, data)

    return res

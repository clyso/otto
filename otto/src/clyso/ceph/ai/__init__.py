from clyso.ceph.ai.data import CephData
from clyso.ceph.ai.result import AIResult

from . import config as aiconfig
from . import report as aireport


def generate_result(ceph_data: CephData) -> AIResult:
    """
    Generate AI analysis result from Ceph cluster data.

    Args:
        ceph_data: CephData object with populated cluster data

    Returns:
        AIResult with analysis sections and recommendations
    """
    res: AIResult = AIResult()

    res.add_section("Cluster")
    res.add_section("Version")
    res.add_section("Operating System")
    res.add_section("Capacity")
    res.add_section("Pools")
    res.add_section("CephFS")
    res.add_section("MON Health")
    res.add_section("OSD Health")
    res.add_section("Configuration")

    aireport.update_result(res, ceph_data)
    aiconfig.update_result(res, ceph_data)

    return res

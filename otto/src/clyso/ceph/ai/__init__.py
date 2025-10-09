from clyso.ceph.ai.data import CephData
from clyso.ceph.ai.result import AIResult
from clyso.ceph.api.schemas import CephReport

from . import config as aiconfig
from . import report as aireport


def generate_result(
    ceph_data: CephData | None = None,
    report_json: dict[str, object] | CephReport | None = None,
    config_dump_json: list[dict[str, object]] | None = None,
) -> AIResult:
    """
    Args:
        ceph_data: CephData object (preferred method)
        report_json: Legacy parameter for backward compatibility (dict or CephReport)
        config_dump_json: Legacy parameter for backward compatibility
    """

    if ceph_data is not None:
        data = ceph_data
    else:
        # Backward compatibility: create CephData from individual parameters
        if config_dump_json is None:
            config_dump_json = []
        if report_json is None:
            report_json = {}
        data = CephData()
        # Convert dict to CephReport if needed
        if isinstance(report_json, dict):
            report_json = CephReport.model_validate(report_json)
        data.add_ceph_report(ceph_report=report_json)
        data.add_ceph_config_dump(ceph_config_dump=config_dump_json)

    res: AIResult = AIResult()

    res.add_section("Cluster")  # Report on the cluster info and health
    res.add_section("Version")  # Check the running versions
    res.add_section("Operating System")  # Check the running versions
    res.add_section("Capacity")  # Check the cluster capacity
    res.add_section("Pools")  # Check the pools
    res.add_section("CephFS")  # Check the Filesystems
    res.add_section("MON Health")  # Check the MONs
    res.add_section("OSD Health")  # Check the OSDs
    res.add_section("Configuration")  # Check configuration settings

    aireport.update_result(res, data)
    aiconfig.update_result(res, data)

    return res

import sys
import traceback
from math import ceil, fsum, log2

import humanize
from packaging import version

from clyso.ceph.ai.crush import Crush
from clyso.ceph.ai.helpers import (
    healthdb,
    known_bugs,
    osdb,
    recommended_versions,
    to_major,
    to_release,
    to_version,
    versiondb,
)

# A list of all check_report functions
check_functions = []


# Decorator to add to check_all
def add_check(func):
    check_functions.append(func)
    return func


@add_check
def check_report_header(result, data) -> None:
    report = data.ceph_report
    section = "Cluster"
    check = "Cluster Info"

    id = report["monmap"]["fsid"]
    v = report["version"]
    ts = report["timestamp"]
    ctime = report["monmap"]["created"]

    summary = f"Cluster info for fsid {id}"
    detail = [f"Version {v}"]
    detail.append(f"Cluster Creation Timestamp: {ctime}")
    detail.append(f"Report Timestamp: {ts}")

    result.add_info_result(section, check, summary, detail)


@add_check
def check_report_version(result, data):
    report = data.ceph_report

    ver = to_version(report["version"])
    major = to_major(ver)
    release_info = versiondb["releases"].get(major, {})

    if release_info.get("version", "old") == "old":
        return _handle_very_old_version(result, ver, recommended_versions())

    if release_info.get("version") == ver and release_info.get("recommended", False):
        return _handle_recommended_version(result, ver)

    return _handle_non_recommended_version(
        result, ver, recommended_versions(), release_info.get("version")
    )


def _handle_very_old_version(result, ver, rec_versions) -> None:
    summary = f"CRITICAL: Running very old release {ver}"
    detail = [
        f"Cluster is running a very old release {ver}. Clyso highly recommends upgrading to one of the stable releases: {', '.join(rec_versions)}."
    ]
    recommend = [f"Upgrade to one of the stable releases: {', '.join(rec_versions)}."]
    result.force_fail = True
    result.add_check_result("Version", "Release", "FAIL", summary, detail, recommend)


def _handle_recommended_version(result, ver) -> None:
    summary = f"Running a recommended stable release {ver}"
    detail = [
        f"Cluster is running {ver}. This is one of the recommended stable releases."
    ]
    result.add_check_result("Version", "Release", "PASS", summary, detail, [])


def _handle_non_recommended_version(result, ver, rec_versions, rec_minor) -> None:
    summary = "Not running a recommended stable release"
    compatible_versions = [
        v for v in rec_versions if version.parse(v) >= version.parse(ver)
    ]

    if compatible_versions:
        detail = [
            f"Cluster is running {ver}. Clyso highly recommends one of the stable releases: {', '.join(compatible_versions)}."
        ]
        recommend = [
            f"Upgrade to one of the stable releases: {', '.join(compatible_versions)}."
        ]
    else:
        detail = [
            f"Cluster is running {ver}, which is newer than our recommended versions. Please ensure you're running a stable release."
        ]
        recommend = [
            "Your version is newer than our recommended versions. It is not possible to downgrade to a previous release so we recommend waiting for a stable release."
        ]

    if rec_minor and version.parse(ver) < version.parse(rec_minor):
        detail.append(
            f"{rec_minor} is the recommended bugfix release for your current version."
        )
        if rec_minor not in compatible_versions:
            recommend.append(f"Alternatively, upgrade to {rec_minor}.")

    result.add_check_result("Version", "Release", "WARN", summary, detail, recommend)


@add_check
def check_report_known_bugs(result, data) -> None:
    report = data.ceph_report
    section = "Version"
    check = "Check for Known Issues in Running Version"
    detail = []
    recommend = []
    passfail = "PASS"

    summary = "No known severe bugs in running release"

    # look for low severity bugs
    (last_updated, bugs) = known_bugs(report["version"], "low")
    for bug in bugs:
        passfail = "WARN"
        summary = f"Info: Found {len(bugs)} low severity issue(s) in running version {report['version']}"
        detail.append(
            f"{bug['name']} (severity: {bug['severity']}): {bug['description']}"
        )
        recommend.append(
            f"{bug['name']} (severity: {bug['severity']}): {bug['recommendation']}"
        )

    (last_updated, bugs) = known_bugs(report["version"], "high")
    for bug in bugs:
        passfail = "FAIL"
        summary = f"CRITICAL: Found {len(bugs)} high severity bugs(s) in running version {report['version']}"
        detail.append(
            f"{bug['name']} (severity: {bug['severity']}): {bug['description']}"
        )
        recommend.append(
            f"{bug['name']} (severity: {bug['severity']}): {bug['recommendation']}"
        )
        result.force_fail = True

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_mixed_versions(result, data) -> None:
    report = data.ceph_report
    section = "Version"
    check = "Mixing Ceph Versions"
    detail = []
    recommend = []

    report["version"]
    osds = report["osd_metadata"]

    versions = []
    for osd in osds:
        if "ceph_version_short" in osd:
            v = osd["ceph_version_short"]
        elif "ceph_version" in osd:
            v = osd["ceph_version"]
        else:
            continue
        if v not in versions:
            versions.append(v)

    if len(versions) == 0:
        passfail = "WARN"
        summary = "Running Unknown Ceph Versions"
        detail.append("It was not possible to determine the running Ceph versions.")
        recommend.append("Contact support@clyso.com for assistance.")
    elif len(versions) == 1:
        passfail = "PASS"
        summary = "Running Equal Ceph Versions"
        detail.append(f"Ceph daemons are all running version {','.join(versions)}.")
    else:
        passfail = "FAIL"
        summary = "Running Mixed Ceph Versions"
        detail.append(
            f"Found several versions of Ceph in the cluster, namely {','.join(versions)}. This may lead to unexpected issues, including data corruption in the worst case."
        )
        recommend.append("Upgrade all Ceph daemons to run the same version.")

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_health(result, data) -> None:
    report = data.ceph_report
    section = "Cluster"
    check = "Health"
    recommend = []

    health = report["health"]

    if health["status"] == "HEALTH_OK":
        summary = "HEALTH_OK"
        detail = ["Cluster is healthy"]
        result.add_check_result(section, check, "PASS", summary, detail, recommend)
        return

    summary = f"{health['status']} with {len(health['checks'])} warnings"
    detail = []
    for c, d in health["checks"].items():
        detail.append(
            f"Internal health check {c} with severity {d['severity']} reports {d['summary']['message']}"
        )
        advice = healthdb["warnings"].get(c)
        if advice:
            recommend.append(advice)

    if health["status"] == "HEALTH_WARN":
        passfail = "WARN"
    if health["status"] == "HEALTH_ERR":
        passfail = "FAIL"
    result.add_check_result(section, check, passfail, summary, detail, recommend)

    # TODO: add Advice about cleaning useless warnings like
    # Pool not scrubbed in time
    # PG numbers imbalance

    # TODO: Advice about fixing more risky warnings like
    # OSD errors – too many failed reads, inconsistent
    # PG availability issues
    # CephFS issues
    # Clients not responding to caps release
    # Clients not keeping up with tid
    # MDS not trimming log segments


@add_check
def check_monmap_epoch(result, data) -> None:
    report = data.ceph_report
    section = "MON Health"
    check = "Monitor Committed Maps"
    recommend = []

    monmap_epoch = report["monmap"]["epoch"]

    if monmap_epoch > 100:
        summary = "Large number of monmaps"
        detail = [
            f"This cluster has a very large number of monmaps ({monmap_epoch}). If this number is increasing rapidly, it may indicate a problem. Please contact support."
        ]
        passfail = "WARN"
    else:
        summary = "Correct number of monmaps"
        detail = [
            f"This cluster has a reasonably small number of monmaps ({monmap_epoch}), which is normal."
        ]
        passfail = "PASS"
    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_num_mons(result, data) -> None:
    report = data.ceph_report
    section = "MON Health"
    check = "Number of Monitors"
    summary = ""

    num_mons = len(report["monmap"]["mons"])
    num_osds = len(report["osdmap"]["osds"])

    if num_mons > 5:
        summary = "Too many Monitors"
        detail = [
            f"Cluster has too many ceph-mon daemons ({num_mons}). Running more than 5 ceph-mons is not recommended in most environments due to the overheads keeping MONs in sync."
        ]
        recommend = ["Deprovision ceph-mon daemons until you have five or fewer."]
        passfail = "WARN"
        result.add_check_result(section, check, passfail, summary, detail, recommend)
    elif num_osds > 1000 and num_mons < 5:
        summary = "Insufficient Monitors for large cluster"
        detail = [
            f"Cluster has insufficient ceph-mon daemons ({num_mons}) for the large number of OSDs ({num_osds}). Above 1000 OSDs, it is recommended to use 5 monitors."
        ]
        recommend = ["Spawn additional ceph-mon daemons until you have five."]
        passfail = "WARN"
        result.add_check_result(section, check, passfail, summary, detail, recommend)
    elif num_mons < 3:
        summary = "Insufficient Monitors"
        detail = [
            f"Cluster has insufficient ceph-mon daemons ({num_mons}). Running fewer than 3 monitors means that each ceph-mon is a single point of failure."
        ]
        recommend = ["Spawn additional ceph-mon daemons until you have at least three."]
        passfail = "FAIL"
        result.add_check_result(section, check, passfail, summary, detail, recommend)
    else:
        summary = "Sufficient Number of Monitors"
        detail = [
            f"Cluster has a sufficient number of ceph-mon daemons ({num_mons}) for its size."
        ]
        recommend = []
        passfail = "PASS"
        result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_even_num_mons(result, data) -> None:
    report = data.ceph_report
    section = "MON Health"
    check = "Even Number of Monitors"

    num_mons = len(report["monmap"]["mons"])
    if num_mons % 2 == 0:
        summary = "Even number of Monitors"
        detail = [
            f"Cluster has an even number of ceph-mon daemons ({num_mons}). This is not a problem however operators should be aware that the {ceil(num_mons / 2 + 1)} of the monitors must be up to maintain quorum."
        ]
        recommend = ["Run an odd number of ceph-mon daemons"]
        passfail = "WARN"
        result.add_check_result(section, check, passfail, summary, detail, recommend)
    else:
        summary = "Odd number of Monitors"
        detail = [
            f"Cluster has an odd number of ceph-mon daemons ({num_mons}). This is ideal for the underlying Monitor PAXOS quorum algorithm. Quorum will be maintained as long as {ceil(num_mons / 2 + 1)} ceph-mon daemons are up and healthy."
        ]
        recommend = []
        passfail = "PASS"
        result.add_check_result(section, check, passfail, summary, detail, recommend)


# TODO: “monmap”:
# Confirm min mon release == “version”
# Stretch mode
# Quorum


@add_check
def check_report_osdmap(result, data) -> None:
    report = data.ceph_report
    section = "OSD Health"
    osdmap = report["osdmap"]
    check = "Check osdmap flags"
    recommend = []
    passfail = "PASS"

    # check flags
    if "flags_set" in osdmap:
        flags = [
            "pglog_hardlimit",
            "purged_snapdirs",
            "recovery_deletes",
            "sortbitwise",
        ]
        missing = []
        for f in flags:
            if f not in osdmap["flags_set"]:
                passfail = "FAIL"
                missing.append(f)
        if passfail == "FAIL":
            summary = "Missing important osdmap flags!"
            missing = ", ".join(missing)
            detail = [f"Cluster missing osdmap flags: {missing}"]
            result.add_check_result(
                section, check, passfail, summary, detail, recommend
            )
        else:
            summary = "OSDMap has correct flags set."
            flags = ", ".join(flags)
            detail = [f"osdmap has the expected flags: {flags}"]
            result.add_check_result(
                section, check, passfail, summary, detail, recommend
            )
    else:
        passfail = "WARN"
        summary = "Unable to check osdmap flags"
        detail = ["Ceph report does not include the osdmap flags_set field."]
        recommend = ["Contact support@clyso.com for assistance."]
        result.add_check_result(section, check, passfail, summary, detail, recommend)

    # TODO: check ratios

    # check require_osd_release
    check = "Check require_osd_release flag"
    major = to_major(report["version"])
    r_o_r = osdmap["require_osd_release"]
    running_release = to_release(major)
    if r_o_r != running_release:
        summary = "CRITICAL: require_osd_release is incorrect!"
        detail = [
            f"require_osd_release {r_o_r} does not match running release {running_release}"
        ]
        recommend = [
            f"Unless you are in the middle of a Ceph upgrade, it is strongly recommended to set the required osd release ASAP, e.g. ceph osd require-osd-release {running_release}"
        ]
        result.add_check_result(section, check, "FAIL", summary, detail, recommend)
        result.force_fail = True
    else:
        summary = "require_osd_release is correct"
        detail = [
            f"require_osd_release {r_o_r} matches running release {running_release}"
        ]
        result.add_check_result(section, check, "PASS", summary, detail, recommend)

    # TODO: check out for long, not clean, pg_upmap_items


@add_check
def check_report_osd_info(result, data) -> None:
    report = data.ceph_report
    section = "OSD Health"
    check = "Info"

    osds = report["osdmap"]["osds"]
    num_osds = len(osds)
    summary = f"Cluster has {num_osds} OSDs configured"
    detail = []
    # TODO: make this less verbose
    #    for o in osds:
    #        updown = {
    #            0: 'down',
    #            1: 'up'
    #        }
    #        inout = {
    #            0: 'out',
    #            1: 'in'
    #        }
    #        detail.append(f"osd.{o['osd']} which is {updown[o['up']]} and {inout[o['in']]} with weight {o['weight']}")
    result.add_info_result(section, check, summary, detail)


@add_check
def check_report_osd_primary_affinity(result, data) -> None:
    report = data.ceph_report
    section = "OSD Health"
    check = "Check OSD Primary Affinity"

    osds = report["osdmap"]["osds"]
    bad = []
    for o in osds:
        if o["primary_affinity"] != 1:
            bad.append(str(o["osd"]))
    if bad:
        passfail = "FAIL"
        summary = "Some OSDs have suboptimal primary-affinity"
        bad = ", ".join(bad)
        detail = [
            f"OSDs {bad} have primary-affinity != 1. This may be leftover from a device replacement procedure."
        ]
        recommend = ["Reset the osd primary-affinity to 1 for the listed OSDs."]
    else:
        passfail = "PASS"
        summary = "All OSDs have optimal primary-affinity"
        bad = ", ".join(bad)
        detail = [
            "All OSDs have the recommended primary-affinity (1). This ensures uniform IO handling across the cluster."
        ]
        recommend = []

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_osd_weight(result, data) -> None:
    report = data.ceph_report
    section = "OSD Health"
    check = "Check OSD Weights"

    osds = report["osdmap"]["osds"]
    bad = []
    for o in osds:
        if o["in"] == 1 and o["weight"] != 1:
            bad.append(str(o["osd"]))
    if bad:
        passfail = "FAIL"
        summary = "Some OSDs have suboptimal weights"
        bad = ", ".join(bad)
        detail = [
            f"OSDs {bad} have weight != 1.0. This may be leftover from a device replacement procedure or attempted data balancing."
        ]
        recommend = [
            "Reset the osd weights to 1 for the listed OSDs and enable the upmap balancer if required."
        ]
    else:
        passfail = "PASS"
        summary = "All OSDs have optimal weight"
        bad = ", ".join(bad)
        detail = [
            "All OSDs have the recommended weight (1). When used in tandem with the upmap balancer, this ensures an optimal data placement."
        ]
        recommend = []

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_pool_info(result, data) -> None:
    report = data.ceph_report
    section = "Pools"
    check = "Info"

    pools = report["osdmap"]["pools"]
    num_pools = len(pools)
    summary = f"Cluster has {num_pools} pools configured"
    detail = []
    for p in pools:
        ptype = "EC" if p["type"] == 3 else "replica"
        create_time = p.get("create_time", "unknown")
        detail.append(
            f"Pool {p['pool_name']} with {ptype} size {p['size']}, created {create_time}"
        )
    result.add_info_result(section, check, summary, detail)


@add_check
def check_report_capacity_info(result, data) -> None:
    report = data.ceph_report
    section = "Capacity"
    check = "Info"
    summary = "Cluster Capacity Info"
    detail = []

    pool_sum = report["pool_sum"]
    osd_sum = report["osd_sum"]
    report["pool_stats"]

    total_pool_size = humanize.naturalsize(
        pool_sum["stat_sum"]["num_bytes"], binary=True
    )
    total_pool_objects = humanize.intword(pool_sum["stat_sum"]["num_objects"])
    detail.append(f"Pools storing {total_pool_size} and {total_pool_objects} objects")

    total_osd_size = humanize.naturalsize(osd_sum["kb"] * 1024, binary=True)
    total_osd_used = humanize.naturalsize(osd_sum["kb_used"] * 1024, binary=True)
    total_osd_avail = humanize.naturalsize(osd_sum["kb_avail"] * 1024, binary=True)
    detail.append(
        f"OSD total capacity {total_osd_size}. Used: {total_osd_used}. Available: {total_osd_avail}."
    )

    result.add_info_result(section, check, summary, detail)


@add_check
def check_report_capacity_overfull(result, data) -> None:
    report = data.ceph_report
    section = "Capacity"
    check = "Check Cluster Capacity Fullness"
    summary = "Cluster Capacity Info"
    detail = []
    recommend = []

    report["pool_sum"]
    osd_sum = report["osd_sum"]
    report["pool_stats"]

    humanize.naturalsize(osd_sum["kb"] * 1024, binary=True)
    humanize.naturalsize(osd_sum["kb_used"] * 1024, binary=True)

    percent_used = osd_sum["kb_used"] / osd_sum["kb"]

    if percent_used > 0.9:
        passfail = "FAIL"
        detail.append(
            f"Cluster is {percent_used:.1%} full, over 90%, risking data loss in case of a node failure."
        )
        recommend.append("Add capacity or delete unneeded data to free space ASAP.")
    elif percent_used > 0.8:
        passfail = "WARN"
        detail.append(
            f"Cluster is {percent_used:.1%} full, over 80%. Add capacity soon."
        )
        recommend.append("Add capacity or delete unneeded data to free space.")
    else:
        passfail = "PASS"
        detail.append(
            f"Cluster is {percent_used:.1%} full, under 80%, safe for production."
        )

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_pool_flags(result, data) -> None:
    report = data.ceph_report
    section = "Pools"
    check = "Recommended Flags"

    # check pool flags
    flags = [
        "nodelete",
        "nosizechange",
    ]
    pools = report["osdmap"]["pools"]
    detail = []
    passfail = "PASS"
    for f in flags:
        pools_missing_flag = []
        for p in pools:
            if f not in p["flags_names"]:
                passfail = "FAIL"
                pools_missing_flag.append(p["pool_name"])
        if pools_missing_flag:
            detail.append(
                f"Pools missing recommended '{f}' flag: {', '.join(pools_missing_flag)}"
            )

    if passfail == "FAIL":
        summary = "Some pools have missing flags"
        recommend = [
            r"It is strongly recommended to set the nodelete and nosizechange flags to prevent unintended pool changes in production. E.g. ceph osd pool set \<poolname\> nodelete 1"
        ]
        result.add_check_result(section, check, passfail, summary, detail, recommend)
    else:
        summary = "Pools have the recommended flag settings."
        detail = [f"Pools have the recommended flags set: {flags}"]
        recommend = []
        result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_pool_size(result, data) -> None:
    report = data.ceph_report
    section = "Pools"
    check = "Pool Sizing"

    # check pool size/min_size
    pools = report["osdmap"]["pools"]
    detail = []
    recommend = []
    for p in pools:
        size = p["size"]
        min_size = p["min_size"]
        if p["type"] == 1:
            if size < 3:
                passfail = "WARN"
                detail.append(f"Replicated pool {p['pool_name']} has size {size}.")
                recommend.append(
                    f"Increase size on pool {p['pool_name']} to 3 to minimize the likelihood of data loss."
                )
            if min_size < 2:
                passfail = "FAIL"
                detail.append(
                    f"Replicated pool {p['pool_name']} has min_size {min_size}."
                )
                recommend.append(
                    f"Increase min_size on pool {p['pool_name']} to 2 to minimize the likelihood of data loss."
                )
        elif p["type"] == 3:
            profile_name = p["erasure_code_profile"]
            profile = report["osdmap"]["erasure_code_profiles"].get(profile_name)
            if not profile:
                # FIXME: do not silently ignore?
                continue
            expected_min_size = int(profile["k"]) + 1
            if min_size < expected_min_size:
                detail.append(
                    f"Erasure {profile['k']}+{profile['m']} pool {p['pool_name']} has min_size {min_size}."
                )
                recommend.append(
                    f"Increase min_size on pool {p['pool_name']} to {expected_min_size} to minimize likelihood of data loss."
                )

    if not detail:
        passfail = "PASS"
        summary = "All pools have correct min_size setting"
        detail.append("All pools have correct min_size setting")
    else:
        passfail = "FAIL"
        summary = "One or more pools have unsafe min_size"

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_pool_autoscale(result, data) -> None:
    report = data.ceph_report
    section = "Pools"
    check = "Pool Autoscale Mode"

    pools = report["osdmap"]["pools"]
    report["version"].split("-")[0]
    detail = []
    recommend = []
    summary = "All pools have pg_autoscaler disabled"
    passfail = "PASS"
    affected_pools = []
    for p in pools:
        try:
            mode = p["pg_autoscale_mode"]
        except KeyError:
            # Old version, no pg_autoscale_mode flag
            return
        if mode == "on":
            passfail = "WARN"
            summary = "pg_autoscaler is on which may cause unexpected data movement"
            affected_pools.append(p["pool_name"])

    if passfail == "PASS":
        detail.append(
            "All pools have pg_autoscaler disabled. This is the recommended setting for most environments."
        )
    elif passfail == "WARN":
        detail.append(
            f"The following pools have pg_autoscale_mode = on. This may cause unexpected background load during production hours, and is not recommended in most environments. Pools: {', '.join(affected_pools)}"
        )
        recommend.append(
            "Set pg_autoscale_mode to 'warn' or 'off' for all pools and set pg_num accordingly."
        )

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_rbd_pools(result, data) -> None:
    report = data.ceph_report
    section = "Pools"
    check = "RBD Pools"

    pools = report["osdmap"]["pools"]
    rbd_pools = [p["pool_name"] for p in pools if "rbd" in p["application_metadata"]]

    if len(rbd_pools) < 5:
        return

    passfail = "WARN"
    summary = "Too many RBD pools"
    detail = [
        f"{len(rbd_pools)} RBD pools found. "
        "This may indicate a problem with the cluster configuration."
    ]
    recommend = [
        "Multiple small pools is inefficient and has a negative performance "
        "impact for users. It is recommended to move in future to a single RBD "
        "pool and enable multi-tenancy using RADOS namespaces.",
    ]

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_pool_min_pgnum(result, data) -> None:
    report = data.ceph_report
    section = "Pools"
    check = "Minimum PG Count"

    pools = report["osdmap"]["pools"]
    pool_stats = {p["poolid"]: p for p in report["pool_stats"]}
    detail = []
    recommend = []
    summary = "All pools have pg_num higher or equal recommended minimum"
    passfail = "PASS"
    crush = Crush(report["crushmap"])
    for p in pools:
        application = (
            len(p["application_metadata"])
            and next(iter(p["application_metadata"].keys()))
        ) or None
        if application in ("mgr", "mgr_devicehealth"):
            # MGR special pools
            continue
        p["pg_num"]
        crush_rule = crush.get_rule_by_id(p["crush_rule"])
        if not crush_rule:
            # FIXME: do not silently ignore?
            continue
        root_id = crush.get_rule_root(crush_rule["rule_name"])
        if not crush_rule:
            # FIXME: do not silently ignore?
            continue
        stats = pool_stats.get(p["pool"])
        if not stats:
            continue
        pg_num_objects = stats["stat_sum"]["num_objects"]
        total_num_objects = report["pool_sum"]["stat_sum"]["num_objects"]
        if pg_num_objects < total_num_objects * 0.01:
            # We don't care much about small pools
            continue

        osd_num = len(set(crush.get_osds_under(root_id)))
        pg_shard_num = p["pg_num"] * p["size"]
        if pg_shard_num < osd_num:
            passfail = "FAIL"
            summary = "Pools have pg_num lower recommended minimum"
            pg_type = "shard" if p["type"] == 3 else "replica"
            detail.append(
                f"Pool {p['pool_name']} with current pg_num {p['pg_num']} has "
                f"fewer {pg_type}s ({pg_shard_num}) than OSDs ({osd_num}).",
            )
            recom_pg_num = ceil(osd_num / p["size"])
            recom_pg_num = 2 ** ceil(log2(recom_pg_num))  # nearest power of 2
            recommend.append(
                f"Set pg_num to {recom_pg_num} for pool {p['pool_name']} "
                f"to have at least one {pg_type} per OSD.",
            )

    if passfail == "PASS":
        detail.append("All pools have at least one replica or shard per OSD.")

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_pool_crush_domain_buckets(result, data) -> None:
    report = data.ceph_report
    section = "Pools"
    check = "Pool CRUSH Failure Domain Buckets"

    pools = report["osdmap"]["pools"]
    detail = []
    recommend = []
    passfail = "PASS"
    failed_count = 0
    crush = Crush(report["crushmap"])
    for p in pools:
        rool_id = p["crush_rule"]
        crush_rule = crush.get_rule_by_id(rool_id)
        if not crush_rule:
            # FIXME: do not silently ignore?
            continue
        item_type = crush.get_rule_failure_domain(rool_id)
        if not item_type:
            # FIXME: do not silently ignore?
            continue
        root_id = crush.get_rule_root(crush_rule["rule_name"])
        if not crush_rule:
            # FIXME: do not silently ignore?
            continue
        items_num = len(set(crush.get_items_of_type_under(item_type, root_id)))
        if items_num < p["size"] + 1:
            failed_count += 1
            if items_num < p["size"]:
                passfail = "FAIL"
            elif passfail != "FAIL":
                passfail = "WARN"
            detail.append(
                f"Pool {p['pool_name']} with size {p['size']} has "
                f"only {items_num} {item_type} items.",
            )
            recommend.append(
                f"You need to have at least {p['size'] + 1} {item_type} items "
                f"for pool {p['pool_name']} to avoid degraded state in case of "
                f"a {item_type} failure.",
            )

    if passfail == "PASS":
        summary = "Enough crush failure domain buckets for all pools"
        detail.append("All pools have CRUSH domain satisfied.")
    else:
        how_many = "all" if len(pools) == failed_count else "some"
        summary = f"Not enough CRUSH failure domain buckets for {how_many} pools"

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_pool_zero_weight_buckets(result, data) -> None:
    report = data.ceph_report
    section = "Pools"
    check = "Zero weight buckets in CRUSH Tree"

    pools = report["osdmap"]["pools"]
    detail = []
    recommend = []
    passfail = "PASS"
    failed_count = 0
    crush = Crush(report["crushmap"])
    for p in pools:
        rool_id = p["crush_rule"]
        crush_rule = crush.get_rule_by_id(rool_id)
        if not crush_rule:
            # FIXME: do not silently ignore?
            continue
        item_type = crush.get_rule_failure_domain(rool_id)
        if not item_type:
            # FIXME: do not silently ignore?
            continue
        root_id = crush.get_rule_root(crush_rule["rule_name"])
        if not crush_rule:
            # FIXME: do not silently ignore?
            continue
        buckets = crush.get_zero_weight_buckets_under(root_id)
        if buckets:
            passfail = "WARN"
            detail.append(
                f"CRUSH tree for pool {p['pool_name']} has zero weight buckets.",
            )

    if passfail == "PASS":
        summary = "No zero weight buckets in CRUSH tree"
        detail.append("All pools use CRUSH tree with no zero weight buckets.")
    else:
        how_many = "All" if len(pools) == failed_count else "Some"
        summary = f"{how_many} pools use CRUSH tree with zero weight buckets."
        recommend.append(
            "Remove unused (zero weight) buckets from CRUSH tree.",
        )

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_pool_crush_tree_balanced(result, data) -> None:
    report = data.ceph_report
    section = "Pools"
    check = "CRUSH Tree Balanced"

    pools = report["osdmap"]["pools"]
    detail = []
    recommend = []
    passfail = "PASS"
    failed_count = 0
    crush = Crush(report["crushmap"])
    for p in pools:
        rool_id = p["crush_rule"]
        crush_rule = crush.get_rule_by_id(rool_id)
        if not crush_rule:
            # FIXME: do not silently ignore?
            continue
        item_type = crush.get_rule_failure_domain(rool_id)
        if not item_type:
            # FIXME: do not silently ignore?
            continue
        root_id = crush.get_rule_root(crush_rule["rule_name"])
        if not crush_rule:
            # FIXME: do not silently ignore?
            continue
        items = set(crush.get_items_of_type_under(item_type, root_id))
        weights = [crush.get_item_weight(i) for i in items]
        # Filter out zero weights, we have a separate check for that
        weights = [w for w in weights if w > 0]
        average = fsum(weights) / len(weights)
        deviation = (max(weights) - min(weights)) / average
        if deviation > 0.2:
            failed_count += 1
            if deviation > 0.5:
                passfail = "FAIL"
            elif passfail != "FAIL":
                passfail = "WARN"
            detail.append(
                f"Pool {p['pool_name']} has CRUSH weights deviation {deviation:g}.",
            )

    if passfail == "PASS":
        summary = "Balanced CRUSH tree for all pools"
        detail.append("All pools have balanced CRUSH tree.")
    else:
        how_many = "all" if len(pools) == failed_count else "some"
        summary = f"Imbalanced CRUSH tree for {how_many} pools"
        recommend.append(
            "To have a balanced tree use OSDs of the same capacity, "
            "the same number of OSDs on hosts, and the same number of "
            "hosts in each rack.",
        )

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_pool_avg_object_size(result, data) -> None:
    report = data.ceph_report
    section = "Pools"
    check = "Pool Average Object Size"

    pools = report["osdmap"]["pools"]
    pool_stats = {p["poolid"]: p for p in report["pool_stats"]}
    detail = []
    recommend = []
    passfail = "PASS"
    for p in pools:
        application = (
            len(p["application_metadata"])
            and next(iter(p["application_metadata"].keys()))
        ) or None
        if application in ("mgr", "mgr_devicehealth"):
            # MGR special pools
            continue
        stats = pool_stats.get(p["pool"])
        if not stats:
            continue
        num_objects = stats["stat_sum"]["num_objects"]
        num_bytes = stats["stat_sum"]["num_bytes"]
        if num_objects < 100000:
            # We care only about pools with a large number of objects
            continue
        if "num_omap_bytes" not in stats["stat_sum"]:
            # very old ceph report, can't make any conclusions below
            return
        if stats["stat_sum"]["num_omap_bytes"] > num_bytes * 0.1:
            # Pool stores omap keys, small data objects are expected
            continue
        avg_obj_size = num_bytes / num_objects
        if p["type"] == 1:
            if avg_obj_size < 4096:
                passfail = "WARN"
                detail.append(
                    f"Average object size for replicated pool {p['pool_name']} "
                    f"is {avg_obj_size:g} bytes.",
                )
                recommend.append(
                    "Using Ceph for storing tiny objects is not optimal. "
                    "Consider changing storage strategy.",
                )
        elif p["type"] == 3 and avg_obj_size < p["stripe_width"]:
            p["erasure_code_profile"]
            passfail = "WARN"
            detail.append(
                f"Average object size for EC pool {p['pool_name']} "
                f"is {avg_obj_size} bytes, which is fewer than the "
                f"stripe width {p['stripe_width']} bytes.",
            )
            recommend.append(
                "Use a pool with an erasure code profile that has a "
                "stripe width smaller than than average object size.",
            )

    if passfail == "PASS":
        summary = "Average object size in all pools is large enough"
        detail.append(
            "For all pools the average object size is higher than allocation unit"
        )
    else:
        summary = "Average object size in some pools is too small"

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_pool_space_amplification(result, data) -> None:
    report = data.ceph_report
    section = "Pools"
    check = "Pool Space Amplification"

    pools = report["osdmap"]["pools"]
    pool_stats = {p["poolid"]: p for p in report["pool_stats"]}
    detail = []
    recommend = []
    passfail = "PASS"
    failed_count = 0
    for p in pools:
        application = (
            len(p["application_metadata"])
            and next(iter(p["application_metadata"].keys()))
        ) or None
        if application in ("mgr", "mgr_devicehealth"):
            # MGR special pools
            continue
        stats = pool_stats.get(p["pool"])
        if not stats:
            continue
        if "store_stats" not in stats:
            # Old version
            return
        num_objects = stats["stat_sum"]["num_objects"]
        num_bytes = stats["stat_sum"]["num_bytes"]
        if num_objects < 1000 or num_bytes < 10485760:
            # Not enough stored data to make judgement
            continue
        if p["type"] == 3:
            profile_name = p["erasure_code_profile"]
            profile = report["osdmap"]["erasure_code_profiles"].get(profile_name)
            if not profile:
                # FIXME: do not silently ignore?
                continue
            k = int(profile["k"])
            m = int(profile["m"])
        else:
            k = 1
            m = p["size"] - 1

        data_stored_ideal = num_bytes * (k + m) / k
        data_stored_real = stats["store_stats"]["allocated"]
        amplification = data_stored_real / data_stored_ideal
        if amplification > 1.2:
            if amplification > 1.5:
                passfail = "FAIL"
            elif passfail != "FAIL":
                passfail = "WARN"
            detail.append(
                f"Pool {p['pool_name']} has space amplification {amplification:.3}.",
            )
            failed_count += 1

    if passfail == "PASS":
        summary = "All pools have low space amplification"
        detail.append("For all pools space amplification is close to 1")
    else:
        how_many = "All" if len(pools) == failed_count else "Some"
        summary = f"{how_many} pools have high space amplification"
        recommend.append(
            "There may be an issue with how ceph stores data. "
            "Please contact support to investigate this further.",
        )

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_pool_cache_tiering(result, data) -> None:
    report = data.ceph_report
    section = "Pools"
    check = "Cache Tiering"

    pools = report["osdmap"]["pools"]
    pool_names = {p["pool"]: p["pool_name"] for p in pools}
    detail = []
    recommend = [
        "Cache tiering has been deprecated in the Reef release "
        "as it has lacked a maintainer for a very long time. "
        "It may be removed in newer releases without much further notice.",
    ]

    for p in pools:
        if p["tier_of"] > 0:
            tier_of = pool_names.get(p["tier_of"], p["tier_of"])
            detail.append(f"Pool {p['pool_name']} is cache tier of pool {tier_of}.")
        elif (
            p["read_tier"] > 0
            and p["write_tier"] > 0
            and p["read_tier"] == p["write_tier"]
        ):
            tier = pool_names.get(p["read_tier"], p["read_tier"])
            detail.append(f"Pool {p['pool_name']} has cache tier pool {tier}.")
        elif p["read_tier"] > 0:
            read_tier = pool_names.get(p["read_tier"], p["read_tier"])
            detail.append(
                f"Pool {p['pool_name']} has cache read tier pool {read_tier}."
            )
        elif p["write_tier"] > 0:
            write_tier = pool_names.get(p["write_tier"], p["write_tier"])
            detail.append(
                f"Pool {p['pool_name']} has cache write tier pool {write_tier}."
            )

    if not detail:
        passfail = "PASS"
        summary = "Cache tiering is not used"
        detail.append("No pools have cache tiering enabled.")
        recommend.append("Do not enable cache tiering.")
    else:
        passfail = "WARN"
        summary = "One or more pools have cache tiering enabled"
        recommend.append("Consider disabling cache tiering.")

    result.add_check_result(section, check, passfail, summary, detail, recommend)


# TODO: “osdmap”
# Advice about min_compat_client
# “pools”
# Size
# Application metadata (application on each pool)
# make sure the number of PGs makes sense for “rbd”, etc..
# Advice about mixed purpose ceph clusters (e.g. if we find cephfs, rbd, rgw all in same cluster)


@add_check
def check_report_pg_upmap(result, data) -> None:
    report = data.ceph_report
    section = "OSD Health"
    check = "Check osdmap pg_upmap list"
    detail = []
    recommend = []

    if report["osdmap"]["pg_upmap"]:
        passfail = "FAIL"
        summary = "osdmap has a non-empty pg_upmap entries"
        detail = [
            f"osdmap contains {len(report['osdmap']['pg_upmap'])} pg_upmap entries, which is not recommended"
        ]
        recommend = [
            "pg_upmap is not useful outside of very rare advanced scenarios. It is likely this was used by mistake and confused with pg-upmap-items entries."
        ]
    else:
        passfail = "PASS"
        summary = "osdmap pg_upmap list is empty"
        detail = [
            "pg_upmap is not useful in normal situations, and this cluster is correctly not using it."
        ]

    result.add_check_result(section, check, passfail, summary, detail, recommend)


# TODO: “pg_upmap_items”
# Check that all upmaps obey crush failure domains

# TODO: “osd_metadata”
# Many items to validate here, OS, rotational, device types for block.db/block, db size, drive models, kernel version, total memory on server, swap size, bluestore/filestore, …


@add_check
def check_report_journal_rotational(result, data) -> None:
    osd_metadata = data.ceph_report["osd_metadata"]
    section = "OSD Health"
    check = "Check BlueFS DB/Journal is on Flash"
    passfail = "PASS"
    detail = []
    recommend = []
    failed_count = 0

    rotational = []
    for osd in osd_metadata:
        if int(osd.get("journal_rotational", 0)):
            passfail = "FAIL"
            rotational.append(f"osd.{osd['id']}")
            failed_count += 1

    if passfail == "FAIL":
        how_many = "All" if len(osd_metadata) == failed_count else "Some"
        summary = f"{how_many} OSDs have bluefs db/wal or journal on rotational device"
        detail.append(
            f"The following OSDs have a rotational db/wal or journal: {', '.join(rotational)}"
        )
        recommend.append(
            "Migrate db/wal or journal for affected OSDs to non-rotational (flash) devices."
        )
    else:
        summary = "All OSDs have bluefs db/wal or journal on non-rotational device"
        detail.append(
            "Bluefs db/wal on non-rotational device is recommended for expected performance."
        )

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_bluefs_db_size(result, data) -> None:
    min_bluefs_db_size = 10737418240  # 10G
    osd_metadata = data.ceph_report["osd_metadata"]
    section = "OSD Health"
    check = "Check OSD bluefs db size"
    passfail = "PASS"
    detail = []
    recommend = []
    failed_count = 0

    for osd in osd_metadata:
        bluefs_db_size = int(osd.get("bluefs_db_size", min_bluefs_db_size + 1))
        if (
            int(osd.get("bluefs_dedicated_db", 0))
            and bluefs_db_size < min_bluefs_db_size
        ):
            passfail = "FAIL"
            detail.append(f"osd.{osd['id']} bluefs db size {bluefs_db_size}")
            recommend.append(
                f"Migrate osd.{osd['id']} bluefs db to partition of at least {min_bluefs_db_size} size"
            )
            failed_count += 1

    if passfail == "FAIL":
        how_many = "All" if len(osd_metadata) == failed_count else "Some"
        summary = f"{how_many} OSDs have too small bluefs db"
    else:
        summary = "All OSDs have large enough bluefs db"
        detail.append(
            f"Bluefs db of at least {min_bluefs_db_size} size is recommended for expected performance."
        )

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_bluefs_wal_size(result, data) -> None:
    min_bluefs_wal_size = 1073741824  # 1G
    osd_metadata = data.ceph_report["osd_metadata"]
    section = "OSD Health"
    check = "Check OSD bluefs wal size"
    passfail = "PASS"
    detail = []
    recommend = []
    failed_count = 0

    for osd in osd_metadata:
        bluefs_wal_size = int(osd.get("bluefs_wal_size", min_bluefs_wal_size + 1))
        if (
            int(osd.get("bluefs_dedicated_wal", 0))
            and bluefs_wal_size < min_bluefs_wal_size
        ):
            passfail = "FAIL"
            detail.append(f"osd.{osd['id']} bluefs wal size {bluefs_wal_size}")
            recommend.append(
                f"Migrate osd.{osd['id']} bluefs wal to partition of at least {min_bluefs_wal_size} size"
            )
            failed_count += 1

    if passfail == "FAIL":
        how_many = "All" if len(osd_metadata) == failed_count else "Some"
        summary = f"{how_many} OSDs have too small bluefs wal"
    else:
        summary = "All OSDs have large enough bluefs wal"
        detail.append(
            f"Bluefs wal of at least {min_bluefs_wal_size} size is recommended for expected performance."
        )

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_bluestore_min_alloc_size(result, data) -> None:
    osd_metadata = data.ceph_report["osd_metadata"]
    section = "OSD Health"
    check = "OSD bluestore min_alloc_size"
    passfail = "PASS"
    detail = []
    recommend = []
    failed_osds = {}

    for osd in osd_metadata:
        try:
            min_alloc_size = int(osd["bluestore_min_alloc_size"])
        except KeyError:
            # Old version
            return
        if min_alloc_size != 4096:
            passfail = "FAIL"
            if min_alloc_size not in failed_osds:
                failed_osds[min_alloc_size] = set()
            failed_osds[min_alloc_size].add(osd["id"])

    if failed_osds:
        passfail == "FAIL"
        how_many = "All" if len(failed_osds) == len(osd_metadata) else "Some"
        summary = f"{how_many} OSDs have non-optimal bluestore min_alloc_size"
        for min_alloc_size, osds in failed_osds.items():
            detail.append(
                f"osds {osds} has bluestore min_alloc_size {min_alloc_size}",
            )
        recommend.append(
            "Redeploy the reported OSDs with bluestore min_alloc_size 4096",
        )
    else:
        summary = "All OSDs have optimal bluestore min_alloc_size"
        detail.append(
            "Bluestore min_alloc_size 4096 is recommended for expected performance.",
        )

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_host_memory(result, data) -> None:
    MEM_PER_OSD_CRITICAL = 2 * 1024 * 1024 * 1024  # 2G
    MEM_PER_OSD_WARNING = 4 * 1024 * 1024 * 1024  # 4G

    osd_metadata = data.ceph_report["osd_metadata"]
    section = "OSD Health"
    check = "OSD host memory"
    passfail = "PASS"
    detail = []
    recommend = []
    hosts = {}

    for osd in osd_metadata:
        try:
            host = osd["hostname"]
        except KeyError:
            # Old version
            return
        if host not in hosts:
            try:
                mem_total = int(osd["mem_total_kb"]) * 1024
            except KeyError:
                # Old version
                return
            hosts[host] = {
                "mem_total": mem_total,
                "osds": [],
            }
        hosts[host]["osds"].append(osd)

    failed_hosts_count = 0
    for name, host in hosts.items():
        mem_per_osd = host["mem_total"] / len(host["osds"])
        if mem_per_osd < MEM_PER_OSD_WARNING:
            if mem_per_osd < MEM_PER_OSD_CRITICAL:
                passfail = "FAIL"
            elif passfail != "FAIL":
                passfail = "WARN"
            detail.append(
                f"Host {name} has {humanize.naturalsize(host['mem_total'], binary=True)} "
                f"total memory for {len(host['osds'])} OSDs",
            )
            recommend.append(
                f"Increase memory on host {name} to at least "
                f"{humanize.naturalsize(MEM_PER_OSD_WARNING * len(host['osds']), binary=True)}",
            )
            failed_hosts_count += 1

    if passfail == "PASS":
        summary = "All OSD hosts have enough memory"
        detail.append(
            f"Minimum {humanize.naturalsize(MEM_PER_OSD_WARNING * len(host['osds']), binary=True)} "
            f"memory per OSD is recommended for expected performance.",
        )
    else:
        how_many = "All" if len(hosts) == failed_hosts_count else "Some"
        summary = f"{how_many} OSD hosts have insufficient memory"

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_host_swap(result, data) -> None:
    osd_metadata = data.ceph_report["osd_metadata"]
    section = "OSD Health"
    check = "OSD host swap"
    passfail = "PASS"
    detail = []
    recommend = []
    hosts = set()
    hosts_with_swap = set()

    for osd in osd_metadata:
        try:
            name = osd["hostname"]
        except KeyError:
            # Old version
            return
        if name in hosts:
            continue
        hosts.add(name)

        try:
            swap = int(osd["mem_swap_kb"]) > 0
        except KeyError:
            # Old version
            return

        if swap:
            passfail = "WARN"
            hosts_with_swap.add(name)

    if passfail == "PASS":
        summary = "All OSD hosts have swap disabled"
        detail.append(
            "Disabling swap is recommended for expected performance.",
        )
    else:
        detail.append(
            f"swap is enabled on OSD hosts: {', '.join(sorted(hosts_with_swap))}",
        )
        recommend.append(
            "Disable swap on hosts and increase memory if needed",
        )
        how_many = "All" if len(hosts) == len(hosts_with_swap) else "Some"
        summary = f"{how_many} OSD hosts have swap enabled"

    result.add_check_result(section, check, passfail, summary, detail, recommend)


# “osdmap_clean_epochs”
# This section is often empty due to a bug
# If filled, can check for pools having not recent clean epoch


@add_check
def check_report_num_osdmaps(result, data) -> None:
    report = data.ceph_report
    section = "OSD Health"
    check = "Check number of osdmaps stored"
    detail = []
    recommend = []

    num_committed = report["osdmap_last_committed"] - report["osdmap_first_committed"]
    if num_committed > 1500:
        passfail = "FAIL"
        summary = f"Cluster has too many osdmaps ({num_committed})"
        detail = [
            f"Ceph is storing {num_committed} osdmaps, which may indicate that they are not being trimmed correctly. This may be transient during extended periods of backfilling."
        ]
        recommend = [
            "If this does not resolve itself when backfilling completes, it can indicate a deeper problem in trimming osdmaps. Consult Clyso support in that case."
        ]
    else:
        passfail = "PASS"
        summary = "Cluster osdmaps are trimming correctly"
        detail = [
            f"Ceph is storing {num_committed} osdmaps, which is within the normal range."
        ]

    result.add_check_result(section, check, passfail, summary, detail, recommend)


# “crushmap”
# We can decode the entire crushmap here
# failure domain correct?
# straw2 vs straw1
# Tunables
# if non optimal, advice how to make optimal, e.g. old clusters need chooseleaf_vary_r around 4 or 5
# chooseleaf_stable – advice if not 1
# choose_total_tries set to 100


@add_check
def check_report_crush_tunables_optimal(result, data) -> None:
    report = data.ceph_report
    section = "OSD Health"
    check = "Check CRUSH Tunables"
    detail = []
    recommend = []

    optimal = {
        "choose_local_tries": 0,
        "choose_local_fallback_tries": 0,
        "choose_total_tries": lambda x: 100 if x < 100 else None,
        "chooseleaf_descend_once": 1,
        "chooseleaf_vary_r": 1,
        "chooseleaf_stable": 1,
        "allowed_bucket_algs": 54,
        "straw_calc_version": 1,
    }

    tunables = report["crushmap"]["tunables"]
    passfail = "PASS"

    if tunables["optimal_tunables"] and not tunables["legacy_tunables"]:
        summary = "CRUSH Tunables are optimal"
        detail = ["CRUSH tunables are optimal, ensuring the ideal data placement."]
        result.add_check_result(section, check, passfail, summary, detail, recommend)
        return

    for tunable in optimal:
        recommended = None
        if callable(optimal[tunable]):
            recommended = optimal[tunable](tunables[tunable])
        elif tunables[tunable] != optimal[tunable]:
            recommended = optimal[tunable]
        if recommended is not None:
            passfail = "WARN"
            summary = "At least one CRUSH tunable is not optimal"
            detail.append(
                f"CRUSH tunable {tunable} is currently {tunables[tunable]}, not the recommended {recommended}."
            )
            recommend.append(
                f"Set the tunable {tunable} to {recommended}. Note that this may result in significant data movement. Contact support if you are unsure."
            )

    if passfail == "PASS":
        summary = "CRUSH Tunables are following the recommended settings"
        detail = ["CRUSH tunables are following the recommended settings"]

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_fsmap_info(result, data) -> None:
    report = data.ceph_report
    section = "CephFS"
    check = "CephFS Info"
    detail = []

    fsmap = report["fsmap"]
    filesystems = fsmap["filesystems"]
    summary = f"Found {len(filesystems)} CephFS filesystems"
    for fs in filesystems:
        mdsmap = fs["mdsmap"]
        detail.append(
            f"{mdsmap['fs_name']}: data pools {mdsmap['data_pools']}, meta pool {mdsmap['metadata_pool']}, max_mds {mdsmap['max_mds']}"
        )
    result.add_info_result(section, check, summary, detail)


@add_check
def check_report_fsmap_multi_mds(result, data) -> None:
    report = data.ceph_report
    section = "CephFS"
    check = "Multi-MDS Safety"
    detail = []
    recommend = []
    fsmap = report["fsmap"]
    filesystems = fsmap["filesystems"]
    has_cephfs = bool(len(filesystems))
    multimds = False
    passfail = "PASS"
    for fs in filesystems:
        mdsmap = fs["mdsmap"]
        if mdsmap["max_mds"] > 1:
            multimds = True
            passfail = "WARN"
            detail.append(
                f"Filesystem {mdsmap['fs_name']} has multiple active MDSs (max_mds is {mdsmap['max_mds']}). Multi-MDS should be used with caution and following careful guidance."
            )
        if mdsmap["max_mds"] > 8:
            passfail = "FAIL"

    if multimds:
        summary = "Found CephFS filesystems with multiple active MDS daemons"
        recommend.append(
            "Multiple active MDS daemons should only be enabled if technically justified and following careful guidance."
        )
    elif has_cephfs:
        summary = "All CephFS filesystems use a single active MDS"
    else:
        summary = "No CephFS fileesystems detected."

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_osd_cluster_network(result, data) -> None:
    report = data.ceph_report
    section = "OSD Health"
    check = "Dedicated Cluster Network"

    first = report["osdmap"]["osds"][0]
    public_ip = first["public_addr"].split(":")[0]
    cluster_ip = first["cluster_addr"].split(":")[0]
    if public_ip == cluster_ip:
        passfail = "WARN"
        summary = "Public and Cluster Networks are Shared"
        detail = [
            "OSDs are using the same IP address for the public and cluster networks. This may have performance implications for busy clusters notably during periods of recovery or backfilling."
        ]
        recommend = [
            "Consider adding a dedicated cluster network for internal OSD traffic."
        ]
    else:
        passfail = "PASS"
        summary = "Public and Cluster Networks are Separated"
        detail = [
            "OSDs are using distinct IP addresses for the public and clusters networks. This is ideal for optimal performance."
        ]
        recommend = []

    result.add_check_result(section, check, passfail, summary, detail, recommend)


@add_check
def check_report_operating_system(result, data) -> None:
    report = data.ceph_report
    section = "Operating System"
    check = "OS Support"

    distros = []
    distro_descriptions = []
    distro_versions = []
    osds = report["osd_metadata"]

    # Check if using cephadm (container) deployment
    is_container_deployment = False
    for osd in osds:
        if "container_image" in osd:
            is_container_deployment = True
            break

    if is_container_deployment:
        summary = "Container Deployment Detected"
        detail = [
            "Ceph is deployed using containers (cephadm). OS check skipped since container deployments use standardized images."
        ]
        passfail = "PASS"
        recommend = []
        result.add_check_result(section, check, passfail, summary, detail, recommend)
        return

    for osd in osds:
        if "distro" not in osd:
            continue
        if osd["distro"] not in distros:
            distros.append(osd["distro"])
        if osd["distro_description"] not in distro_descriptions:
            distro_descriptions.append(osd["distro_description"])
        if osd["distro_version"] not in distro_versions:
            distro_versions.append(osd["distro_version"])

    detail = []
    recommend = []
    summary = "Operating System is Supported"
    passfail = "PASS"
    for d in distro_descriptions:
        if d not in osdb["operating_systems"]:
            passfail = "WARN"
            summary = "Operating System is Unknown"
            detail.append(
                f"{d} is unknown - this may or may not be a stable platform for Ceph."
            )
            recommend.append(
                f"Upgrade {d} to a recommended recent OS, including RHEL 9+ or clones, Ubuntu 22.04+, or Debian 12+. See https://docs.ceph.com/en/latest/start/os-recommendations/ for further information."
            )
            continue

        os = osdb["operating_systems"][d]
        if os["status"] != "Supported":
            passfail = "WARN"
            summary = f"Operating System is {os['status']}"
            detail.append(os["detail"])
            recommend.append(
                f"{os['recommend']} See https://docs.ceph.com/en/latest/start/os-recommendations/ for further information."
            )
        else:
            detail.append(f"{d} is Supported.")

    result.add_check_result(section, check, passfail, summary, detail, recommend)


# TODO
# num_pg, num_active, num_osd:
# Advice about number of pgs per osd
# pool_sum, osd_sum, osd_sum_by_class:
#  Display some summary info, no obvious warnings from here
# pool_stats:
# Warn about large log_size
# num_pg_by_state
# Warning any non-active PGs


def update_result(res, data) -> None:
    for c in check_functions:
        try:
            c(res, data)
        except Exception:
            print(f"An exception occurred in check function {c}!\n", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)

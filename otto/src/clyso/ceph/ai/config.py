# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

# Otto - Configuration analysis module
# Copyright (C) 2025 Clyso. All rights reserved.

# NOTE: basedpyright has issues with stub files in this environment
# Disable issues related to missing builtins and stubs, but keep meaningful type checking
#
# pyright: reportMissingImports=false
# pyright: reportMissingTypeStubs=false
# pyright: reportAny=false
# pyright: reportExplicitAny=false

from __future__ import annotations

import sys
import traceback
from typing import Any, Callable
import builtins

from clyso.ceph.ai.facts import CephFacts, ConfigLookup


# A list of all config check functions
config_check_functions: list[Callable[..., None]] = []


# Decorator to add config checks to the registry
def add_config_check(func: Callable[..., None]) -> Callable[..., None]:
    config_check_functions.append(func)
    return func


@add_config_check
def check_config_osd_op_queue(
    result: Any, _data: Any, _facts: Any, config_lookup: Any
) -> None:
    """Check OSD operation queue configuration"""
    section: str = "Configuration"
    check: str = "OSD Operation Queue"

    # Check osd_op_queue setting in osd section
    osd_op_queue: Any = config_lookup.get_config_value("osd_op_queue", "osd")

    detail: list[str] = []
    recommend: list[str] = []

    # TODO: need to add CES version check here since it won't be in the config dump
    if not osd_op_queue:
        summary: str = "OSD operation queue not explicitly configured to use wpq"
        detail.append(
            "osd_op_queue is not set in osd section - using Ceph defaults (mclock in Quincy and later)."
        )
        detail.append(
            "While mclock is the new default in recent Ceph versions, it has not demonstrated sufficient performance stability for production workloads."
        )
        recommend.append(
            "Configure osd_op_queue to use 'wpq' (Weighted Priority Queue) for better reliability and performance stability. ceph config set osd osd_op_queue wpq
"
        )
        result.add_check_result(section, check, "WARN", summary, detail, recommend)
    elif osd_op_queue == "wpq":
        summary = "OSD operation queue optimally configured to use wpq"
        detail.append(
            "osd_op_queue is set to 'wpq' (Weighted Priority Queue) which provides better performance stability compared to mclock."
        )
        result.add_check_result(section, check, "PASS", summary, detail, [])
    else:
        summary = "OSD operation queue using non-optimal setting"
        detail.append(
            f"osd_op_queue is set to '{osd_op_queue}' instead of the recommended 'wpq'."
        )
        detail.append(
            "While mclock is the new default in recent Ceph versions, it has not demonstrated sufficient performance stability for production workloads."
        )
        recommend.append(
            "Set osd_op_queue to 'wpq' for better performance stability and reliability."
        )
        result.add_check_result(section, check, "WARN", summary, detail, recommend)


def update_result(airesult: Any, ceph_data: Any) -> None:
    """
    Main entry point for configuration analysis.
    Called from the main analysis pipeline.
    """
    if (
        not builtins.hasattr(ceph_data, "ceph_config_dump")
        or not ceph_data.ceph_config_dump
    ):
        return

    # Create facts and config lookup objects
    # Need the CephFacts object to get information like version number for
    # specific config recommendations
    try:
        facts: CephFacts = CephFacts(ceph_data)
        config_lookup: ConfigLookup = ConfigLookup(ceph_data.ceph_config_dump)
    except Exception as e:
        builtins.print(f"Failed to initialize config analysis: {e}", file=sys.stderr)
        return

    for check_func in config_check_functions:
        try:
            check_func(airesult, ceph_data, facts, config_lookup)
        except Exception:
            builtins.print(
                f"An exception occurred in config check function {check_func.__name__}!",
                file=sys.stderr,
            )
            builtins.print(traceback.format_exc(), file=sys.stderr)

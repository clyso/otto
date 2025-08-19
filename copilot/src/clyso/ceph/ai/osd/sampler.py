# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import math
import random
from typing import Optional, List, Dict


def calculate_sample_size(total_osds: int, user_specified: Optional[int] = None) -> int:
    """Calculate sample size based on cluster size and user input"""
    if user_specified is not None:
        return min(user_specified, total_osds)

    if total_osds < 50:
        return min(5, total_osds)
    else:
        return int(round(math.sqrt(total_osds)))


def stratified_sample_osds(
    device_class_to_osds: Dict[str, List[int]], up_osds: List[int], sample_size: int
) -> List[int]:
    """Sample random OSDs by looping through device classes"""

    if sample_size >= len(up_osds):
        return up_osds.copy()

    osd_pools_by_class = {}
    for dc, osds in device_class_to_osds.items():
        up_osds_in_class = [osd for osd in osds if osd in up_osds]
        if up_osds_in_class:
            osd_pools_by_class[dc] = up_osds_in_class

    if not osd_pools_by_class:
        return []

    sampled_osds = []
    device_classes = list(osd_pools_by_class.keys())
    class_index = 0

    while len(sampled_osds) < sample_size and osd_pools_by_class:
        device_class = device_classes[class_index % len(device_classes)]
        osd_pool = osd_pools_by_class[device_class]

        selected_osd = osd_pool.pop(random.randrange(len(osd_pool)))
        sampled_osds.append(selected_osd)

        if not osd_pool:
            del osd_pools_by_class[device_class]
            device_classes.remove(device_class)
        else:
            class_index += 1

    return sampled_osds

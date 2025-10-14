# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Internal JSON parsing utilities for handling Ceph's non-standard JSON output."""

import json
import math
from typing import Any


def parse_ceph_json(json_data: str) -> Any:
    """
    Parse JSON data from Ceph with special handling for non-standard values.

    Ceph sometimes outputs non-standard JSON constants like 'inf', '-inf', and 'nan'
    which are not valid JSON. This function handles those cases by converting them
    to valid JSON 'Infinity', '-Infinity', and 'NaN' before parsing.

    Args:
        json_data: Raw JSON string from Ceph command output

    Returns:
        Parsed Python object (dict, list, etc.)
    """

    def parse_json_constants(arg):
        if arg == "Infinity":
            return math.inf
        elif arg == "-Infinity":
            return -math.inf
        elif arg == "NaN":
            return math.nan
        return None

    # Replace non-standard JSON constants with valid ones
    json_data = json_data.replace(" inf,", " Infinity,")
    json_data = json_data.replace(" -inf,", " -Infinity,")
    json_data = json_data.replace(" nan,", " NaN,")

    return json.loads(json_data, parse_constant=parse_json_constants)

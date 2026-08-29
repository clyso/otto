# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import json

# Check result -> numeric gauge value, ordered by severity
# (PASS < WARN < UNKNOWN < FAIL) so higher values mean "worse" and dashboards
# can alert on a threshold.
STATUS_VALUE = {"PASS": 0, "WARN": 1, "UNKNOWN": 2, "FAIL": 3}


def _escape_label(value: str) -> str:
    """Escape a Prometheus label value (backslash, double-quote, newline)."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_prometheus(result: str) -> str:
    """Render a checkup result JSON string as Prometheus text exposition."""
    data = json.loads(result)
    summary = data["summary"]
    sections = data["sections"]

    lines: list[str] = []

    lines.append("# HELP otto_checkup_score Overall checkup score")
    lines.append("# TYPE otto_checkup_score gauge")
    lines.append(f"otto_checkup_score {summary['score']}")

    lines.append("# HELP otto_checkup_max_score Maximum possible checkup score")
    lines.append("# TYPE otto_checkup_max_score gauge")
    lines.append(f"otto_checkup_max_score {summary['max_score']}")

    lines.append("# HELP otto_checkup_section_score Per-section checkup score")
    lines.append("# TYPE otto_checkup_section_score gauge")
    for section in sections:
        label = _escape_label(section["id"])
        lines.append(
            f'otto_checkup_section_score{{section="{label}"}} {section["score"]}'
        )

    lines.append(
        "# HELP otto_checkup_check_status "
        "Check status (0=PASS, 1=WARN, 2=UNKNOWN, 3=FAIL)"
    )
    lines.append("# TYPE otto_checkup_check_status gauge")
    for section in sections:
        section_label = _escape_label(section["id"])
        for check in section["checks"]:
            check_label = _escape_label(check["id"])
            value = STATUS_VALUE[check["result"]]
            lines.append(
                f'otto_checkup_check_status{{section="{section_label}",'
                f'check="{check_label}"}} {value}'
            )

    return "\n".join(lines) + "\n"

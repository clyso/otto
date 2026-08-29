# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import re
import subprocess
import unittest

from clyso.ceph.otto.prometheus import STATUS_VALUE, render_prometheus

# Every non-comment line must be `name`, optional `{labels}`, a space, a number.
_LINE_RE = re.compile(r"^[a-z_]+(\{[^}]*\})? -?[0-9.]+$")


class RenderPrometheusTest(unittest.TestCase):
    def setUp(self):
        with open("tests/otto.json") as f:
            self.result = json.load(f)
        self.out = render_prometheus(json.dumps(self.result))

    def test_metric_families_and_completeness(self):
        for type_line in (
            "# TYPE otto_checkup_score gauge",
            "# TYPE otto_checkup_max_score gauge",
            "# TYPE otto_checkup_section_score gauge",
            "# TYPE otto_checkup_check_status gauge",
        ):
            self.assertIn(type_line, self.out)

        # One check_status line per check in the input.
        n_checks = sum(len(s["checks"]) for s in self.result["sections"])
        n_status_lines = sum(
            1
            for line in self.out.splitlines()
            if line.startswith("otto_checkup_check_status{")
        )
        self.assertEqual(n_status_lines, n_checks)

        # Spot-check two status values: Cluster/Health is WARN (1);
        # Version/Check for Known Issues is FAIL (3).
        self.assertIn(
            'otto_checkup_check_status{section="Cluster",check="Health"} '
            f"{STATUS_VALUE['WARN']}",
            self.out,
        )
        self.assertIn(
            'otto_checkup_check_status{section="Version",'
            'check="Check for Known Issues in Running Version"} '
            f"{STATUS_VALUE['FAIL']}",
            self.out,
        )

    def test_label_escaping(self):
        result = {
            "summary": {"score": 0.0, "max_score": 1, "grade": "F"},
            "sections": [
                {
                    "id": 'Quo"te\\back',
                    "score": 0.0,
                    "max_score": 1,
                    "grade": "F",
                    "checks": [{"id": 'a"b\\c', "result": "FAIL"}],
                }
            ],
        }
        out = render_prometheus(json.dumps(result))
        self.assertIn(r'section="Quo\"te\\back"', out)
        self.assertIn(r'check="a\"b\\c"', out)

    def test_exposition_format_shape(self):
        self.assertTrue(self.out.endswith("\n"))
        for line in self.out.splitlines():
            if line.startswith("#") or not line:
                continue
            self.assertRegex(line, _LINE_RE)


class CliPrometheusTest(unittest.TestCase):
    def test_cli_format_prometheus(self):
        process = subprocess.Popen(
            [  # noqa: S607
                "otto",
                "checkup",
                "--ceph_report_json=tests/report.pacific.json",
                "--format=prometheus",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout_output, _ = process.communicate()
        self.assertEqual(process.returncode, 0)
        first_line = stdout_output.decode().splitlines()[0]
        self.assertEqual(first_line, "# HELP otto_checkup_score Overall checkup score")


if __name__ == "__main__":
    unittest.main()

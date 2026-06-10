# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import subprocess
import unittest
from pathlib import Path

FIXTURE = str(Path(__file__).parent / "report.pacific.json")


def _run(*extra_args):
    return subprocess.run(  # noqa: S603
        ["otto", "checkup", "-i", FIXTURE, *extra_args],  # noqa: S607
        capture_output=True,
        text=True,
    )


class CheckupOutputTest(unittest.TestCase):
    def test_format_json_shape(self):
        proc = _run("--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertEqual(set(doc.keys()), {"summary", "sections"})
        self.assertLessEqual(
            {"score", "grade", "max_score"}, set(doc["summary"].keys())
        )

    def test_text_flags_do_not_leak_into_json(self):
        plain = _run("--format", "json")
        with_verbose = _run("--format", "json", "--verbose")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertEqual(with_verbose.returncode, 0, with_verbose.stderr)
        self.assertEqual(plain.stdout, with_verbose.stdout)

    def test_default_behavior_unchanged(self):
        proc = _run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(
            proc.stdout.startswith("Running tests:"),
            f"Unexpected default output: {proc.stdout!r}",
        )


if __name__ == "__main__":
    unittest.main()

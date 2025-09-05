import os
import subprocess
import textwrap
import unittest


class SmokeTestCopilotCLI(unittest.TestCase):
    def test_cli(self):
        for report in os.listdir("tests/reports/"):
            process = subprocess.Popen(  # noqa: S603
                [  # noqa: S607
                    "ceph-copilot",
                    "checkup",
                    f"--ceph_report_json=tests/reports/{report}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            _, stderr_output = process.communicate()

            assert not stderr_output, (
                f"Copilot produced stderr output for infile {report}:\n"
                + f"{stderr_output.decode()}"
            )
            print(f"tests/reports/{report} OK")

    def test_histogram(self):
        expected_output = textwrap.dedent("""\
        # NumSamples = 12; Min = 85.00; Max = 87.00
        # Mean = 85.583333; Variance = 0.576389; SD = 0.759203; Median 85.000000
        # each # represents a count of 1
            85.0000 -    85.2000 [     7]: #######
            85.2000 -    85.4000 [     0]:
            85.4000 -    85.6000 [     0]:
            85.6000 -    85.8000 [     0]:
            85.8000 -    86.0000 [     3]: ###
            86.0000 -    86.2000 [     0]:
            86.2000 -    86.4000 [     0]:
            86.4000 -    86.6000 [     0]:
            86.6000 -    86.8000 [     0]:
            86.8000 -    87.0000 [     2]: ##
            """)

        for pg_dump, osd_tree in zip(
            os.listdir("tests/histogram/pgdumps/"),
            os.listdir("tests/histogram/osdtrees/"),
            strict=False,
        ):
            process = subprocess.Popen(  # noqa: S603
                [  # noqa: S607
                    "ceph-copilot",
                    "pools",
                    "pg",
                    "distribution",
                    f"--pg_dump_json=tests/histogram/pgdumps/{pg_dump}",
                    f"--osd_tree_json=tests/histogram/osdtrees/{osd_tree}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr_output = process.communicate()

            assert not stderr_output, (
                f"Copilot produced stderr output for infile {pg_dump} and {osd_tree}:\n"
                + f"{stderr_output.decode()}"
            )
            print(f"tests/pg_dump/{pg_dump} and tests/osd_tree/{osd_tree} OK")

            stdout_first_line = stdout.decode().splitlines()[0]
            expected_output_first_line = expected_output.splitlines()[0]

            assert stdout_first_line == expected_output_first_line, (
                f"Unexpected output for infile {pg_dump} and {osd_tree}:\n"
                + f"{stdout.decode()}"
            )

    def test_arguments(self):
        # We are testing that appropriate help messages are printed when no
        # arguments are passed
        valid_commands = ["cluster", "pools", "toolkit", ""]

        for cmd in valid_commands:
            args = ["ceph-copilot"]
            if cmd is not None:
                args.append(cmd)
            process = subprocess.Popen(  # noqa: S603
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr_output = process.communicate()

            # Make sure that usage line is printed
            self.assertIn(
                f"usage: ceph-copilot {cmd if cmd else ''}",
                stdout.decode(),
                f"Unexpected usage line for {cmd}:\n{stdout}",
            )


if __name__ == "__main__":
    unittest.main()

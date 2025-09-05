import json
import os
import unittest

import clyso.ceph.ai as ai_module


class TestClassResult(unittest.TestCase):
    def test_result_foo(self) -> None:
        from clyso.ceph.ai.result import AIResult

        r = AIResult()
        r.add_section("Foo")
        res = r.dump()
        expected = (
            '{"summary": {"score": 0, "grade": "-", "max_score": 0}, '
            + '"sections": [{"id": "Foo", "score": 0, "max_score": 0, "summary": "", '
            + '"info": [], "checks": [], "grade": "-"}]}'.replace("\n", "")
        )
        self.assertTrue(res == expected, f"\n{res}\nnot equal to expected\n{expected}")

    def test_result_section_twice(self) -> None:
        from clyso.ceph.ai.result import AIResult

        r = AIResult()
        r.add_section("Foo")
        self.assertRaises(
            AssertionError,
            r.add_section,
            "Foo",
        )  # Cannot add a section twice

    def test_check_result(self) -> None:
        from clyso.ceph.ai.result import AIResult

        r = AIResult()
        r.add_section("Health")
        r.add_check_result(
            "Health",
            "CEPH_HEALTH",
            "PASS",
            "HEALTH_OK",
            "HEALTH_OK",
            [],
        )
        res = r.dump()
        expected = (
            '{"summary": {"score": 1.0, "grade": "A+", "max_score": 1}, '
            + '"sections": [{"id": "Health", "score": 1.0, "max_score": 1, '
            + '"summary": "", "info": [], "checks": [{"id": "CEPH_HEALTH", '
            + '"result": "PASS", "summary": "HEALTH_OK", "detail": "HEALTH_OK", '
            + '"recommend": []}], "grade": "A+"}]}'.replace("\n", "")
        )
        self.assertTrue(res == expected, f"\n{res}\nnot equal to expected\n{expected}")


class TestClysoCephAI(unittest.TestCase):
    def setUp(self) -> None:
        test_path = os.path.dirname(os.path.abspath(__file__))
        _report = os.path.join(test_path, "report.pacific.json")
        with open(_report) as file:
            self.report_json = json.load(file)

    def test_check_report(self) -> None:
        result = ai_module.generate_result(report_json=self.report_json)
        out = json.loads(result.dump())

        # Write the new JSON output to a temp file
        with open("tests/temp_copilot.json", "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)

        with open("tests/copilot.json") as f:
            expected = json.load(f)

        failures = []

        def assert_equal(actual, expected, message) -> None:
            try:
                assert actual == expected, message
            except AssertionError as e:
                failures.append(str(e))

        assert_equal(out["summary"], expected["summary"], "Summary mismatch")
        assert_equal(
            len(out["sections"]),
            len(expected["sections"]),
            "Number of sections mismatch",
        )

        for out_section, expected_section in zip(
            out["sections"],
            expected["sections"],
            strict=False,
        ):
            assert_equal(
                out_section["id"],
                expected_section["id"],
                f"Section ID mismatch for {out_section['id']}",
            )
            assert_equal(
                out_section["score"],
                expected_section["score"],
                f"Score mismatch for section {out_section['id']}",
            )
            assert_equal(
                out_section["max_score"],
                expected_section["max_score"],
                f"Max score mismatch for section {out_section['id']}",
            )
            assert_equal(
                out_section["summary"],
                expected_section["summary"],
                f"Summary mismatch for section {out_section['id']}",
            )
            assert_equal(
                out_section["grade"],
                expected_section["grade"],
                f"Grade mismatch for section {out_section['id']}",
            )

            assert_equal(
                len(out_section["info"]),
                len(expected_section["info"]),
                f"Number of info items mismatch for section {out_section['id']}",
            )
            for out_info, expected_info in zip(
                out_section["info"],
                expected_section["info"],
                strict=False,
            ):
                assert_equal(
                    out_info["id"],
                    expected_info["id"],
                    f"Info ID mismatch for section {out_section['id']}",
                )
                assert_equal(
                    out_info["summary"],
                    expected_info["summary"],
                    f"Info summary mismatch for section {out_section['id']},"
                    + f"info {out_info['id']}",
                )
                assert_equal(
                    out_info["detail"],
                    expected_info["detail"],
                    f"Info detail mismatch for section {out_section['id']}, "
                    + f"info {out_info['id']}",
                )

            assert_equal(
                len(out_section["checks"]),
                len(expected_section["checks"]),
                f"Number of checks mismatch for section {out_section['id']}",
            )
            for out_check, expected_check in zip(
                out_section["checks"],
                expected_section["checks"],
                strict=False,
            ):
                assert_equal(
                    out_check["id"],
                    expected_check["id"],
                    f"Check ID mismatch for section {out_section['id']}",
                )
                assert_equal(
                    out_check["result"],
                    expected_check["result"],
                    f"Check result mismatch for section {out_section['id']}, "
                    + f"check {out_check['id']}",
                )
                assert_equal(
                    out_check["summary"],
                    expected_check["summary"],
                    f"Check summary mismatch for section {out_section['id']}, "
                    + f"check {out_check['id']}",
                )
                assert_equal(
                    out_check["detail"],
                    expected_check["detail"],
                    f"Check detail mismatch for section {out_section['id']}, "
                    + f"check {out_check['id']}",
                )
                assert_equal(
                    out_check["recommend"],
                    expected_check["recommend"],
                    f"Check recommendations mismatch for section {out_section['id']},"
                    + f"check {out_check['id']}",
                )

        if failures:
            print("The following checks failed:")
            for failure in failures:
                print(f"- {failure}")
            print(
                "Copilot output with new changes saved to tests/temp_copilot.json. "
                + "Replace copilot.json to pass the tests if you are sure of the new "
                + "copilot changes\n"
                + "cp tests/temp_copilot.json tests/copilot.json\n",
            )
            self.fail(f"{len(failures)} checks failed. See above for details.")
        else:
            print("test_check_report passed")

    def test_check_version_releases(self) -> None:
        test_path = os.path.dirname(os.path.abspath(__file__))

        test_cases = [
            ("report-reef.json", "reef", "18.2.0"),
            ("report.quincy.json", "quincy", "17.2.6"),
            ("report.pacific.json", "pacific", "16.2.9"),
            ("report.squid.json", "squid", "19.3.0"),
        ]

        for report_file, release_name, current_version in test_cases:
            with self.subTest(
                report_file=report_file,
                release_name=release_name,
                current_version=current_version,
            ):
                self._check_version_release(
                    test_path,
                    report_file,
                    release_name,
                    current_version,
                )

    def _check_version_release(
        self,
        test_path,
        report_file,
        release_name,
        current_version,
    ) -> None:
        _report = os.path.join(test_path, report_file)
        with open(_report) as file:
            report_json = json.load(file)

        result = ai_module.generate_result(report_json=report_json)
        result_json = json.loads(result.dump())

        version_section = next(
            (
                section
                for section in result_json["sections"]
                if section["id"] == "Version"
            ),
            None,
        )
        assert version_section is not None, (
            f"Version section not found in the result for {report_file}"
        )

        release_check = next(
            (check for check in version_section["checks"] if check["id"] == "Release"),
            None,
        )
        assert release_check is not None, f"Release check not found for {report_file}"

        # Common assertions for all cases
        assert release_check["result"] in ["WARN", "PASS", "FAIL"], (
            f"Release check result should be WARN, PASS, or FAIL for {report_file}"
        )
        assert current_version in release_check["summary"] or any(
            current_version in detail for detail in release_check["detail"]
        ), (
            f"Current version {current_version} should be mentioned in summary or "
            + f"details for {report_file}"
        )

        if release_check["result"] == "PASS":
            assert "recommended stable release" in release_check["summary"].lower(), (
                "Summary should mention recommended stable release for PASS "
                + f"result in {report_file}"
            )
            assert len(release_check["recommend"]) == 0, (
                f"No recommendations expected for PASS result in {report_file}"
            )

        elif release_check["result"] == "WARN":
            assert (
                "Not running a recommended stable release" in release_check["summary"]
                or "newer than our recommended versions" in release_check["summary"]
            ), (
                "Summary should mention not running a recommended stable release or "
                + f"being newer for WARN result in {report_file}"
            )

        elif release_check["result"] == "FAIL":
            assert "CRITICAL" in release_check["summary"], (
                f"Summary should include CRITICAL for FAIL result in {report_file}"
            )
            assert any(
                "upgrade" in recommend.lower()
                for recommend in release_check["recommend"]
            ), (
                "Recommendations should include upgrade advice for FAIL result "
                + f"in {report_file}"
            )


if __name__ == "__main__":
    unittest.main()

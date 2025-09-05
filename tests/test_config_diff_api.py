import json
import os
import unittest
import tempfile
import subprocess

import requests

COPILOT_CONFIG_DIFF_API_ENDPOINT_ENV = "COPILOT_CONFIG_DIFF_API_ENDPOINT"
VERSION_ENV = "COPILOT_VERSION"


class SmokeTestConfigDiffAPI(unittest.TestCase):
    def test_config_diff_api_versions(self):
        config_diff_api_endpoint = os.getenv(COPILOT_CONFIG_DIFF_API_ENDPOINT_ENV)
        if not config_diff_api_endpoint:
            print(
                f"{COPILOT_CONFIG_DIFF_API_ENDPOINT_ENV} env is not set. Skipping tests"
            )
            return
        res = requests.get(f"{config_diff_api_endpoint}/api/versions")
        assert res.ok, (
            f"get versions failed: "
            f"{res.status_code} ({res.reason})\n{res.content.decode()}"
        )
        data = json.loads(res.content.decode())
        assert "count" in data, "Response should contain 'count' field"
        assert "versions" in data, "Response should contain 'versions' field"
        assert data["count"] > 0
        expected_sorted_versions = sorted(
            data["versions"],
            key=lambda v: tuple(int(x) for x in v[1:].split(".")),
            reverse=True,
        )
        assert data["versions"] == expected_sorted_versions

    def test_config_diff_api_version_config(self):
        config_diff_api_endpoint = os.getenv(COPILOT_CONFIG_DIFF_API_ENDPOINT_ENV)
        if not config_diff_api_endpoint:
            print(
                f"{COPILOT_CONFIG_DIFF_API_ENDPOINT_ENV} env is not set. Skipping tests"
            )
            return

        versions_res = requests.get(f"{config_diff_api_endpoint}/api/versions")
        if not versions_res.ok:
            print("Cannot get versions for config test")
            return

        versions_data = json.loads(versions_res.content.decode())
        versions = versions_data["versions"]

        if len(versions) == 0:
            print("No versions available for config test")
            return

        test_version = versions[0]
        res = requests.get(f"{config_diff_api_endpoint}/api/config/{test_version}")

        assert res.ok, (
            f"get config failed for version {test_version}: "
            f"{res.status_code} ({res.reason})\n{res.content.decode()}"
        )

        data = json.loads(res.content.decode())
        assert "version_config" in data, (
            "Response should contain 'version_config' field"
        )
        assert len(data["version_config"]) > 0, "version_config should not be empty"

        version_config = data["version_config"]
        daemon_names = list(version_config.keys())
        expected_daemons = ["global", "mon", "osd", "mgr"]
        found_expected = any(daemon in daemon_names for daemon in expected_daemons)
        assert found_expected, (
            f"Should find at least one of {expected_daemons}, found: {daemon_names}"
        )

    def test_config_diff_api_diff(self):
        config_diff_api_endpoint = os.getenv(COPILOT_CONFIG_DIFF_API_ENDPOINT_ENV)
        if not config_diff_api_endpoint:
            print(
                f"{COPILOT_CONFIG_DIFF_API_ENDPOINT_ENV} env is not set. Skipping tests"
            )
            return
        versions_res = requests.get(f"{config_diff_api_endpoint}/api/versions")
        if not versions_res.ok:
            print("Cannot get versions for diff test")
            return

        versions_data = json.loads(versions_res.content.decode())
        versions = versions_data["versions"]

        version_pairs_to_test = []

        if len(versions) >= 2:
            version_pairs_to_test.append((versions[1], versions[0]))

        if len(versions) >= 5:
            version_pairs_to_test.append((versions[4], versions[0]))

        if len(versions) >= 8:
            version_pairs_to_test.append((versions[7], versions[2]))

        if len(versions) >= 10:
            version_pairs_to_test.append((versions[9], versions[4]))

        for source_version, target_version in version_pairs_to_test:
            res = requests.get(
                f"{config_diff_api_endpoint}/api/diff/{source_version}/{target_version}"
            )
            assert res.ok, (
                f"get diff failed for {source_version} -> {target_version}: "
                f"{res.status_code} ({res.reason})\n{res.content.decode()}"
            )
            data = json.loads(res.content.decode())
            assert "diff" in data, (
                f"Response should contain 'diff' field for {source_version} -> {target_version}"
            )
            assert isinstance(data["diff"], dict), (
                f"Diff should be a dictionary for {source_version} -> {target_version}"
            )

    def test_config_diff_api_sanity_check(self):
        config_diff_api_endpoint = os.getenv(COPILOT_CONFIG_DIFF_API_ENDPOINT_ENV)
        if not config_diff_api_endpoint:
            print(
                f"{COPILOT_CONFIG_DIFF_API_ENDPOINT_ENV} env is not set. Skipping tests"
            )
            return

        source_version = "v16.2.0"
        target_version = "v19.2.0"

        expected_diff_file = os.path.join(
            os.path.dirname(__file__), "expected-config-diff.json"
        )

        if not os.path.exists(expected_diff_file):
            print(
                f"Expected diff file not found: {expected_diff_file}. Skipping sanity test."
            )
            return

        with open(expected_diff_file, "r") as f:
            expected_data = json.load(f)

        res = requests.get(
            f"{config_diff_api_endpoint}/api/diff/{source_version}/{target_version}"
        )
        assert res.ok, (
            f"get diff failed for sanity test {source_version} -> {target_version}: "
            f"{res.status_code} ({res.reason})\n{res.content.decode()}"
        )

        actual_data = json.loads(res.content.decode())

        assert "diff" in actual_data, "Response should contain 'diff' field"

        if actual_data["diff"] != expected_data["diff"]:
            with tempfile.TemporaryDirectory() as tmp_dir:
                actual_file = os.path.join(tmp_dir, "actual_data.json")
                expected_file = os.path.join(tmp_dir, "expected_data.json")

                with open(actual_file, "w") as f:
                    json.dump(actual_data, f, indent=2)
                with open(expected_file, "w") as f:
                    json.dump(expected_data, f, indent=2)

                diff_output = ""
                try:
                    diff_output = subprocess.check_output(
                        ["diff", "-u", expected_file, actual_file],
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                except subprocess.CalledProcessError as e:
                    diff_output = e.output

                raise AssertionError(
                    f"Diff mismatch for {source_version} -> {target_version}.\n"
                    f"Diff (- expected / + actual):\n{diff_output}"
                )
        print(
            f"Sanity test passed: {source_version} -> {target_version} diff matches expected result"
        )


if __name__ == "__main__":
    unittest.main()

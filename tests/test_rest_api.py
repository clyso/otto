import json
import os
import unittest

import requests

REST_API_ENDPOINT_ENV = "COPILOT_REST_API_ENDPOINT"
VERSION_ENV = "COPILOT_VERSION"

# ruff: noqa: S113


class SmokeTestCopilotRESTAPI(unittest.TestCase):
    def test_rest_api(self):
        rest_api_endpoint = os.getenv(REST_API_ENDPOINT_ENV)
        if not rest_api_endpoint:
            print(f"{REST_API_ENDPOINT_ENV} env is not set. Skipping tests")
            return
        url = f"{rest_api_endpoint}/analyze"
        print(f"using {url} endpoint")

        # GET version

        res = requests.get(url=f"{rest_api_endpoint}/version")

        assert res.ok, (
            f"get version failed: "
            f"{res.status_code} ({res.reason})\n{res.content.decode()}"
        )

        out = json.loads(res.content.decode())
        version = os.getenv(VERSION_ENV)
        if not version:
            print(f"{VERSION_ENV} env is not set. Skipping version check")
        else:
            assert out == version

        # DELETE all

        res = requests.delete(url=url)

        assert res.ok, (
            f"delete {url} failed: "
            f"{res.status_code} ({res.reason})\n{res.content.decode()}"
        )

        res = requests.get(url=url)

        assert res.ok, (
            f"get {url} failed: "
            f"{res.status_code} ({res.reason})\n{res.content.decode()}"
        )

        out = json.loads(res.content.decode())

        assert len(out) == 0

        for report_file in os.listdir("tests/reports/"):
            with open(os.path.join("tests/reports", report_file)) as f:
                report = f.read()

            # POST

            data = json.dumps({"report": report}).encode()
            headers = {"Content-Type": "application/json"}
            res = requests.post(url=url, headers=headers, data=data)

            assert res.ok, (
                f"tests/reports/{report_file} post failed: "
                f"{res.status_code} ({res.reason})\n{res.content.decode()}"
            )

            out = json.loads(res.content.decode())
            assert len(out) == 1, "expecting {result_id : result}"

            result_id = next(iter(out.keys()))
            result = out[result_id]

            # GET

            res = requests.get(url=f"{url}/{result_id}")

            assert res.ok, (
                f"tests/reports/{report_file} get {result_id} failed: "
                f"{res.status_code} ({res.reason})\n{res.content.decode()}"
            )

            out = json.loads(res.content.decode())
            assert len(out) == 1, "expecting {result_id : result}"

            get_result_id = next(iter(out.keys()))
            get_result = out[get_result_id]

            assert get_result_id == result_id
            assert get_result == result

            # DELETE

            res = requests.delete(url=f"{url}/{result_id}")

            assert res.ok, (
                f"tests/reports/{report_file} delete {result_id} failed: "
                f"{res.status_code} ({res.reason})\n{res.content.decode()}"
            )

            out = json.loads(res.content.decode())
            assert len(out) == 1, "expecting {result_id : result}"

            delete_result_id = next(iter(out.keys()))
            delete_result = out[delete_result_id]

            assert delete_result_id == result_id
            assert delete_result == result

            # GET (NOENT)

            res = requests.get(url=f"{url}/{result_id}")

            assert not res.ok
            assert res.status_code == 404

            out = json.loads(res.content.decode())
            assert out == {"detail": f"{result_id} not found"}

            # DELETE (NOENT)

            res = requests.delete(url=f"{url}/{result_id}")

            assert res.ok, (
                f"tests/reports/{report_file} delete {result_id} failed: "
                f"{res.status_code} ({res.reason})\n{res.content.decode()}"
            )

            out = json.loads(res.content.decode())
            assert len(out) == 1, "expecting {result_id : result}"

            delete_result_id = next(iter(out.keys()))
            delete_result = out[delete_result_id]

            assert delete_result_id == result_id
            assert delete_result is None

            print(f"tests/reports/{report_file} OK")

        # prepare for GET list, DELETE all tests

        result_ids = []

        for report_file in os.listdir("tests/reports/"):
            with open(os.path.join("tests/reports", report_file)) as f:
                report = f.read()

            data = json.dumps({"report": report}).encode()
            headers = {"Content-Type": "application/json"}
            res = requests.post(url=url, headers=headers, data=data)

            assert res.ok, (
                f"tests/reports/{report_file} post failed: "
                f"{res.status_code} ({res.reason})\n{res.content.decode()}"
            )

            out = json.loads(res.content.decode())
            assert len(out) == 1, "expecting {result_id : result}"

            result_id = next(iter(out.keys()))
            result_ids.append(result_id)

        # GET list

        res = requests.get(url=url)

        assert res.ok, (
            f"get {url} failed: "
            f"{res.status_code} ({res.reason})\n{res.content.decode()}"
        )

        out = json.loads(res.content.decode())

        assert len(out) == len(result_ids)
        for result_id in result_ids:
            assert result_id in out

        # DELETE all

        res = requests.delete(url=url)

        assert res.ok, (
            f"delete {url} failed: "
            f"{res.status_code} ({res.reason})\n{res.content.decode()}"
        )

        res = requests.get(url=url)

        assert res.ok, (
            f"get {url} failed: "
            f"{res.status_code} ({res.reason})\n{res.content.decode()}"
        )

        out = json.loads(res.content.decode())

        assert len(out) == 0


if __name__ == "__main__":
    unittest.main()

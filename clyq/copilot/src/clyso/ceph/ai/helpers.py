# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import fnmatch
import os

import yaml

local_path = os.path.dirname(os.path.abspath(__file__))
versions_file = os.path.join(local_path, "versions.yaml")
with open(versions_file) as file:
    versiondb = yaml.safe_load(file)

bugs_file = os.path.join(local_path, "bugs.yaml")
with open(bugs_file) as file:
    bugdb = yaml.safe_load(file)

health_file = os.path.join(local_path, "health.yaml")
with open(health_file) as file:
    healthdb = yaml.safe_load(file)

os_file = os.path.join(local_path, "os.yaml")
with open(os_file) as file:
    osdb = yaml.safe_load(file)


def to_version(version: str) -> str:
    # e.g. map 16.2.13-0 to 16.2.13
    #      map v16 to 16
    return version.split("-")[0].replace("v", "")


def to_major(version: str) -> str:
    # e.g. map 16.2.13-0 to v16
    x = to_version(version).split(".")[0]
    if x.startswith("v"):
        return x
    return "v" + x


def to_release(version: str) -> str:
    major = to_major(version)
    return versiondb["releases"][major].get("name")


def recommended_versions():
    return [
        v["version"]
        for v in versiondb["releases"].values()
        if v.get("recommended", False) and "version" in v
    ]


def recommended_minor(version):
    major = to_major(version)
    release = versiondb["releases"].get(major)
    return release["version"] if release and "version" in release else None


def map_score_to_grade(score) -> str:
    assert 0.0 <= score <= 1.0, f"Score must be between 0 and 1, not {score}"

    if score >= 0.97:
        return "A+"
    if score >= 0.93:
        return "A"
    if score >= 0.90:
        return "A-"
    if score >= 0.87:
        return "B+"
    if score >= 0.83:
        return "B"
    if score >= 0.80:
        return "B-"
    if score >= 0.70:
        return "C"
    if score >= 0.60:
        return "D"
    return "F"


def known_bugs(version, severity="high"):
    def match_version(version, pattern):
        # Check for range
        if "[" in pattern and "]" in pattern:
            start, end = map(int, pattern.split("[")[1].split("]")[0].split("-"))
            base = pattern.split("[")[0]
            return any(version == f"{base}{i}" for i in range(start, end + 1))
        # Check for wildcard
        return fnmatch.fnmatch(version, pattern)

    def is_affected(version, patterns) -> bool:
        return any(match_version(version, pattern) for pattern in patterns)

    version = version.split("-")[0]

    found = []
    for bug in bugdb["bugs"]:
        if (
            is_affected(version, bug["affected_versions"])
            and severity == bug["severity"]
        ):
            found.append(bug)
    return (bugdb["last_updated"], found)

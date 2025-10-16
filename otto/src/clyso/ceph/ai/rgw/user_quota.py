# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import sys
from typing import TextIO

import prettytable

from clyso.ceph.api.commands import (
    radosgw_admin_global_quota_get,
    radosgw_admin_user_list,
    radosgw_admin_user_info,
)
from clyso.ceph.api.schemas import (
    MalformedCephDataError,
    RGWGlobalQuotaResponse,
    RGWUserListResponse,
    RGWUserInfoResponse,
    RGWQuotaSettings,
)


class RGWUserQuota:
    """List and display RGW user quota settings."""

    def __init__(
        self,
        verbose: bool = False,
        output_format: str = "plain",
        output_stream: TextIO = sys.stdout,
        error_stream: TextIO = sys.stderr,
    ) -> None:
        self.verbose: bool = verbose
        self.output_format: str = output_format
        self.output_stream: TextIO = output_stream
        self.error_stream: TextIO = error_stream

    def _error(self, msg: str) -> None:
        """Print error message to stderr."""
        print(f"ERROR: {msg}", file=self.error_stream)

    def _info(self, msg: str) -> None:
        """Print info message to stderr."""
        print(f"INFO: {msg}", file=self.error_stream)

    def _debug(self, msg: str) -> None:
        """Print debug message to stderr if verbose mode is enabled."""
        if self.verbose:
            print(f"DEBUG: {msg}", file=self.error_stream)

    def _get_human_readable(self, bytes_value: int, precision: int = 2) -> str:
        """Convert bytes to human-readable format (Ki/Mi/Gi/Ti)."""
        suffixes = ["", "Ki", "Mi", "Gi", "Ti"]
        suffix_index = 0
        value = float(bytes_value)

        while value > 1024 and suffix_index < 4:
            suffix_index += 1
            value = value / 1024.0

        return f"{value:.{precision}f}{suffixes[suffix_index]}"

    def _get_global_quota(self) -> RGWGlobalQuotaResponse:
        """Get global quota from Ceph."""
        try:
            return radosgw_admin_global_quota_get()
        except MalformedCephDataError as e:
            self._error(f"Failed to get global quota: {e}")
            raise ValueError(f"Failed to get global quota: {e}")

    def _get_users(self) -> RGWUserListResponse:
        """Get list of all RGW users."""
        try:
            return radosgw_admin_user_list()
        except MalformedCephDataError as e:
            self._error(f"Failed to get user list: {e}")
            raise ValueError(f"Failed to get user list: {e}")

    def _get_user_info(self, user: str) -> RGWUserInfoResponse:
        """Get user information including quota settings."""
        try:
            return radosgw_admin_user_info(user)
        except MalformedCephDataError as e:
            self._error(f"Failed to get user info for {user}: {e}")
            raise ValueError(f"Failed to get user info: {e}")

    def _print_user_quota(
        self, user_quota_list: list[dict[str, str | RGWQuotaSettings]]
    ) -> None:
        """Print quota information as a pretty table."""
        tbl = prettytable.PrettyTable(
            ("User ID", "Bucket [size objects]", "User [size objects]"),
            hrules=prettytable.HEADER,
            vrules=prettytable.NONE,
        )
        tbl.align["User ID"] = "l"

        for quota in user_quota_list:
            bucket_quota_obj = quota["bucket_quota"]
            user_quota_obj = quota["user_quota"]

            if not isinstance(bucket_quota_obj, RGWQuotaSettings):
                continue
            if not isinstance(user_quota_obj, RGWQuotaSettings):
                continue

            # Format bucket quota
            if bucket_quota_obj.enabled:
                if bucket_quota_obj.max_size > 0:
                    bucket_quota = (
                        f"{self._get_human_readable(bucket_quota_obj.max_size)} "
                    )
                else:
                    bucket_quota = "unlimited "
                if bucket_quota_obj.max_objects > 0:
                    bucket_quota += f"{bucket_quota_obj.max_objects}"
                else:
                    bucket_quota += "unlimited"
            else:
                bucket_quota = "--"

            if user_quota_obj.enabled:
                if user_quota_obj.max_size > 0:
                    user_quota = f"{self._get_human_readable(user_quota_obj.max_size)} "
                else:
                    user_quota = "unlimited "
                if user_quota_obj.max_objects > 0:
                    user_quota += f"{user_quota_obj.max_objects}"
                else:
                    user_quota += "unlimited"
            else:
                user_quota = "--"

            tbl.add_row([quota["user_id"], bucket_quota, user_quota])

        print(tbl, file=self.output_stream)

    def run(self) -> None:
        """Execute the user quota listing workflow."""
        user_quota_list: list[dict[str, str | RGWQuotaSettings]] = []

        global_quota = self._get_global_quota()
        self._debug(f"global quota: {global_quota.model_dump()}")

        users = self._get_users()
        self._debug(f"users: {list(users)}")

        for user in users:
            user_info = self._get_user_info(user)
            self._debug(f"user: {user} info: {user_info.model_dump()}")

            bucket_quota = user_info.bucket_quota
            user_quota = user_info.user_quota

            # If quota not enabled, use global defaults
            if not bucket_quota.enabled:
                bucket_quota = global_quota.bucket_quota
            if not user_quota.enabled:
                user_quota = global_quota.user_quota

            user_quota_list.append(
                {
                    "user_id": user,
                    "bucket_quota": bucket_quota,
                    "user_quota": user_quota,
                }
            )
        if self.output_format != "plain":
            # Convert Pydantic objects to dicts for JSON serialization
            json_output = [
                {
                    "user_id": q["user_id"],
                    "bucket_quota": q["bucket_quota"].model_dump()
                    if isinstance(q["bucket_quota"], RGWQuotaSettings)
                    else q["bucket_quota"],
                    "user_quota": q["user_quota"].model_dump()
                    if isinstance(q["user_quota"], RGWQuotaSettings)
                    else q["user_quota"],
                }
                for q in user_quota_list
            ]
            if self.output_format == "json":
                print(json.dumps(json_output), file=self.output_stream)
            elif self.output_format == "json-pretty":
                print(json.dumps(json_output, indent=4), file=self.output_stream)
        else:
            self._print_user_quota(user_quota_list)

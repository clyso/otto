# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import sys
import errno
from typing import Any, Optional

from clyso.ceph.ai.rgw.incomplete_multipart_list import RGWIncompleteMultipartList
from clyso.ceph.ai.rgw.user_df import RGWUserDF
from clyso.ceph.ai.rgw.user_quota import RGWUserQuota
from clyso.ceph.api.schemas import MalformedCephDataError


class RGWFindIncompleteMultipartListCommand:
    """Command class that orchestrates RGW find-incomplete-multipart-list workflow"""

    def __init__(self, args: Any):
        self.args = args
        self.finder: Optional[RGWIncompleteMultipartList] = None

    def execute(self) -> None:
        """Execute the complete RGW incomplete-multipart-list workflow"""
        try:
            self._validate_args()
            self._setup_finder()
            self._run_finder()
        except ValueError as e:
            print(f"Argument validation error: {e}", file=sys.stderr)
            sys.exit(errno.EINVAL)
        except MalformedCephDataError as e:
            print(f"Error parsing Ceph data: {e}", file=sys.stderr)
            sys.exit(errno.EIO)
        except Exception as e:
            print(f"Error during RGW incomplete-multipart-list: {e}", file=sys.stderr)
            sys.exit(errno.EIO)

    def _validate_args(self) -> None:
        """Validate the arguments"""
        valid_formats = ["plain", "json", "json-pretty"]
        if self.args.format not in valid_formats:
            raise ValueError(
                f"Invalid format: {self.args.format}. Must be one of {valid_formats}"
            )

    def _setup_finder(self) -> None:
        """Initialize the RGW incomplete-multipart-list finder"""

        self.finder = RGWIncompleteMultipartList(
            buckets=self.args.bucket if self.args.bucket else None,
            verbose=self.args.verbose,
            include_rados_objects=self.args.rados_objects,
            output_format=self.args.format,
            output_stream=self.args.output_stream,
            error_stream=self.args.error_stream,
        )

    def _run_finder(self) -> None:
        """Run the RGW incomplete-multipart-list finder"""
        if not self.finder:
            raise RuntimeError("Finder not initialized")
        self.finder.run()


class RGWUserDFCommand:
    """Command class that orchestrates RGW user-df workflow"""

    def __init__(self, args: Any):
        self.args = args
        self.calculator: Optional[RGWUserDF] = None

    def execute(self) -> None:
        """Execute the complete RGW user-df workflow"""
        try:
            self._validate_args()
            self._setup_calculator()
            self._run_calculator()
        except ValueError as e:
            print(f"Argument validation error: {e}", file=sys.stderr)
            sys.exit(errno.EINVAL)
        except MalformedCephDataError as e:
            print(f"Error parsing Ceph data: {e}", file=sys.stderr)
            sys.exit(errno.EIO)
        except Exception as e:
            print(f"Error during RGW user-df: {e}", file=sys.stderr)
            sys.exit(errno.EIO)

    def _validate_args(self) -> None:
        """Validate the arguments"""
        if not self.args.user:
            raise ValueError("user is required")

    def _setup_calculator(self) -> None:
        """Initialize the RGW user-df calculator"""

        self.calculator = RGWUserDF(
            users=self.args.user,
            verbose=self.args.verbose,
            process_objects=self.args.process_objects,
            output_stream=sys.stdout,
            error_stream=sys.stderr,
        )

    def _run_calculator(self) -> None:
        """Run the RGW user-df calculator"""
        if not self.calculator:
            raise RuntimeError("Calculator not initialized")
        self.calculator.run()


class RGWUserQuotaCommand:
    """Command class that orchestrates RGW user-quota workflow"""

    def __init__(self, args: Any):
        self.args = args
        self.quota_lister: Optional[RGWUserQuota] = None

    def execute(self) -> None:
        """Execute the complete RGW user-quota workflow"""
        try:
            self._validate_args()
            self._setup_quota_lister()
            self._run_quota_lister()
        except ValueError as e:
            print(f"Argument validation error: {e}", file=sys.stderr)
            sys.exit(errno.EINVAL)
        except MalformedCephDataError as e:
            print(f"Error parsing Ceph data: {e}", file=sys.stderr)
            sys.exit(errno.EIO)
        except Exception as e:
            print(f"Error during RGW user-quota: {e}", file=sys.stderr)
            sys.exit(errno.EIO)

    def _validate_args(self) -> None:
        """Validate the arguments"""
        valid_formats = ["plain", "json", "json-pretty"]
        if self.args.format not in valid_formats:
            raise ValueError(
                f"Invalid format: {self.args.format}. Must be one of {valid_formats}"
            )

    def _setup_quota_lister(self) -> None:
        """Initialize the RGW user-quota lister"""
        self.quota_lister = RGWUserQuota(
            verbose=self.args.verbose,
            output_format=self.args.format,
            output_stream=sys.stdout,
            error_stream=sys.stderr,
        )

    def _run_quota_lister(self) -> None:
        """Run the RGW user-quota lister"""
        if not self.quota_lister:
            raise RuntimeError("Quota lister not initialized")
        self.quota_lister.run()

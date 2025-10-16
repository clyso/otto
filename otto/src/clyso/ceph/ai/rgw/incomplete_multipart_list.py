# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import re
import subprocess
import sys
from typing import Any, Optional, TextIO

from clyso.ceph.api.commands import (
    radosgw_admin_bucket_list,
    radosgw_admin_bucket_list_objects,
)
from clyso.ceph.api.schemas import MalformedCephDataError


MULTIPART_UPLOAD_ID_PREFIX = "2~"


class IncompleteMultipartUpload:
    """Represents an incomplete multipart upload."""

    def __init__(self, upload_id: str, object_name: str) -> None:
        self.upload_id = upload_id
        self.object_name = object_name
        self.parts: list[str] = []
        self.rados_objects: list[str] = []

    def add_part(self, part_name: str) -> None:
        """Add a part to this upload."""
        self.parts.append(part_name)

    def add_rados_object(self, rados_obj: str) -> None:
        """Add a RADOS object to this upload."""
        self.rados_objects.append(rados_obj)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "name": self.object_name,
            "parts": self.parts,
        }
        if self.rados_objects:
            result["rados_objects"] = self.rados_objects
        return result


class RGWIncompleteMultipartList:
    """Find and list incomplete multipart uploads in RGW buckets."""

    def __init__(
        self,
        buckets: Optional[list[str]] = None,
        verbose: bool = False,
        include_rados_objects: bool = False,
        output_format: str = "plain",
        output_stream: TextIO = sys.stdout,
        error_stream: TextIO = sys.stderr,
    ) -> None:
        self.buckets: list[str] = buckets or self._get_buckets()
        self.verbose: bool = verbose
        self.include_rados_objects: bool = include_rados_objects
        self.output_format: str = output_format
        self.output_stream: TextIO = output_stream
        self.error_stream: TextIO = error_stream
        self.incomplete_uploads: dict[str, dict[str, IncompleteMultipartUpload]] = {}

    def _get_buckets(self) -> list[str]:
        """Get list of all buckets from RGW."""
        try:
            bucket_list = radosgw_admin_bucket_list()
            return list(bucket_list.root)
        except MalformedCephDataError as e:
            raise ValueError(f"Failed to get bucket list: {e}")

    def _error(self, msg: str) -> None:
        """Print error message to stderr."""
        print(f"ERROR: {msg}", file=self.error_stream)

    def _debug(self, msg: str) -> None:
        """Print debug message to stderr if verbose mode is enabled."""
        if self.verbose:
            print(f"DEBUG: {msg}", file=self.error_stream)

    def _list_incomplete_multipart(
        self, bucket: str
    ) -> dict[str, IncompleteMultipartUpload]:
        """
        List incomplete multipart uploads in a bucket.
        """
        try:
            bucket_objects = radosgw_admin_bucket_list_objects(bucket)
        except MalformedCephDataError as e:
            self._error(f"Failed to list bucket {bucket}: {e}")
            return {}

        incomplete_uploads: dict[str, IncompleteMultipartUpload] = {}

        # Regex to match: _multipart_<name>.<upload_id>.<meta|part_number>
        regex = re.compile(
            rf"^_multipart_(.+)\.({MULTIPART_UPLOAD_ID_PREFIX}.+)\.(meta|\d+)$"
        )

        for obj in bucket_objects:
            match = regex.match(obj.name)
            if match:
                self._debug(f"Found mp object: {bucket}/{obj.name}")
                obj_name = match.group(1)
                upload_id = match.group(2)
                what = match.group(3)

                # Create upload entry if it doesn't exist
                if upload_id not in incomplete_uploads:
                    incomplete_uploads[upload_id] = IncompleteMultipartUpload(
                        upload_id, obj_name
                    )

                # Add part (skip .meta files)
                if what != "meta":
                    incomplete_uploads[upload_id].add_part(obj.name)

        return incomplete_uploads

    def _list_rados_objects(
        self, bucket: str, incomplete_uploads: dict[str, IncompleteMultipartUpload]
    ) -> None:
        """
        List RADOS objects for incomplete multipart uploads.
        """
        fs = "\x1f"  # Field separator
        regex = re.compile(rf"^(.+)\.({MULTIPART_UPLOAD_ID_PREFIX}.+)\.(\d+)$")

        cmd = [
            "radosgw-admin",
            "bucket",
            "radoslist",
            "--rgw-obj-fs",
            fs,
            "--bucket",
            bucket,
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )

            while True:
                line = process.stdout.readline()
                if not line:
                    return

                try:
                    rados_obj, _bucket, name = tuple(line.rstrip().split(fs))
                    self._debug(f"Got {rados_obj} {_bucket} {name}")

                    match = regex.match(name)
                    if match:
                        self._debug(f"Processing {rados_obj} {name}")
                        upload_id = match.group(2)
                        if upload_id not in incomplete_uploads:
                            continue

                        self._debug(f"Adding {rados_obj} to upload {upload_id}")
                        incomplete_uploads[upload_id].add_rados_object(rados_obj)

                except ValueError as e:
                    self._debug(f"Failed to parse radoslist line: {e}")
                    continue

        except Exception as e:
            self._error(f"Failed to list rados objects: {e}")
            return

    def _print_incomplete_multipart(self) -> None:
        """
        Print results in plain text format.
        """
        for bucket, uploads in self.incomplete_uploads.items():
            if not uploads:
                continue

            print(f"Bucket: {bucket}", file=self.output_stream)
            for upload_id, upload in uploads.items():
                print(f"  Upload ID: {upload_id}", file=self.output_stream)
                print(f"    Name: {upload.object_name}", file=self.output_stream)
                print("    Parts:", file=self.output_stream)
                for part in upload.parts:
                    print(f"      {part}", file=self.output_stream)

                if upload.rados_objects:
                    print("    Rados objects:", file=self.output_stream)
                    for rados_obj in upload.rados_objects:
                        print(f"      {rados_obj}", file=self.output_stream)

    def run(self) -> None:
        """
        Execute the complete workflow.
        """
        self._debug(f"Buckets: {self.buckets}")

        # Find incomplete multipart uploads in all buckets
        for bucket in self.buckets:
            self.incomplete_uploads[bucket] = self._list_incomplete_multipart(bucket)

        # Optionally list RADOS objects
        if self.include_rados_objects:
            for bucket, uploads in self.incomplete_uploads.items():
                if not uploads:
                    continue
                self._list_rados_objects(bucket, uploads)

        if self.output_format != "plain":
            result = {
                bucket: {
                    upload_id: upload.to_dict() for upload_id, upload in uploads.items()
                }
                for bucket, uploads in self.incomplete_uploads.items()
            }
            if self.output_format == "json":
                print(json.dumps(result), file=self.output_stream)
            elif self.output_format == "json-pretty":
                print(json.dumps(result, indent=4), file=self.output_stream)
        else:
            self._print_incomplete_multipart()

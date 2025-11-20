# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import sys
import subprocess
import argparse

from clyso.ceph.ai.rgw.command import (
    RGWFindIncompleteMultipartListCommand,
    RGWUserDFCommand,
    RGWUserQuotaCommand,
)


def get_tools_dir() -> str:
    """Get the tools directory path"""
    tools_dir_candidates = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../otto/tools")),
        "/usr/libexec/otto/tools",
        "/usr/share/otto/tools",
        "/usr/lib/otto/tools",
    ]

    for tools_dir in tools_dir_candidates:
        if os.path.exists(tools_dir):
            return tools_dir

    return ""


def add_command_rgw(subparsers: argparse.ArgumentParser) -> None:
    parser_rgw = subparsers.add_parser(
        "rgw", help="RGW-related operations and analysis"
    )
    rgw_subparsers = parser_rgw.add_subparsers(description="RGW subcommands")
    rgw_subparsers.required = True

    # find-missing command
    parser_rgw_find_missing = rgw_subparsers.add_parser(
        "find-missing",
        help="Search for rgw objects missing rados objects in data pool",
        description="Search for rgw objects missing rados objects in data pool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:
           otto rgw find-missing -b bucket1 bucket2 -- default.rgw.buckets.data
        """,
    )
    parser_rgw_find_missing.add_argument(
        "data_pool",
        help="data pool name",
        nargs="*",
        default=None,
    )
    parser_rgw_find_missing.add_argument(
        "-b",
        "--bucket",
        metavar="bucket",
        help="bucket name",
        nargs="*",
        default=None,
    )
    parser_rgw_find_missing.add_argument(
        "-w",
        "--workers",
        metavar="N",
        help="number of workers (default: 64)",
        type=int,
        default=64,
    )
    parser_rgw_find_missing.add_argument(
        "-m",
        "--max-concurrent-ios",
        metavar="N",
        help="max concurrent ios for bucket radoslist (default: 512)",
        type=int,
        default=512,
    )
    parser_rgw_find_missing.add_argument(
        "-s",
        "--status-output",
        metavar="file",
        help="status output (default: stderr)",
        default=None,
    )
    parser_rgw_find_missing.add_argument(
        "-d",
        "--processed-buckets-db",
        metavar="file",
        help="processed buckets db",
        default=None,
    )
    parser_rgw_find_missing.add_argument(
        "-c",
        "--corrupted-objects",
        metavar="object_name",
        help="store corrupted objects list in bucket object with this name",
        default=None,
    )
    parser_rgw_find_missing.add_argument(
        "-f",
        "--fix",
        help="recreate missing rados objects (filled with zeros)",
        action="store_true",
        default=False,
    )
    parser_rgw_find_missing.add_argument(
        "-i",
        "--fix-bucket-index",
        help="fix bucket index",
        action="store_true",
        default=False,
    )
    parser_rgw_find_missing.add_argument(
        "-n",
        "--dry-run",
        help="do not do any changes, just print what would be done",
        action="store_true",
        default=False,
    )
    parser_rgw_find_missing.set_defaults(func=subcommand_rgw_find_missing)

    # incomplete-multipart command
    parser_rgw_incomplete_multipart_list = rgw_subparsers.add_parser(
        "incomplete-multipart-list", help="List incomplete multipart uploads"
    )
    parser_rgw_incomplete_multipart_list.add_argument(
        "bucket",
        help="bucket name",
        nargs="*",
        default=None,
    )
    parser_rgw_incomplete_multipart_list.add_argument(
        "-v",
        "--verbose",
        help="verbose output",
        action="store_true",
    )
    parser_rgw_incomplete_multipart_list.add_argument(
        "-f",
        "--format",
        metavar="format",
        help="format (plain|json|json-pretty, default: plain)",
        default="plain",
    )
    parser_rgw_incomplete_multipart_list.add_argument(
        "-r",
        "--rados-objects",
        help="list rados objects too",
        action="store_true",
    )
    parser_rgw_incomplete_multipart_list.set_defaults(
        func=subcommand_rgw_incomplete_multipart_list,
        output_stream=sys.stdout,
        error_stream=sys.stderr,
    )

    # user-df command
    parser_rgw_user_df = rgw_subparsers.add_parser(
        "user-df", help="Calculate user's usage stats"
    )
    parser_rgw_user_df.add_argument(
        "user",
        help="user name",
        nargs="+",
    )
    parser_rgw_user_df.add_argument(
        "-v",
        "--verbose",
        help="verbose output",
        action="store_true",
    )
    parser_rgw_user_df.add_argument(
        "-o",
        "--process-objects",
        help="get stats from listing objects as well as from bucket stats",
        action="store_true",
    )
    parser_rgw_user_df.set_defaults(func=subcommand_rgw_user_df)

    # user-quota command
    parser_rgw_user_quota = rgw_subparsers.add_parser(
        "user-quota", help="List user's quota"
    )
    parser_rgw_user_quota.add_argument(
        "-v",
        "--verbose",
        help="verbose output",
        action="store_true",
    )
    parser_rgw_user_quota.add_argument(
        "-f",
        "--format",
        metavar="format",
        help="format (plain|json|json-pretty, default: plain)",
        default="plain",
    )
    parser_rgw_user_quota.set_defaults(func=subcommand_rgw_user_quota)


def subcommand_rgw_find_missing(args: argparse.Namespace) -> None:
    """Run the rgw find-missing tool."""
    tools_dir = get_tools_dir()

    if not tools_dir:
        print("Error: Ceph Tools directory not found", file=sys.stderr)
        exit(1)

    find_missing_script = os.path.join(tools_dir, "clyso-rgw-find-missing")

    if not os.path.exists(find_missing_script):
        print(
            f"Error: find-missing script not found at {find_missing_script}",
            file=sys.stderr,
        )
        exit(1)

    cmd = [find_missing_script]

    if args.data_pool:
        cmd.extend(args.data_pool)

    if args.bucket:
        cmd.append("-b")
        cmd.extend(args.bucket)

    if args.workers != 64:
        cmd.extend(["-w", str(args.workers)])

    if args.max_concurrent_ios != 512:
        cmd.extend(["-m", str(args.max_concurrent_ios)])

    if args.status_output:
        cmd.extend(["-s", args.status_output])

    if args.processed_buckets_db:
        cmd.extend(["-d", args.processed_buckets_db])

    if args.corrupted_objects:
        cmd.extend(["-c", args.corrupted_objects])

    if args.fix:
        cmd.append("-f")

    if args.fix_bucket_index:
        cmd.append("-i")

    if args.dry_run:
        cmd.append("-n")

    process = None
    try:
        process = subprocess.Popen(cmd)
        return_code = process.wait()
    except KeyboardInterrupt:
        if process:
            process.terminate()
            return_code = process.wait()
        else:
            print(
                "Process creation interrupted or failed before start.", file=sys.stderr
            )
            exit(1)

    if return_code != 0:
        print(
            f"Error: find-missing script failed with code {return_code}",
            file=sys.stderr,
        )
        exit(return_code)


def subcommand_rgw_incomplete_multipart_list(args: argparse.Namespace) -> None:
    """Execute the rgw incomplete-multipart-list subcommand"""
    command = RGWFindIncompleteMultipartListCommand(args)
    command.execute()


def subcommand_rgw_user_df(args: argparse.Namespace) -> None:
    """Execute the rgw user-df subcommand"""
    command = RGWUserDFCommand(args)
    command.execute()


def subcommand_rgw_user_quota(args: argparse.Namespace) -> None:
    """Execute the rgw user-quota subcommand"""
    command = RGWUserQuotaCommand(args)
    command.execute()

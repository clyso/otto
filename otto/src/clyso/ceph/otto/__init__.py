# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
import errno
import yaml

from clyso.ceph.ai import generate_result
from clyso.ceph.ai.common import OttoParser
from clyso.ceph.api.commands import ceph_report, ceph_command
from clyso.ceph.api.loaders import load_ceph_report, load_config_dump
from clyso.ceph.ai.data import CephData
from clyso.ceph.ai.pg import add_command_pg
from clyso.ceph.otto.upmap import add_command_upmap_remapped
from clyso.__version__ import __version__
from clyso.ceph.ai.cephfs import add_command_cephfs

from clyso.ceph.ai.osd.command import OSDPerfCommand

CONFIG_FILE = "otto.yaml"


def render_progress_bar(data):
    statuses = []
    for section in data["sections"]:
        for check in section["checks"]:
            statuses.append(check["result"])
    characters = {
        "PASS": ".",
        "WARN": "!",
        "FAIL": "X",
    }
    progress_bar = [characters.get(status, "?") for status in statuses]
    return "".join(progress_bar)


def compact_result(result):
    # Load the JSON data
    json_data = json.loads(result)

    # Print a "progress bar"
    print(f"Running tests: {render_progress_bar(json_data)}")

    # Print the summary
    print(
        f"Overall score: {json_data['summary']['score']:g} out of {json_data['summary']['max_score']} ({json_data['summary']['grade']})"
    )

    # Loop over the sections
    warned = False
    for section in json_data["sections"]:
        for check in section["checks"]:
            if check["result"] != "PASS":
                print(
                    f"- {check['result']} in {section['id']}/{check['id']}: {check['summary']}"
                )
                warned = True

    if warned:
        print("Use --verbose or --summary for details and recommendations")


def compact_result_summary(result):
    # Load the JSON data
    json_data = json.loads(result)

    # Print the summary
    print(
        f"Overall score: {json_data['summary']['score']:g} out of {json_data['summary']['max_score']} ({json_data['summary']['grade']})"
    )

    # Loop over the sections
    for section in json_data["sections"]:
        # Only show checks that failed or have warnings
        failed_checks = [
            check for check in section["checks"] if check["result"] != "PASS"
        ]

        if failed_checks:
            print(f"Section: {section['id']}")
            print(
                f"Score: {section['score']:g} out of {section['max_score']} ({section['grade']})"
            )

            # Show info for context
            if section["info"]:
                print("Info:")
                for info in section["info"]:
                    print(f"  - ID: {info['id']}")
                    print(f"    Summary: {info['summary']}")
                    print("    Details:")
                    for detail in info["detail"]:
                        print(f"      - {detail}")
                    if not info["detail"]:
                        print("      - None")

            print("Failed/Warning Checks:")
            for check in failed_checks:
                print(f"  - ID: {check['id']}")
                print(f"    Result: {check['result']}")
                print(f"    Summary: {check['summary']}")
                print("    Details:")
                for detail in check["detail"]:
                    print(f"      - {detail}")
                if not check["detail"]:
                    print("      - None")
                print("    Recommendations:")
                for recommend in check["recommend"]:
                    print(f"      - {recommend}")
                if not check["recommend"]:
                    print("      - None")
                print("")

            print("")


def verbose_result(result):
    # Load the JSON data
    json_data = json.loads(result)

    # Print the summary
    print(
        f"Overall score: {json_data['summary']['score']:g} out of {json_data['summary']['max_score']} ({json_data['summary']['grade']})"
    )

    # Loop over the sections
    for section in json_data["sections"]:
        print(f"Section: {section['id']}")
        print(
            f"Score: {section['score']:g} out of {section['max_score']} ({section['grade']})"
        )
        print("Info:")
        for info in section["info"]:
            print(f"  - ID: {info['id']}")
            print(f"    Summary: {info['summary']}")
            print("    Details:")
            for detail in info["detail"]:
                print(f"      - {detail}")
            if not info["detail"]:
                print("      - None")
        if not section["info"]:
            print("  - None")
        print("Checks:")
        for check in section["checks"]:
            print(f"  - ID: {check['id']}")
            print(f"    Result: {check['result']}")
            print(f"    Summary: {check['summary']}")
            print("    Details:")
            for detail in check["detail"]:
                print(f"      - {detail}")
            if not check["detail"]:
                print("      - None")
            print("    Recommendations:")
            for recommend in check["recommend"]:
                print(f"      - {recommend}")
            if not check["recommend"]:
                print("      - None")
            print("")
        if not section["checks"]:
            print("  - None")
            print("")


def subcommand_checkup(args: argparse.Namespace) -> None:
    data = CephData()
    warnings: list[str] = []
    verbose: bool = getattr(args, "verbose", False)

    using_static_report: bool = bool(getattr(args, "ceph_report_json", None))

    if args.ceph_report_json:
        try:
            data.ceph_report = load_ceph_report(args.ceph_report_json)
        except Exception as e:
            print(
                f"Error: Failed to load ceph report from {args.ceph_report_json}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        try:
            data.ceph_report = ceph_report()
        except Exception as e:
            print(f"Error: Failed to collect ceph report via CLI: {e}", file=sys.stderr)
            sys.exit(1)

    config_dump_file = getattr(args, "ceph_config_dump", None)
    if config_dump_file:
        try:
            data.ceph_config_dump = load_config_dump(config_dump_file)
        except Exception as e:
            if verbose:
                print(
                    f"Warning: Failed to load config dump from {config_dump_file}: {e}",
                    file=sys.stderr,
                )
            warnings.append(
                "Config dump analysis skipped - unable to load configuration data"
            )
    elif not using_static_report:
        try:
            raw_config = ceph_command("ceph config dump -f json")
            if isinstance(raw_config, list):
                data.ceph_config_dump = raw_config
            else:
                warnings.append("Config dump analysis skipped - unexpected format")
        except Exception as e:
            if verbose:
                print(
                    f"Warning: Failed to collect config dump via CLI: {e}",
                    file=sys.stderr,
                )
            warnings.append(
                "Config dump analysis skipped - unable to collect configuration data"
            )
    else:
        warnings.append("Config dump analysis skipped - using static report")

    if args.verbose or args.summary:
        for warning in warnings:
            print(f"Warning: {warning}")

    result = generate_result(ceph_data=data)

    if args.summary:
        compact_result_summary(result.dump())
    elif args.verbose:
        verbose_result(result.dump())
    else:
        compact_result(result.dump())


def subcommand_osd_perf(args):
    """Execute OSD performance analysis command"""
    command = OSDPerfCommand(args)
    command.execute()


def get_tuning_profiles():
    return {
        "balanced": {
            "description": "Balanced tuning for general-purpose workloads.",
            "settings": {
                "osd": {
                    "osd_op_threads": 8,
                },
            },
            "devices": "hdd|mixed|ssd|nvme",
        },
        "performance": {
            "description": "Optimized for high-performance workloads.",
            "settings": {
                "osd": {
                    "osd_op_threads": 16,
                    "osd_memory_target": 2147483648,
                },
            },
        },
        "capacity": {
            "description": "Optimized for large-scale, capacity-oriented workloads.",
            "settings": {
                "osd": {
                    "osd_op_threads": 4,
                },
            },
        },
        "lowmem": {
            "description": "Optimized for low memory nodes, e.g. edge devices.",
            "settings": {
                "osd": {
                    "osd_memory_target": 2147483648,
                },
            },
        },
    }


def profile_list(args):
    profiles = get_tuning_profiles()
    print("Available tuning profiles:")
    for name, profile in profiles.items():
        print(f"- {name}: {profile['description']}")
    profile_show(args)


def profile_set(args):
    profile_name = args.profilename
    profiles = get_tuning_profiles()
    if profile_name not in profiles:
        print(f"Error: Unknown profile '{profile_name}'.")
        profile_list(args)
        return

    config_file = Path(CONFIG_FILE)
    config_data = {"active_profile": profile_name}
    try:
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")
    except Exception as e:
        print(f"Error writing config file: {e}")
        return

    print(f"Successfully set active tuning profile to '{profile_name}'.")


def profile_show(args):
    config_file = Path(CONFIG_FILE)
    if not config_file.exists():
        print("Error: No active tuning profile found.")
        return

    try:
        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error reading config file: {e}")
        return

    active_profile = config.get("active_profile")
    if not active_profile:
        print("Error: No active tuning profile found.")
        return

    print(f"Active tuning profile: {active_profile}")


def profile_verify(args):
    config_file = Path(CONFIG_FILE)
    if not config_file.exists():
        print("Error: No active tuning profile found.")
        return

    try:
        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error reading config file: {e}")
        return

    active_profile = config.get("active_profile")
    if not active_profile:
        print("Error: No active tuning profile found.")
        return

    profiles = get_tuning_profiles()
    profile = profiles.get(active_profile)
    if not profile:
        print(f"Error: Unknown profile '{active_profile}'.")
        return

    settings = profile.get("settings")
    if not settings:
        print(f"Error: No settings found for profile '{active_profile}'.")
        return

    for key, value in settings.items():
        ceph_value = run_ceph_command(["config", "get", "global", key])
        if str(value) != ceph_value.strip():
            print(
                f"Error: Mismatched setting '{key}': expected '{value}', found '{ceph_value.strip()}'."
            )
            return

    print("Current Ceph configuration matches the active profile.")


def get_tools_dir():
    tools_dir_candidates = [
        (Path(__file__).parent / "tools").resolve(),
        Path("/usr/libexec/otto/tools"),
        Path("/usr/share/otto/tools"),
        Path("/usr/lib/otto/tools"),
    ]

    for tools_dir in tools_dir_candidates:
        if tools_dir.exists():
            return tools_dir

    return None


def list_executable_files(directory: Path) -> list[str]:
    """
    Recursively lists executable files in the given directory and all subdirectories.

    Parameters:
    directory (Path): The path to the directory to search in.

    Returns:
    list: A list of paths to executable files.
    """
    if not directory.exists():
        raise FileNotFoundError(errno.ENOENT, f"Directory {directory} does not exist")
    if not directory.is_dir():
        raise NotADirectoryError(
            errno.ENOTDIR, f"Directory {directory} is not a directory"
        )

    executable_files: list[str] = []

    # Walk through the directory
    for file_path in directory.rglob("*"):
        # Check if the file is executable
        if file_path.is_file() and os.access(file_path, os.X_OK):
            executable_files.append(str(file_path.relative_to(directory)))

    return executable_files


def toolkit_help(args):
    tools_dir = get_tools_dir()

    if not tools_dir.exists():
        print("Ceph Tools directory not found", file=sys.stderr)
        exit(errno.ENOENT)

    try:
        print("Available scripts:")
        tools = list_executable_files(tools_dir)
        for tool in tools:
            print(f"  {tool}")
        print("	Use 'otto toolkit <script> -h' for script-specific help")
    except (FileNotFoundError, NotADirectoryError) as e:
        print(f"Error accessing tools directory: {e}", file=sys.stderr)
        exit(e.errno)


def toolkit_echo(args):
    tools_dir = get_tools_dir()
    if not tools_dir.exists():
        print("Ceph Tools directory not found", file=sys.stderr)
        exit(errno.ENOENT)
    script_path = tools_dir / args.script
    if not script_path.exists():
        print(f"Script {args.script} not found", file=sys.stderr)
        exit(errno.ENOENT)
    try:
        content = script_path.read_text()
        print(content)
    except Exception as e:
        print(f"Error reading script {args.script}: {e}", file=sys.stderr)
        exit(errno.EIO)


def toolkit_run(args):
    tools_dir = get_tools_dir()
    if not tools_dir.exists():
        print("Ceph Tools directory not found", file=sys.stderr)
        exit(errno.ENOENT)

    if hasattr(args, "help") and args.help:
        cmd = [tools_dir / args.script, "-h"]
    else:
        cmd = [tools_dir / args.script] + args.args
        cmd_str = f"{args.script} {' '.join(args.args)}"
        print(f"Running tool: {cmd_str}")

    subprocess.run(cmd, check=False)


def planner_upgrade(args):
    print("Upgrade planner is coming soon.")
    return


def planner_capacity(args):
    print("Capacity planner is coming soon.")
    return


def planner_replacement(args):
    print("Hardware replacement planner is coming soon.")
    return


def run_ceph_command(args):
    command = ["ceph"]
    command.extend(args)

    try:
        output = subprocess.check_output(command)
        print(output.decode("utf-8"))
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.output.decode('utf-8')}")
        exit(errno.EIO)


def main():
    # Create the top-level parser
    parser = OttoParser(prog="otto", description="Otto: Your Expert Ceph Assistant.")

    subparsers = parser.add_subparsers(
        title="subcommands",
        description="valid subcommands",
        dest="{cluster, pool, toolkit}",
    )
    parser.add_argument(
        "--version",
        "-v",
        "-V",
        action="version",
        version=f"Otto v{__version__}",
    )
    subparsers.required = True

    # # Add a subparser for the 'help' command
    help_parser = subparsers.add_parser("help", help="Show this help message and exit")
    help_parser.set_defaults(func=lambda args: parser.print_help())

    # create the parser for the "checkup" command
    parser_checkup = subparsers.add_parser(
        "checkup", help="Perform an overall health and safety check on the cluster"
    )
    parser_checkup.add_argument(
        "--ceph_report_json", "-i", type=str, help="analyze this `ceph.report` file"
    )
    parser_checkup.add_argument(
        "--ceph-config-dump", type=str, help="analyze this config dump file"
    )
    parser_checkup.add_argument("--summary", action="store_true", help="Summary output")
    parser_checkup.add_argument("--verbose", action="store_true", help="Verbose output")
    parser_checkup.set_defaults(func=subcommand_checkup)

    # TODO: add back once we start collecting for this
    # parser_checkup.add_argument(
    #     "--ceph-osd-tree", type=str, help="analyze this OSD tree file"
    # )
    # parser_checkup.add_argument(
    #     "--ceph-pg-dump", type=str, help="analyze this PG dump file"
    # )

    # create the parser for the "osd" related commands
    parser_osd = subparsers.add_parser(
        "osd", help="OSD-related operations and analysis"
    )
    osd_subparsers = parser_osd.add_subparsers(description="OSD subcommands")
    osd_subparsers.required = True

    # OSD Performance command
    parser_osd_perf = osd_subparsers.add_parser(
        "perf", help="Analyze OSD performance metrics across the cluster"
    )
    parser_osd_perf.add_argument(
        "osd_id",
        nargs="?",
        type=int,
        help="Specific OSD ID to analyze (e.g., 123)",
    )
    parser_osd_perf.add_argument(
        "-n",
        "--num-osds",
        type=int,
        default=5,
        help="Number of random OSDs to sample (default: 5)",
    )
    parser_osd_perf.add_argument(
        "-f",
        "--file",
        type=str,
        help="JSON file containing OSD perf dump data to analyze",
    )
    parser_osd_perf.set_defaults(func=subcommand_osd_perf)

    # Create the parser for the "pg" related commands
    add_command_pg(subparsers)

    # Create the parser for the "cephfs" related commands
    add_command_cephfs(subparsers)

    # Create the parser for the "upmap" command
    add_command_upmap_remapped(subparsers)

    # HIDE THE PLANNER and PROFILE COMMANDS FOR NOW

    # # Create the parser for the "planner" command
    # parser_planner = subparsers.add_parser('planner', help='Ceph Planning Tools')
    # planner_subparsers = parser_planner.add_subparsers(dest="{upgrade, capacity, replacement}")
    # planner_subparsers.required = True;

    # # Create the parser for the "planner upgrade" command
    # parser_planner_upgrade = planner_subparsers.add_parser('upgrade', help='Plan a ceph upgrade')
    # parser_planner_upgrade.set_defaults(func=planner_upgrade)

    # # Create the parser for the "planner capacity" command
    # parser_planner_capacity = planner_subparsers.add_parser('capacity', help='Ceph capacity planning')
    # parser_planner_capacity.set_defaults(func=planner_capacity)

    # # Create the parser for the "planner replacement" command
    # parser_planner_replacement = planner_subparsers.add_parser('replacement', help='Hardware replacement planning')
    # parser_planner_replacement.set_defaults(func=planner_replacement)

    # # Create the parser for the "profile" command
    # parser_profile = subparsers.add_parser('profile', help='View and apply Ceph Tuning Profiles')
    # profile_subparsers = parser_profile.add_subparsers(dest = "{list,set,show,verify}")
    # profile_subparsers.required = True;

    # # Create the parser for the "profile list" command
    # parser_profile_list = profile_subparsers.add_parser('list', help='List available Ceph tuning profiles')
    # parser_profile_list.set_defaults(func=profile_list)

    # # Create the parser for the "profile set" command
    # parser_profile_set = profile_subparsers.add_parser('set', help='Set a Ceph tuning profile')
    # parser_profile_set.add_argument('profilename', type=str, help='profilename help')
    # parser_profile_set.set_defaults(func=profile_set)

    # # Create the parser for the "profile show" command
    # parser_profile_show = profile_subparsers.add_parser('show', help='Show the currently used Ceph tuning profile')
    # parser_profile_show.set_defaults(func=profile_show)

    # # Create the parser for the "profile verify" command
    # parser_profile_verify = profile_subparsers.add_parser('verify', help='Check if the cluster configuration matches the profile recommendations')
    # parser_profile_verify.set_defaults(func=profile_verify)

    # Create the parser for the "toolkit" command
    parser_toolkit = subparsers.add_parser(
        "toolkit", help="A selection of useful Ceph Tools"
    )
    toolkit_subparsers = parser_toolkit.add_subparsers(
        dest="toolkit_command", help="A selection of useful Ceph Tools", metavar=""
    )
    toolkit_subparsers.required = False
    parser_toolkit.set_defaults(func=toolkit_help)

    parser_echo = toolkit_subparsers.add_parser(
        "echo", help="Display the contents of a script"
    )
    parser_echo.add_argument("script", type=str, help="Name of the script to display")
    parser_echo.set_defaults(func=toolkit_echo)

    tools_dir = get_tools_dir()
    if tools_dir.exists():
        tools = list_executable_files(tools_dir)
        for tool in tools:
            try:
                parser_tool = toolkit_subparsers.add_parser(
                    tool,
                    help=f"Use 'otto toolkit {tool} -h' for help",
                    add_help=False,
                    formatter_class=argparse.RawDescriptionHelpFormatter,
                )
                parser_tool.add_argument(
                    "-h",
                    "--help",
                    action="store_true",
                    help=f"Use 'otto toolkit {tool} -h' for help",
                )
                parser_tool.add_argument(
                    "args",
                    nargs=argparse.REMAINDER,
                    help=f"Arguments for {tool}",
                )
                parser_tool.set_defaults(func=toolkit_run, script=tool)
            except Exception as e:
                print(f"Error adding parser for {tool}: {e}", file=sys.stderr)
                exit(errno.EIO)

    # Parse the arguments and call the appropriate function
    args = parser.parse_args()
    args.func(args)

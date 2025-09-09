import argparse
import json
import os
import subprocess
import sys

import yaml

from clyso.ceph.ai import generate_result
from clyso.ceph.ai.common import (
    CopilotParser,
    load_ceph_report_file,
    CEPH_FILES,
)
from clyso.ceph.api.commands import ceph_report, ceph_command
from clyso.ceph.ai.data import CephData
from clyso.ceph.ai.pg import add_command_pg
from clyso.ceph.copilot.upmap import add_command_upmap
from clyso.__version__ import __version__

from clyso.ceph.ai.osd.command import OSDPerfCommand

CONFIG_FILE = "copilot.yaml"


def collect(args=None):
    skip_confirmation = getattr(args, "yes", True) if args else True
    return ceph_report(skip_confirmation=skip_confirmation)


def collect_data_source(
    explicit_file,
    file_patterns,
    cli_command,
    data_source_name,
    verbose=False,
    args=None,
):
    """
    1. Check if file is explicitly provided via CLI argument
    2. Check if file exists in current directory (using file patterns)
    3. Fall back to running ceph CLI command
    """
    skip_confirmation = getattr(args, "yes", True) if args else True
    if explicit_file:
        try:
            with open(explicit_file, "r") as file:
                return json.load(file)
        except Exception as e:
            if verbose:
                print(
                    f"Warning: Failed to read {data_source_name} from {explicit_file}: {e}",
                    file=sys.stderr,
                )
            return None

    for pattern in file_patterns:
        if os.path.exists(pattern):
            try:
                with open(pattern, "r") as file:
                    return json.load(file)
            except Exception as e:
                if verbose:
                    print(
                        f"Warning: Failed to read {data_source_name} from {pattern}: {e}",
                        file=sys.stderr,
                    )
                continue

    if cli_command:
        return ceph_command(cli_command, skip_confirmation=skip_confirmation)

    return None


def collect_all_data(args):
    """
    Returns a populated CephData object and a list of warnings.
    """
    skip_confirmation = getattr(args, "yes", True)
    data = CephData()
    warnings = []
    verbose = getattr(args, "verbose", False)

    """Load Ceph report from specified file or default location."""
    using_static_report = bool(args.ceph_report_json)

    if using_static_report:
        report = load_ceph_report_file(args.ceph_report_json)
        data.add_ceph_report(report)
    elif os.path.exists(CEPH_FILES["ceph-report"]):
        report = load_ceph_report_file(CEPH_FILES["ceph-report"])
        data.add_ceph_report(report)
    else:
        try:
            report = collect(args)
            data.add_ceph_report(report)
        except Exception as e:
            print(f"Error: Failed to collect ceph report via CLI: {e}", file=sys.stderr)
            sys.exit(1)

    # Collect Config Dump - avoid CLI commands when using static report
    config_dump = collect_data_source(
        getattr(args, "ceph_config_dump", None),
        [CEPH_FILES["config_dump"]],
        None if using_static_report else "ceph config dump -f json",
        "config dump",
        verbose,
        args,
    )
    if config_dump:
        data.add_ceph_config_dump(config_dump)
    else:
        warnings.append(
            "Config dump analysis skipped - unable to collect configuration data"
        )

    return data, warnings


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
    print(f"Running tests: {render_progress_bar(json_data)}\n")

    # Print the summary
    print(
        f"Overall score: {json_data['summary']['score']:g} out of {json_data['summary']['max_score']} ({json_data['summary']['grade']})\n"
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
        print("\nUse --verbose or --summary for details and recommendations")


def compact_result_summary(result):
    # Load the JSON data
    json_data = json.loads(result)

    # Print the summary
    print(
        f"Overall score: {json_data['summary']['score']:g} out of {json_data['summary']['max_score']} ({json_data['summary']['grade']})\n"
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
        f"Overall score: {json_data['summary']['score']:g} out of {json_data['summary']['max_score']} ({json_data['summary']['grade']})\n"
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


def subcommand_checkup(args):
    # CephData creation
    data, warnings = collect_all_data(args)

    # Show warnings for both verbose and summary modes
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

    with open(CONFIG_FILE, "w") as f:
        yaml.dump({"active_profile": profile_name}, f)

    print(f"Successfully set active tuning profile to '{profile_name}'.")


def profile_show(args):
    if not os.path.exists(CONFIG_FILE):
        print("Error: No active tuning profile found.")
        return

    with open(CONFIG_FILE, "r") as f:
        config = yaml.safe_load(f)

    active_profile = config.get("active_profile")
    if not active_profile:
        print("Error: No active tuning profile found.")
        return

    print(f"Active tuning profile: {active_profile}")


def profile_verify(args):
    if not os.path.exists(CONFIG_FILE):
        print("Error: No active tuning profile found.")
        return

    with open(CONFIG_FILE, "r") as f:
        config = yaml.safe_load(f)

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
        os.path.abspath(os.path.join(os.path.dirname(__file__), "tools")),
        "/usr/libexec/ceph-copilot/tools",
        "/usr/share/ceph-copilot/tools",
        "/usr/lib/ceph-copilot/tools",
    ]

    for tools_dir in tools_dir_candidates:
        if os.path.exists(tools_dir):
            return tools_dir

    return None


def list_executable_files(directory):
    """
    Recursively lists executable files in the given directory and all subdirectories.

    Parameters:
    directory (str): The path to the directory to search in.

    Returns:
    list: A list of paths to executable files.
    """
    assert os.path.exists(directory)
    executable_files = []

    # Walk through the directory
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            # Check if the file is executable
            if os.path.isfile(file_path) and os.access(file_path, os.X_OK):
                executable_files.append(os.path.relpath(file_path, directory))

    return executable_files


def toolkit_list(args):
    tools_dir = get_tools_dir()

    print(f"Ceph Tools are installed to {tools_dir}")
    print("\nTools:\n")
    tools = list_executable_files(tools_dir)
    for t in tools:
        print(f"{t}")
    return


def toolkit_run(args):
    tools_dir = get_tools_dir()
    if not tools_dir:
        print("Ceph Tools directory not found", file=sys.stderr)
        exit(1)

    cmd = [os.path.join(tools_dir, args.tool)] + args.args
    cmd_str = f"{args.tool} {' '.join(args.args)}"

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


# note: use jsoncmd to run ceph comamnds with json
def run_ceph_command(args):
    skip_confirmation = getattr(args, "yes", True)
    command = ["ceph"]
    command.extend(args)
    cmd_str = " ".join(command)

    if not skip_confirmation:
        try:
            response = input(f"+ {cmd_str} [y/n]: ").strip().lower()
            if response not in ("y", "yes"):
                print("Command execution cancelled by user.")
                return
        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled by user.")
            return

    try:
        output = subprocess.check_output(command)
        print(output.decode("utf-8"))
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.output.decode('utf-8')}")
        exit(1)


def main():
    # Create the top-level parser
    parser = CopilotParser(
        prog="ceph-copilot", description="Ceph Copilot: Your Expert Ceph Assistant."
    )

    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=True,
        help="Automatically confirm all interactive prompts",
    )

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
        version=f"Clyso Ceph Copilot v{__version__}",
    )
    subparsers.required = True

    # # Add a subparser for the 'help' command
    help_parser = subparsers.add_parser("help", help="Show this help message and exit")
    help_parser.set_defaults(func=lambda args: parser.print_help())

    # create the parser for the "cluster" command
    parser_cluster = subparsers.add_parser(
        "cluster", help="List of commands related to the cluster"
    )
    cluster_subparsers = parser_cluster.add_subparsers(
        dest="{checkup}", description="valid subcommands", help="additional help"
    )
    cluster_subparsers.required = True

    # create the parser for the "pool" command
    parser_pool = subparsers.add_parser(
        "pools", help="Operations and management of Ceph pools"
    )
    pool_subparsers = parser_pool.add_subparsers(
        dest="{pg}", description="valid subcommands for pools", help="additional help"
    )
    pool_subparsers.required = True

    # create the parser for the "checkup" command
    parser_checkup = cluster_subparsers.add_parser(
        "checkup", help="Perform an overall health and safety check on the cluster"
    )
    parser_checkup.add_argument(
        "--ceph_report_json", "-i", type=str, help="analyze this `ceph.report` file"
    )
    parser_checkup.add_argument(
        "--ceph-config-dump", type=str, help="analyze this config dump file"
    )
    # TODO: add back once we start collecting for this
    # parser_checkup.add_argument(
    #     "--ceph-osd-tree", type=str, help="analyze this OSD tree file"
    # )
    # parser_checkup.add_argument(
    #     "--ceph-pg-dump", type=str, help="analyze this PG dump file"
    # )
    parser_checkup.add_argument("--summary", action="store_true", help="Summary output")
    parser_checkup.add_argument("--verbose", action="store_true", help="Verbose output")
    parser_checkup.set_defaults(func=subcommand_checkup)

    # Create the parser for the "osd-perf" command
    parser_osd_perf = cluster_subparsers.add_parser(
        "osd-perf", help="Analyze OSD performance metrics across the cluster"
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

    # Add the upmap command
    add_command_upmap(cluster_subparsers)

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
        dest="{list, run}", help="tool help"
    )
    toolkit_subparsers.required = True

    # Create the parser for the "toolkit list" command
    parser_toolkit_list = toolkit_subparsers.add_parser(
        "list", help="List the included Ceph tools"
    )
    parser_toolkit_list.set_defaults(func=toolkit_list)

    # Create the parser for the "toolkit run" command
    parser_toolkit_run = toolkit_subparsers.add_parser(
        "run",
        help="Run an included Ceph tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n\tceph-copilot toolkit run contrib/jj_ceph_balancer -h",
    )
    parser_toolkit_run.add_argument("tool", type=str, help="tool name")
    parser_toolkit_run.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Name of the tool to run and its arguments",
    )

    parser_toolkit_run.set_defaults(func=toolkit_run)

    # Create the parser for "pg" command
    add_command_pg(pool_subparsers)

    # Parse the arguments and call the appropriate function
    args = parser.parse_args()
    args.func(args)

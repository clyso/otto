import os
import sys
import subprocess
import argparse


def add_command_upmap(subparsers) -> None:
    """Add the upmap command to the cluster subparser."""
    parser_upmap = subparsers.add_parser(
        "upmap",
        help="PG upmap tools to quickly make remapped PGs active+clean",
        description=(
            "Upmap tools use Ceph's pg-upmap-items functionality to quickly modify "
            "all PGs which are currently remapped to become active+clean. "
            "This is useful after changing crush rules, tunables, or adding capacity."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage procedure:
    1. Backup your osdmaps, crush maps, ...
    2. Set the norebalance flag: 'ceph osd set norebalance'
    3. Make your change (tunables, add osds, etc...)
    4. Run this command to generate the script: 'ceph-copilot cluster upmap'
    5. Execute the script twice: 'ceph-copilot cluster upmap | sh -x'
    6. After cluster is 100% active+clean, unset norebalance: 'ceph osd unset norebalance'
    7. The ceph-mgr balancer in upmap mode will gradually remove the added upmap-items entries
""",
    )

    parser_upmap.add_argument(
        "--ignore-backfilling",
        action="store_true",
        help="Ignore PGs that are backfilling but not in backfill+wait state",
    )

    parser_upmap.set_defaults(func=upmap_remapped)


def upmap_remapped(args: argparse.Namespace) -> None:
    """Run the upmap-remapped tool."""
    tools_dir = get_tools_dir()

    if not tools_dir:
        print("Error: Ceph Tools directory not found", file=sys.stderr)
        exit(1)

    upmap_script = os.path.join(tools_dir, "cern/upmap-remapped.py")

    if not os.path.exists(upmap_script):
        print(f"Error: Upmap script not found at {upmap_script}", file=sys.stderr)
        exit(1)

    cmd = [upmap_script]

    if args.ignore_backfilling:
        cmd.append("--ignore-backfilling")

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
        print(f"Error: Upmap script failed with code {return_code}", file=sys.stderr)
        exit(return_code)


def get_tools_dir() -> str:
    """Get the directory containing the tools."""
    tools_dir_candidates = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "tools")),
        "/usr/libexec/ceph-copilot/tools",
        "/usr/share/ceph-copilot/tools",
        "/usr/lib/ceph-copilot/tools",
    ]

    for tools_dir in tools_dir_candidates:
        if os.path.exists(tools_dir):
            return tools_dir

    return ""

from .command import CephfsSessionTopCommand


def add_command_cephfs(subparsers):
    parser_cephfs = subparsers.add_parser(
        "cephfs", help="CephFS-related operations and analysis"
    )
    cephfs_subparsers = parser_cephfs.add_subparsers(description="CephFS subcommands")
    cephfs_subparsers.required = True

    parser_session_top = cephfs_subparsers.add_parser(
        "session-top", help="Display CephFS session top"
    )
    parser_session_top.set_defaults(func=subcommand_session_top)

    parser_session_top.add_argument(
        "-m",
        "--mds",
        metavar="name",
        help="show for this MDS only",
        required=False,
    )
    parser_session_top.add_argument(
        "-F",
        "--fs",
        metavar="cephfs",
        help="show for this fs only",
        required=False,
        default="",
    )
    parser_session_top.add_argument(
        "-f",
        "--file",
        metavar="file",
        help="process session list from file",
        action="append",
        required=False,
    )
    parser_session_top.add_argument(
        "-N",
        "--top",
        metavar="n",
        type=int,
        help="show firs N sessions only (default: %(default)s)",
        required=False,
        default=100,
    )
    parser_session_top.add_argument(
        "-s",
        "--sort-by",
        metavar="loadavg|numcaps|reccaps|relcaps|liveness|capacqu|host|root|count",
        help="sort by specified field (default: %(default)s)",
        default="loadavg",
        required=False,
    )
    parser_session_top.add_argument(
        "-H",
        "--filter-by-host",
        metavar="hostname",
        help="show sessions for this hostname only",
        required=False,
    )
    parser_session_top.add_argument(
        "-X",
        "--filter-by-host-regexp",
        metavar="regexp",
        help="show sessions from hosts matching this regexp",
        required=False,
    )
    parser_session_top.add_argument(
        "-r",
        "--filter-by-root",
        metavar="root",
        help="show sessions for this root only",
        required=False,
    )
    parser_session_top.add_argument(
        "-R",
        "--filter-by-root-regexp",
        metavar="regexp",
        help="show sessions with roots matching this regexp",
        required=False,
    )
    parser_session_top.add_argument(
        "-g",
        "--group-by-host",
        help="group sessions by hostname",
        action="store_true",
        default=False,
    )
    parser_session_top.add_argument(
        "-G",
        "--group-by-root",
        help="group sessions by root",
        action="store_true",
        default=False,
    )


def subcommand_session_top(args):
    """Execute the session top subcommand"""
    command = CephfsSessionTopCommand(args)
    command.execute()

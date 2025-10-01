from clyso.ceph.ai.pg.distribution import PGHistogram
from clyso.ceph.api.commands import ceph_osd_tree, ceph_pg_dump
import json
from pathlib import Path


def add_command_pg(subparsers):
    # Create the parser for "pg" command
    parser_pg = subparsers.add_parser(
        "pg", help="List of scripts related to placement groups (PG)"
    )
    parser_pg = parser_pg.add_subparsers(dest="{distribution}")
    parser_pg.required = True

    # Create the parser for "pg distribution" command
    parser_pg_distribution = parser_pg.add_parser(
        "distribution", help="plot a graph of pg distributions"
    )
    parser_pg_distribution.set_defaults(func=pg_distribution)
    parser_pg_distribution.add_argument(
        "--osd_tree_json", type=str, help="analyze this ceph osd tree file"
    )
    parser_pg_distribution.add_argument(
        "--pg_dump_json", type=str, help="analyze this pg dump file"
    )
    parser_pg_distribution.add_argument(
        "--normalize",
        action="store_true",
        default=False,
        help="Normalize number of PGs to each OSD's CRUSH weight",
    )
    parser_pg_distribution.add_argument(
        "--pools", action="append", help="Only work on these Ceph pool IDs"
    )
    parser_pg_distribution.add_argument("-m", "--min", help="minimum value for graph")
    parser_pg_distribution.add_argument("-x", "--max", help="maximum value for graph")
    parser_pg_distribution.add_argument(
        "-b", "--bins", help="Number of bins to use for the histogram"
    )
    parser_pg_distribution.add_argument(
        "-l",
        "--logscale",
        action="store_true",
        default=False,
        help="Bins grow in logarithmic scale",
    )
    parser_pg_distribution.add_argument(
        "-B",
        "--custom-bins",
        help="Comma separated list of bin edges for the histogram",
    )
    parser_pg_distribution.add_argument(
        "--no-mvsd",
        action="store_false",
        default=True,
        help="Disable the calculation of Mean, Variance and SD (improves performance)",
    )
    parser_pg_distribution.add_argument(
        "-f", "--bin-format", default="%10.4f", help="format for bin numbers"
    )
    parser_pg_distribution.add_argument(
        "-p",
        "--percentage",
        action="store_true",
        default=False,
        help="List percentage for each bar",
    )
    parser_pg_distribution.add_argument("--dot", default="#", help="Dot representation")


def pg_distribution(args):
    """
    Generate PG distribution histogram.

    Now using typed API functions for better type safety and validation.
    """
    if args.osd_tree_json:
        osd_weights = json.loads(Path(args.osd_tree_json).read_text())
    elif Path("osd_info-tree_json").exists():
        osd_weights = json.loads(Path("osd_info-tree_json").read_text())
    else:
        osd_tree = ceph_osd_tree()
        osd_weights = osd_tree.model_dump()

    if args.pg_dump_json:
        pg_stats = json.loads(Path(args.pg_dump_json).read_text())
    elif Path("pg_info-dump_json").exists():
        pg_stats = json.loads(Path("pg_info-dump_json").read_text())
    else:
        pg_dump = ceph_pg_dump()
        pg_stats = pg_dump.model_dump()

    pg_histogram = PGHistogram(osd_weights, pg_stats, args)
    pg_histogram.print_ascii_histogram()

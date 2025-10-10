"""
Typed implementation of upmap-remapped functionality.

This module provides a typed, testable implementation of the CERN upmap-remapped
tool, with full integration into the otto CLI and API layer.

Original CERN tool: tools/cern/upmap-remapped.py
"""

import argparse
import sys

from clyso.ceph.api.commands import CephConnection
from clyso.ceph.api.schemas import OSDDFNode, OSDDumpResponse, PGStat


class UpmapRemappedGenerator:
    """
    Generates upmap commands for remapped PGs.

    This tool uses Ceph's pg-upmap-items functionality to quickly modify
    all PGs which are currently remapped to become active+clean.
    """

    def __init__(
        self, connection: CephConnection, ignore_backfilling: bool = False
    ) -> None:
        """
        Initialize the upmap command generator.

        Args:
            connection: Active CephConnection instance
            ignore_backfilling: Skip PGs that are actively backfilling
        """
        self.conn = connection
        self.ignore_backfilling = ignore_backfilling
        self.osds: list[int] = []
        self.osd_df_nodes: list[OSDDFNode] = []
        self.pool_types: dict[str, str] = {}

    def generate_commands(self) -> list[str]:
        """
        Generate all upmap commands for remapped PGs.

        Returns:
            List of shell commands to execute
        """
        commands: list[str] = []

        if self.ignore_backfilling:
            print("All actively backfilling PGs will be ignored.", file=sys.stderr)

        try:
            self.osds = self.conn.get_osd_list()
            osd_df = self.conn.get_osd_df()
            self.osd_df_nodes = osd_df.nodes
            remapped_pgs = self.conn.get_remapped_pgs()
            osd_dump = self.conn.get_osd_dump()
            self.pool_types = self.conn.get_pool_types()
        except Exception as e:
            print(f"Error loading cluster data: {e}", file=sys.stderr)
            sys.exit(1)

        if not remapped_pgs:
            print("There are no remapped PGs", file=sys.stderr)
            return commands

        existing_upmaps = self._build_upmap_index(osd_dump)

        commands.append(
            r'while ceph status | grep -q "peering\|activating\|laggy"; do sleep 2; done'
        )

        num = 0
        for pg in remapped_pgs:
            if num == 50:
                commands.append(
                    r'wait; sleep 4; while ceph status | grep -q "peering\|activating\|laggy"; do sleep 2; done'
                )
                num = 0

            if self._should_skip_pg(pg):
                continue

            pgid = pg.pgid

            if pgid in existing_upmaps:
                commands.append(self._format_rm_upmap_command(pgid))
                num += 1
                continue

            pool_name = pgid.split(".")[0]
            pool_type = self.pool_types.get(pool_name)

            if not pool_type:
                print(f"Unknown pool type for {pool_name}", file=sys.stderr)
                continue

            is_replicated = pool_type == "replicated"

            try:
                mappings = self._gen_upmap_mappings(pg.up, pg.acting, is_replicated)
            except Exception:
                continue

            cmd = self._format_upmap_command(pgid, mappings)
            if cmd:
                commands.append(cmd)
                num += 1

        commands.append(
            r'wait; sleep 4; while ceph status | grep -q "peering\|activating\|laggy"; do sleep 2; done'
        )

        return commands

    def _should_skip_pg(self, pg: PGStat) -> bool:
        """Check if PG should be skipped based on filters."""
        if self.ignore_backfilling and "backfilling" in pg.state:
            return True
        return False

    def _build_upmap_index(self, osd_dump: OSDDumpResponse) -> set[str]:
        """Build a set of PGIDs that already have upmaps."""
        upmap_index: set[str] = set()
        for upmap_item in osd_dump.pg_upmap_items:
            pgid = str(upmap_item.get("pgid", ""))
            if pgid:
                upmap_index.add(pgid)
        return upmap_index

    def _get_crush_weight(self, osd_id: int) -> float:
        """
        Calculate effective crush weight for an OSD.

        Args:
            osd_id: OSD ID

        Returns:
            Effective crush weight (crush_weight * reweight)
        """
        for node in self.osd_df_nodes:
            if node.id == osd_id:
                crush_weight = node.crush_weight if node.crush_weight else 0.0
                reweight = node.reweight if node.reweight else 1.0
                return crush_weight * reweight
        return 0.0

    def _gen_upmap_mappings(
        self, up: list[int], acting: list[int], replicated: bool = False
    ) -> list[tuple[int, int]]:
        """
        Generate upmap item pairs for a PG.

        Args:
            up: List of up OSDs
            acting: List of acting OSDs
            replicated: True if replicated pool, False if erasure coded

        Returns:
            List of (from_osd, to_osd) tuples
        """
        if len(up) != len(acting):
            raise ValueError("up and acting must be same length")

        mappings = [
            (u, a)
            for u, a in zip(up, acting)
            if u != a and u in self.osds and self._get_crush_weight(a) > 0
        ]

        if replicated:
            p = list(mappings)
            u_set = set(x[0] for x in p)
            a_set = set(x[1] for x in p)
            mappings = list(zip(u_set - a_set, a_set - u_set))
        else:
            for x, y in mappings[:]:
                if (y, x) in mappings:
                    mappings.remove((x, y))
                    mappings.remove((y, x))

            while True:
                swapped = False
                for i in range(len(mappings) - 1):
                    for j in range(i + 1, len(mappings)):
                        if (
                            mappings[j][0] == mappings[i][1]
                            and mappings[j][1] != mappings[i][0]
                        ):
                            mappings[i], mappings[j] = mappings[j], mappings[i]
                            swapped = True

                if not swapped:
                    break

        return mappings

    def _format_upmap_command(self, pgid: str, mappings: list[tuple[int, int]]) -> str:
        """Format upmap command for a PG."""
        if not mappings:
            return ""

        cmd = f"ceph osd pg-upmap-items {pgid} "
        for from_osd, to_osd in mappings:
            cmd += f"{from_osd} {to_osd} "
        cmd += "&"
        return cmd

    def _format_rm_upmap_command(self, pgid: str) -> str:
        """Format remove upmap command for a PG."""
        return f"ceph osd rm-pg-upmap-items {pgid} &"


def run_upmap_remapped(ignore_backfilling: bool = False) -> None:
    """
    Main entry point for upmap-remapped command.

    Args:
        ignore_backfilling: Skip PGs that are actively backfilling
    """
    with CephConnection() as conn:
        generator = UpmapRemappedGenerator(
            connection=conn, ignore_backfilling=ignore_backfilling
        )
        commands = generator.generate_commands()

        for cmd in commands:
            print(cmd)


def add_command_upmap_remapped(subparsers) -> None:
    """Add the upmap command to the cluster subparser."""
    parser_upmap = subparsers.add_parser(
        "upmap-remapped",
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
    4. Run this command to generate the script: 'otto upmap-remapped'
    5. Execute the script twice: 'otto upmap-remapped | sh -x'
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
    run_upmap_remapped(ignore_backfilling=args.ignore_backfilling)

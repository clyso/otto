#!/usr/bin/env python3

import argparse
import json
import math
import random
import subprocess
import sys
from collections import defaultdict
from typing import Dict, List, Tuple, Set, Iterable, Optional

try:
    from dataclasses import dataclass
except ImportError:
    def dataclass(cls):
        """Minimal drop-in replacement for @dataclass."""
        annotations = getattr(cls, '__annotations__', {})
        fields = list(annotations.keys())

        # Auto-generate __init__
        def __init__(self, *args, **kwargs):
            for name, value in zip(fields, args):
                setattr(self, name, value)
            for name in fields[len(args):]:
                setattr(self, name, kwargs.pop(name))
            if kwargs:
                raise TypeError(f"Unexpected arguments: {', '.join(kwargs)}")

        # Auto-generate __repr__
        def __repr__(self):
            vals = ", ".join(f"{f}={getattr(self, f)!r}" for f in fields)
            return f"{cls.__name__}({vals})"

        # Auto-generate __eq__
        def __eq__(self, other):
            if not isinstance(other, cls):
                return NotImplemented
            return all(getattr(self, f) == getattr(other, f) for f in fields)

        cls.__init__ = __init__
        cls.__repr__ = __repr__
        cls.__eq__ = __eq__
        return cls

# ------------------------- Helpers to talk to Ceph ----------------------------

def run_json(cmd: List[str]) -> dict:
    """Run a command and parse JSON stdout."""
    try:
        out = subprocess.check_output(cmd, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print(f"ERROR running {' '.join(cmd)}:\n{e.output}", file=sys.stderr)
        raise
    return json.loads(out)

def load_osd_and_pg() -> Tuple[dict, dict]:
    try:
        osd_dump = run_json(["ceph", "osd", "dump", "-f", "json"])
        pg_dump = run_json(["ceph", "pg", "dump", "-f", "json"])
    except Exception as e:
        print(f"ERROR: Failed to load cluster state: {e}", file=sys.stderr)
        sys.exit(1)
    return osd_dump, pg_dump

# ---------------------------- Data extraction --------------------------------

PG = str
UpmapItems = Dict[PG, List[Tuple[int, int]]]

@dataclass
class CephSnapshot:
    # From osd dump:
    osd_weight: Dict[int, float]          # effective weights for IN/UP OSDs
    osd_in_up: Set[int]                   # OSDs that are both in and up
    pool_size: Dict[int, int]             # pool_id -> replication size
    pg_upmap_items: UpmapItems            # current upmap items

    # From pg dump:
    pgs_up: Dict[PG, List[int]]           # pgid -> up osd set
    pgs_pool: Dict[PG, int]               # pgid -> pool_id


def parse_snapshot(osd_dump: dict, pg_dump: dict) -> CephSnapshot:
    # osd weights
    osd_weight: Dict[int, float] = {}
    osd_in_up: Set[int] = set()
    for osd in osd_dump.get("osds", []):
        oid = int(osd["osd"])
        up = bool(osd.get("up", 0))
        inn = bool(osd.get("in", 0))
        # effective weight (rough approximation)
        crush_w = float(osd.get("crush_weight", osd.get("weight", 0.0)))
        reweight = float(osd.get("reweight", 1.0))
        w = crush_w * reweight
        if inn and up and w > 0:
            osd_weight[oid] = w
            osd_in_up.add(oid)

    # pool sizes
    pool_size: Dict[int, int] = {}
    for p in osd_dump.get("pools", []):
        pid = int(p["pool"])
        size = int(p.get("size", 3))
        pool_size[pid] = size

    # upmap items
    upmaps: UpmapItems = {}
    for it in osd_dump.get("pg_upmap_items", []):
        pgid = str(it["pgid"])
        pairs = [(int(m["from"]), int(m["to"])) for m in it.get("mappings", [])]
        if pairs:
            upmaps[pgid] = pairs

    # pg up sets
    pgs_up: Dict[PG, List[int]] = {}
    pgs_pool: Dict[PG, int] = {}
    for s in pg_dump.get("pg_stats", []):
        pgid = str(s["pgid"])
        up = s.get("up", [])
        if up:
            pgs_up[pgid] = [int(x) for x in up]
            # pool id is the int prefix before the '.'
            try:
                pid = int(pgid.split(".")[0])
                pgs_pool[pgid] = pid
            except Exception:
                # fallback: skip if we can't parse
                continue

    return CephSnapshot(
        osd_weight=osd_weight,
        osd_in_up=osd_in_up,
        pool_size=pool_size,
        pg_upmap_items=upmaps,
        pgs_up=pgs_up,
        pgs_pool=pgs_pool,
    )

# --------------------------- Balancer core (port) -----------------------------

@dataclass
class Adapter:
    snap: CephSnapshot
    # Mutable copy for proposed changes:
    pg_upmap_items: UpmapItems
    # Optional seed
    seed: Optional[int] = None

    # Interface the algorithm expects:
    def iter_pgs(self, only_pools: Optional[Set[int]]) -> Iterable[PG]:
        for pg in self.snap.pgs_up:
            if only_pools and self.snap.pgs_pool.get(pg) not in only_pools:
                continue
            yield pg

    def pg_to_up_acting_osds(self, pg: PG) -> List[int]:
        # "up" already includes current upmap effects according to pg dump
        return self.snap.pgs_up.get(pg, [])

    def get_pg_pool_size(self, pg: PG) -> int:
        return self.snap.pool_size.get(self.snap.pgs_pool.get(pg, -1), 3)

    def get_osds_weight(self) -> Dict[int, float]:
        return dict(self.snap.osd_weight)

    # CRUSH-agnostic candidate generator:
    def pg_to_raw_upmap(self, pg: PG) -> Tuple[List[int], List[int], List[int]]:
        """
        Returns (raw, orig, out). We use a simple heuristic:
          - orig: current 'up' OSDs for pg
          - out:  best underfull OSDs (not in 'up', in+up, non-duplicate)
        We’ll rotate candidates so each orig has a plausible distinct 'to'.
        """
        up = list(self.snap.pgs_up.get(pg, []))
        # Compute current deviations to pick underfull list
        pgs_by_osd, osd_weight, total_pgs = build_pool_pgs_info(self, None)
        if total_pgs == 0 or sum(osd_weight.values()) == 0:
            return ([], [], [])
        pgs_per_weight = total_pgs / float(sum(osd_weight.values()))
        osd_dev, dev_osd, _, _ = calc_deviations(pgs_by_osd, osd_weight, pgs_per_weight)
        under = [oid for (dev, oid) in dev_osd if dev < 0]

        # Build 'out' aligned with 'up'. Choose first underfull not in up.
        out: List[int] = []
        cursor = 0
        for o in up:
            choice = None
            # try a few underfull options, skipping duplicates and current members
            tries = 0
            while cursor < len(under) and tries < len(under):
                cand = under[cursor % len(under)]
                cursor += 1
                tries += 1
                if cand not in up and cand in self.snap.osd_in_up:
                    choice = cand
                    break
            if choice is None:
                # fallback: any in+up osd not in pg
                for cand in self.snap.osd_in_up:
                    if cand not in up:
                        choice = cand
                        break
            if choice is None:
                # give up for this orig
                continue
            out.append(choice)

        # Align lengths: keep only positions where we have a pair
        orig = up[:len(out)]
        return ([], orig, out)

# ---- Utility functions adapted from the earlier port -------------------------

def build_pool_pgs_info(m: Adapter, only_pools: Optional[Set[int]]):
    pgs_by_osd: Dict[int, Set[PG]] = defaultdict(set)
    total_pgs = 0

    for pg in m.iter_pgs(only_pools):
        up = m.pg_to_up_acting_osds(pg)
        for osd in up:
            pgs_by_osd[osd].add(pg)

    for pg in m.iter_pgs(only_pools):
        total_pgs += m.get_pg_pool_size(pg)

    osd_weight = m.get_osds_weight()
    for oid in list(osd_weight.keys()):
        pgs_by_osd.setdefault(oid, set())

    return pgs_by_osd, osd_weight, total_pgs

def calc_deviations(
    pgs_by_osd: Dict[int, Set[PG]],
    osd_weight: Dict[int, float],
    pgs_per_weight: float,
):
    osd_deviation: Dict[int, float] = {}
    deviation_osd: List[Tuple[float, int]] = []
    stddev = 0.0
    cur_max_abs = 0.0
    for oid, opgs in pgs_by_osd.items():
        if oid not in osd_weight:
            continue
        target = osd_weight[oid] * pgs_per_weight
        deviation = float(len(opgs)) - target
        osd_deviation[oid] = deviation
        deviation_osd.append((deviation, oid))
        stddev += deviation * deviation
        cur_max_abs = max(cur_max_abs, abs(deviation))
    deviation_osd.sort()
    return osd_deviation, deviation_osd, stddev, cur_max_abs

def fill_overfull_underfull(deviation_osd: List[Tuple[float, int]], max_deviation: int):
    overfull: Set[int] = set()
    more_overfull: Set[int] = set()
    underfull: List[int] = []
    more_underfull: List[int] = []

    for dev, oid in sorted(deviation_osd, key=lambda x: x[0], reverse=True):
        if dev <= 0:
            break
        if dev > max_deviation:
            overfull.add(oid)
        else:
            more_overfull.add(oid)

    for dev, oid in deviation_osd:
        if dev >= 0:
            break
        if dev < -int(max_deviation):
            underfull.append(oid)
        else:
            more_underfull.append(oid)

    return overfull, more_overfull, underfull, more_underfull

def build_candidates(m: Adapter, to_skip: Set[PG], only_pools: Optional[Set[int]], aggressive: bool):
    candidates: List[Tuple[PG, List[Tuple[int, int]]]] = []
    for pg, um in m.pg_upmap_items.items():
        if pg in to_skip:
            continue
        if only_pools and m.snap.pgs_pool.get(pg) not in only_pools:
            continue
        candidates.append((pg, list(um)))
    if aggressive:
        random.shuffle(candidates)
    return candidates

def try_drop_remap_overfull(
    candidates, overfull_osd, temp_pgs_by_osd, to_unmap: Set[PG], to_upmap: UpmapItems
) -> bool:
    for pg, um_pairs in candidates:
        new_items: List[Tuple[int, int]] = []
        dropped_any = False
        for (um_from, um_to) in um_pairs:
            if um_from == overfull_osd:
                temp_pgs_by_osd[um_to].discard(pg)
                temp_pgs_by_osd[um_from].add(pg)
                dropped_any = True
            else:
                new_items.append((um_from, um_to))
        if dropped_any:
            if not new_items:
                to_unmap.add(pg)
            else:
                to_upmap[pg] = new_items
            return True
    return False

def try_drop_remap_underfull(
    candidates, underfull_osd, temp_pgs_by_osd, to_unmap: Set[PG], to_upmap: UpmapItems
) -> bool:
    for pg, um_pairs in candidates:
        new_items: List[Tuple[int, int]] = []
        dropped_any = False
        for (um_from, um_to) in um_pairs:
            if um_to == underfull_osd:
                temp_pgs_by_osd[um_to].discard(pg)
                temp_pgs_by_osd[um_from].add(pg)
                dropped_any = True
            else:
                new_items.append((um_from, um_to))
        if dropped_any:
            if not new_items:
                to_unmap.add(pg)
            else:
                to_upmap[pg] = new_items
            return True
    return False

def find_best_remap(orig: List[int], out: List[int], existing: Set[int], osd_deviation: Dict[int, float]) -> int:
    best_pos = -1
    max_dev = 0.0
    for i in range(min(len(orig), len(out))):
        if orig[i] == out[i]:
            continue
        if orig[i] in existing or out[i] in existing:
            continue
        dev = osd_deviation.get(orig[i], 0.0)
        if dev > max_dev:
            max_dev = dev
            best_pos = i
    return best_pos

def add_remap_pair(
    pg: PG,
    pos: int,
    orig: List[int],
    out: List[int],
    pg_pool_size: int,
    existing: Set[int],
    temp_pgs_by_osd: Dict[int, Set[PG]],
    to_upmap: UpmapItems,
):
    o = orig[pos]
    t = out[pos]
    existing.add(o); existing.add(t)
    temp_pgs_by_osd[o].discard(pg)
    temp_pgs_by_osd[t].add(pg)
    if pg in to_upmap:
        items = list(to_upmap[pg])
    else:
        items = []
    # Ensure we don't exceed pool size
    if len(items) >= pg_pool_size:
        return
    # Avoid duplicate mapping pairs
    if (o, t) not in items:
        items.append((o, t))
    to_upmap[pg] = items

@dataclass
class CalcResult:
    num_changed: int
    to_unmap_cmds: List[str]
    to_upmap_cmds: List[str]

def calc_pg_upmaps(
    m: Adapter,
    max_deviation: int,
    max_changes: int,
    only_pools: Optional[Set[int]] = None,
    aggressive: bool = True,
    fast_aggressive: bool = False,
) -> CalcResult:
    if max_changes <= 0:
        return CalcResult(0, [], [])

    rng = random.Random(m.seed)
    random.seed(m.seed)

    # Baseline
    pgs_by_osd, osd_weight, total_pgs = build_pool_pgs_info(m, only_pools)
    if total_pgs == 0 or sum(osd_weight.values()) == 0:
        return CalcResult(0, [], [])
    pgs_per_weight = total_pgs / float(sum(osd_weight.values()))
    osd_deviation, deviation_osd, stddev, cur_max_abs = calc_deviations(
        pgs_by_osd, osd_weight, pgs_per_weight
    )

    num_changed = 0
    skip_overfull = False
    using_more_overfull = False

    # Keep original upmaps to compute deltas -> commands
    original_upmaps = {pg: list(items) for pg, items in m.pg_upmap_items.items()}

    while num_changed < max_changes and cur_max_abs > max_deviation:
        overfull, more_overfull, underfull, more_underfull = fill_overfull_underfull(deviation_osd, max_deviation)
        if not overfull and not underfull:
            break
        if not overfull and underfull:
            overfull = more_overfull
            using_more_overfull = True

        to_skip: Set[PG] = set()
        local_fallback_retried = 0
        n_changes_osd_prev = 0
        osd_to_skip: Set[int] = set()

        while True:
            to_unmap: Set[PG] = set()
            to_upmap: UpmapItems = {}
            temp_pgs_by_osd = {k: set(v) for k, v in pgs_by_osd.items()}

            changed = False
            # Pass 1: overfull search
            for dev, osd in sorted(deviation_osd, key=lambda x: x[0], reverse=True):
                if skip_overfull and underfull:
                    break
                if fast_aggressive and osd in osd_to_skip:
                    continue
                if dev < 0:
                    break
                if not using_more_overfull and dev <= max_deviation:
                    break

                # Undo items targeting this overfull OSD
                cand = build_candidates(m, to_skip, only_pools, aggressive)
                if try_drop_remap_overfull(cand, osd, temp_pgs_by_osd, to_unmap, to_upmap):
                    changed = True
                    break

                # Try new remap one-by-one
                pgs = [pg for pg in pgs_by_osd.get(osd, ()) if pg not in to_skip]
                if aggressive:
                    rng.shuffle(pgs)
                for pg in pgs:
                    _, orig, out = m.pg_to_raw_upmap(pg)
                    if not orig or not out:
                        continue
                    existing: Set[int] = set()
                    # avoid endpoints used by existing items for this PG
                    for a, b in m.pg_upmap_items.get(pg, []):
                        existing.add(a); existing.add(b)
                    if pg in to_upmap:
                        for a, b in to_upmap[pg]:
                            existing.add(a); existing.add(b)
                    pos = find_best_remap(orig, out, existing, osd_deviation)
                    if pos == -1:
                        continue
                    add_remap_pair(pg, pos, orig, out, m.get_pg_pool_size(pg), existing, temp_pgs_by_osd, to_upmap)
                    changed = True
                    break
                if changed:
                    break

                if fast_aggressive:
                    if num_changed == n_changes_osd_prev:
                        osd_to_skip.add(osd)
                    else:
                        n_changes_osd_prev = num_changed

            if not changed:
                # Pass 2: underfull search — undo items that moved data away
                cand = build_candidates(m, to_skip, only_pools, aggressive)
                for dev, osd in deviation_osd:
                    if osd not in underfull:
                        if dev >= 0:
                            break
                        continue
                    if abs(dev) < max_deviation:
                        break
                    if try_drop_remap_underfull(cand, osd, temp_pgs_by_osd, to_unmap, to_upmap):
                        changed = True
                        break

            if not changed:
                if not aggressive:
                    break
                if not skip_overfull:
                    break
                skip_overfull = False
                continue

            # Accept only if stddev improves
            new_osd_dev, new_dev_osd, new_stddev, new_cur_max = calc_deviations(
                temp_pgs_by_osd, osd_weight, pgs_per_weight
            )
            if new_stddev >= stddev:
                involved = set(to_unmap) | set(to_upmap.keys())
                to_skip |= involved
                local_fallback_retried += 1
                if local_fallback_retried > 8:
                    break
                continue

            # Apply
            for pg in to_unmap:
                if pg in m.pg_upmap_items:
                    del m.pg_upmap_items[pg]
            for pg, items in to_upmap.items():
                m.pg_upmap_items[pg] = items

            pgs_by_osd = temp_pgs_by_osd
            osd_deviation, deviation_osd, stddev, cur_max_abs = (
                new_osd_dev, new_dev_osd, new_stddev, new_cur_max
            )
            num_changed += len(to_unmap) + len(to_upmap)
            break

    # Diff original vs final -> commands
    rm_cmds: List[str] = []
    add_cmds: List[str] = []

    final_upmaps = m.pg_upmap_items
    # removals & changes
    for pg, old_items in original_upmaps.items():
        new_items = final_upmaps.get(pg)
        if not new_items:
            rm_cmds.append(f"ceph osd rm-pg-upmap-items {pg}")
        elif new_items != old_items:
            rm_cmds.append(f"ceph osd rm-pg-upmap-items {pg}")
            flat = " ".join(f"{a} {b}" for a, b in new_items)
            add_cmds.append(f"ceph osd pg-upmap-items {pg} {flat}")

    # additions
    for pg, new_items in final_upmaps.items():
        if pg not in original_upmaps:
            flat = " ".join(f"{a} {b}" for a, b in new_items)
            add_cmds.append(f"ceph osd pg-upmap-items {pg} {flat}")

    return CalcResult(num_changed=num_changed, to_unmap_cmds=rm_cmds, to_upmap_cmds=add_cmds)

# ------------------------------- Main ----------------------------------------

def parse_args():
    ap = argparse.ArgumentParser(description="Suggest pg-upmap-items changes.")
    ap.add_argument("--max-deviation", type=int, default=1,
                    help="Stop when |deviation| <= this for all OSDs (default: 1)")
    ap.add_argument("--max-changes", type=int, default=200,
                    help="Maximum number of PG-level changes to propose (default: 200)")
    ap.add_argument("--pools", type=str, default="",
                    help="Comma-separated pool IDs to include (default: all)")
    ap.add_argument("--seed", type=int, default=None,
                    help="Optional RNG seed for reproducibility")
    return ap.parse_args()

def main():
    args = parse_args()
    only_pools: Optional[Set[int]] = None
    if args.pools:
        only_pools = {int(x.strip()) for x in args.pools.split(",") if x.strip()}

    osd_dump, pg_dump = load_osd_and_pg()
    snap = parse_snapshot(osd_dump, pg_dump)

    adapter = Adapter(snap=snap, pg_upmap_items=dict(snap.pg_upmap_items), seed=args.seed)
    res = calc_pg_upmaps(
        adapter,
        max_deviation=args.max_deviation,
        max_changes=args.max_changes,
        only_pools=only_pools,
        aggressive=True,
        fast_aggressive=False,
    )

    if not res.to_unmap_cmds and not res.to_upmap_cmds:
        print("# No improvements found (or already within max deviation).")
        return

    print("# Proposed changes:")
    for cmd in res.to_unmap_cmds:
        print(cmd)
    for cmd in res.to_upmap_cmds:
        print(cmd)

if __name__ == "__main__":
    main()


# `clyso-cephfs-filesystem-upgrade`: `fail_fs`, standbys first

The `fail_fs` method (the default) now mimics, on a stock cephadm (no PR
needed), the staged switch proposed for mgr/cephadm
(`upgrade_staged_switch`): when the filesystem has enough standbys, its
outage is reduced to `fs fail` → `fs set joinable true` → journal replay,
with **no MDS redeploy inside the window**. When it does not, the script
falls back to what `fail_fs` always did (redeploy inside the window), minus
the `orch ps` cache lag, and says so before failing anything;
`--add-standbys` avoids the fallback.


> **`--add-standbys` needs an explicit `count` placement with free slots.**
> cephadm places at most `per_host = 1 + (count - 1) // N` daemons of an MDS
> service on each of its N candidate hosts. The temporary daemons must fit in
> the free slots of the *original* count (`count + extras <= N * per_host`):
> otherwise they double up on a host that already runs one, and when the
> original placement is restored cephadm reconciles that host and removes a
> daemon - possibly a rank holder, i.e. an unplanned failover while the
> filesystem serves. The same goes for a `count_per_host` or bare label/host
> placement. The script checks this before adding anything, declines if there
> is no room, and falls back to redeploying the ranks inside the outage window
> (safe, slightly longer). To get the zero-redeploy switch, make room: add the
> placement label to another host, or add a permanent standby.
>
> While adding, the set of new daemons is accepted only once the service holds
> exactly the raised count and that set is stable over two polls (a failed
> deploy makes cephadm place a replacement and remove the surplus later), and
> the script checks that no host went above the original per-host limit. When
> bringing the service back to its original count after the switch, the idle
> standbys it removes are chosen host by host, over-limit hosts first; if a
> host is still above the limit with only rank holders left, the service is
> left **unmanaged** rather than letting cephadm fail a rank over, and the
> command to restore it is printed.
>
> The candidate hosts are resolved as cephadm does: the explicit host list,
> else the label, else every host, then `host_pattern` if any; draining hosts
> (`_no_schedule`) are left out, but offline and maintenance hosts are kept -
> cephadm does not move MDS daemons away from unreachable hosts, so they count
> in the per-host limit. Since cephadm cannot deploy on an unreachable host,
> the free slots must also be on reachable ones.

An MDS the monitors do not know (down, e.g. on an offline host) holds no rank
and cannot take one while down: it is fenced like the other previous actives,
never waited for inside the outage window, and its redeploy is only scheduled
after the switch.

## How it works

1. `allow_standby_replay` is turned off (so upgraded standbys stay plain
   standbys and keep their gids), and the filesystem is set **not joinable**:
   the actives keep serving, but the monitors no longer promote a standby
   (nor re-balance ranks by affinity).
2. Every **standby** MDS of the filesystem is redeployed on the target image
   while the filesystem keeps serving; nothing changes for clients.
3. If at least `max_mds` upgraded standbys are pinned to the filesystem
   (`mds_join_fs`): the previous actives are fenced (see *Robustness*), then
   the filesystem is failed and set joinable again immediately. The monitors
   hand every rank to the upgraded pinned standbys. The outage is the
   fail/rejoin and the replay.
4. The filesystem is set not joinable again, the fence is lifted, and the
   previous actives, now standbys, are redeployed with the filesystem
   serving. The filesystem is then set joinable and `allow_standby_replay` is
   restored.

Why not joinable in steps 1–2 and 4: that is when MDS of two releases sit
side by side (upgraded standbys next to old actives, then old standbys next
to upgraded actives). An active that crashed then would be replaced by
whichever standby the monitors pick — possibly one of the other release, and
the filesystem would run mixed-version active ranks, which CephFS does not
support. Not joinable, a crashed active is simply not replaced until the
phase ends: in steps 1–2 its rank is recovered by the switch that follows,
in step 4 by the upgraded standbys once the filesystem is joinable again. The
old `fail_fs` never had this exposure (it failed the filesystem before
redeploying anything). `--keep-failover` keeps the filesystem joinable during
those phases instead, if an immediate replacement matters more than a
single-version filesystem; the script then warns about it.

With fewer upgraded standbys than ranks, the remaining daemons are redeployed
inside the window (as with `fail_fs`) — the script says so before failing
anything. `--add-standbys` avoids that: it temporarily raises the placement
count of the `mds.<fs>` service by the missing number, waits for the new
daemons to register as standbys, and does the full switch. The new daemons are
**born on the target image**: `container_image` is set on the `mds.<fs>` config
section before the count is raised (cephadm resolves a new daemon's image from
the config db, and never redeploys an existing daemon because that setting
changed, so the still-old actives are not touched); they are pinned to the
filesystem by the service's `mds_join_fs`. Right after the switch, before
phase 3, the service is brought back to its original number of daemons
**without any failover**, removing idle standbys only, in this order: previous
actives still on the old version (no point upgrading a daemon that is about to
go), then idle extras, then idle upgraded standbys. Phase 3 then upgrades only
the previous actives that stay. Extras that took a rank simply stay as regular
members of the service; only daemon ids differ from before. The spec is set
`unmanaged` for the duration of that cleanup so cephadm neither re-creates nor
picks daemons to remove itself. If the run aborts before the switch, the
extras are removed and the placement and the `container_image` section are
put back as they were
(cephadm's own scale-down removes from the end of its list, active ranks
included).

Every wait inside the outage window uses the monitors (`fs dump`,
`mds metadata`) rather than `orch ps`, whose cache lags ~20 s behind a
redeploy; the `fail_fs` method benefits from the same change.

## Fewer standbys than ranks: the hybrid case

The full switch needs at least `max_mds` upgraded standbys pinned to the
filesystem (`mds_join_fs`) at the moment of `fs fail`. When there are fewer
— or when `mds_join_fs` is not set for the service, since the monitors could
then hand a rank to any standby — the script still runs, but part of the
work moves back inside the outage window:

1. `fs fail`
2. **every** previous active MDS that is not yet on the target version is
   redeployed, back to back (`ceph orch daemon redeploy`), and the script
   waits until the monitors see each of them registered as a standby with a
   new gid and the target version
3. `fs set joinable true`

Compared with `fail_fs`, the hybrid still saves the ~20 s `orch ps` cache
lag and the redeploys of the standbys; compared with the full switch it
costs one redeploy (~3–4 s) per previous active MDS inside the window.
The script announces which case it is in before failing anything:

    Only 1 upgraded standby(s) pinned to cephfs2 for 3 rank(s): 3 MDS will be
    redeployed inside the outage window (re-run with --add-standbys, ...)

Why *every* previous active MDS, and not just the `max_mds − standbys`
missing ones? Because the monitors hand the ranks to the pinned standbys in
gid order. After `fs fail` the previous actives respawn as standbys, on the
old version, with gids lower than anything redeployed afterwards. If only
some of them were redeployed, the ones left on the old version would be
chosen for the remaining ranks before the freshly redeployed ones, and the
filesystem would come back with a mixed-version set of active ranks. The
only safe condition for `joinable true` is: no pinned standby on the old
version — hence all of them.

`--add-standbys` turns the hybrid case into a full switch. With
`max_mds = 3` and 2 standbys:

1. standby-replay off (standby-replay daemons count as standbys once stopped)
2. the 2 existing standbys are redeployed on the target image, filesystem
   serving
3. 2 upgraded standbys for 3 ranks → **1** daemon is missing → the
   placement count of `mds.<fs>` is raised by 1; the new daemon is born on
   the target image (`container_image` set on `mds.<fs>`) and pinned to the
   filesystem by the service's `mds_join_fs`; the script waits for it to
   register as a standby
4. `fs fail` → `fs set joinable true`: the 3 ranks go to the 3 upgraded
   standbys, lowest gids first — the 2 original standbys, then the extra —
   with nothing redeployed inside the window
5. the service goes back to its original number of daemons: 1 of the 3
   previous actives (fenced, idle, still on the old version) is removed
   rather than upgraded; the placement count goes back to its original value
6. the 2 previous actives that stay, now standbys, are redeployed with the
   filesystem serving

Existing standbys are upgraded *before* the extra is added on purpose: the
extra then has the highest gid among the upgraded standbys and only takes a
rank when one is really missing.

## Usage

    clyso-cephfs-filesystem-upgrade -i quay.io/ceph/ceph:v18.2.8 cephfs               # fail_fs is the default
    clyso-cephfs-filesystem-upgrade -i quay.io/ceph/ceph:v18.2.8 --all
    clyso-cephfs-filesystem-upgrade -i ... cephfs2 --add-standbys       # fewer standbys than ranks
    clyso-cephfs-filesystem-upgrade -i ... cephfs --flush-journal       # opt-in
    clyso-cephfs-filesystem-upgrade -i ... cephfs --keep-failover       # see "How it works"

Prerequisites for the full switch: `mds_join_fs` set for the service (`-J`;
without it the script warns and falls back to redeploying inside the window,
and `--add-standbys` is refused), `refuse_standby_for_another_fs`
recommended with several filesystems (`-R`, the script warns otherwise), no
damaged rank. bash 4.4 or later.

`--flush-journal` (off by default) flushes the journal of each active rank,
one at a time, right before the fence and `fs fail`, for a shorter replay; it
adds metadata-pool I/O *before* the outage window, never inside it. It does
lengthen the time the filesystem is not joinable (a crashed active is not
replaced during the flush either), by up to `FLUSH_TIMEOUT` (60 s) per rank;
with `--keep-failover` it runs before the filesystem is set not joinable.

## Caveats

* While the standbys are upgraded (steps 1–2), and while the previous actives
  are (step 4), the filesystem is not joinable: an active MDS that crashes is
  not replaced until the phase ends — at most `REDEPLOY_TIMEOUT` per phase,
  typically tens of seconds. The ranks that are still up keep serving.
* With `--keep-failover`, an active that crashes during those phases is
  replaced at once, by the first pinned standby whatever its release: the
  filesystem then runs mixed-version ranks until the switch (step 3) or the
  script's final check. The mgr/cephadm staged switch has neither trade-off:
  it switches every daemon inside the outage window.
* While fenced (from just before `fs fail` until every rank is back, a few
  seconds), the previous actives are unpinned for **every** filesystem: one
  that needs a standby in that window and has no pinned standby available
  can take one of them as a rank (a pinned standby always wins over them).
  Harmless while every filesystem is on the old release; in a cluster
  upgraded one filesystem at a time, an already-upgraded filesystem could
  pick up an old MDS. Keeping a spare standby pinned to each filesystem
  avoids it.
* The fence relies on the monitors filling *empty* ranks — see *Robustness*.
* On Tentacle and later, `fs fail` refuses a filesystem with `MDS_TRIM` or
  `MDS_CACHE_OVERSIZED`; `--flush-journal` clears the trim backlog.

## Robustness

Before failing the filesystem for a full switch, the script verifies the switch
will really hand every rank to an upgraded standby:

* no MDS of the filesystem is still restarting - it snapshots every gid (rank
  holders and pinned standbys) from the **monitors** twice, `CHURN_CHECK_SECS`
  apart (default 4 s); a redeploy or a cephadm reconciliation in flight restarts
  a daemon and changes its gid, which would scramble which standby wins a rank.
  This check is monitor-based on purpose: `orch ps` lags ~20 s behind a redeploy
  and would wrongly flag the standbys just upgraded in phase 1 as not running.
* the `max_mds` lowest-gid pinned standbys are all on the target version,
  leaving out the daemons about to be fenced (e.g. an active that crashed
  while the filesystem was not joinable and came back as a pinned standby on
  the old release: it is fenced with the others).

If either check fails the script stops **before** `fs fail`, changing nothing,
and says what to fix (typically: let `orch ps` settle, and make the
`mds.<fs> container_image` service pin match the target so cephadm stops
reconciling).

When the filesystem runs with `allow_standby_replay`, the script disables it
first. Disabling it stops the standby-replay daemons, which respawn as plain
standbys after a short gap during which the monitors do not know them. The script
records exactly those daemons and waits until each is a plain standby again before
classifying, so they are upgraded in phase 1 like any other standby (rather than
being seen mid-gap as unknown and mistaken for ranks, which would make it think
there are no standbys and needlessly add some). `allow_standby_replay` is restored
at the end.

**The switch does not rely on gid ordering.** Right before `fs fail`, the script
*fences* the current rank holders: it sets a per-daemon `mds_join_fs` naming a
filesystem that does not exist. The monitors then record them with
`join_fscid` NONE (unpinned), and when a rank is filled
(`FSMap::get_available_standby`) a standby pinned to the filesystem wins over
an unpinned one, whatever the gids. With at least `max_mds` upgraded pinned
standbys (the full-switch condition) the old daemons are therefore never picked:
no old-version MDS takes a rank next to the upgraded ones (CephFS does not
support mixed-version active ranks). `refuse_standby_for_another_fs` plays no
part in this: it only keeps out standbys pinned to *another* filesystem.

"Pinned wins over unpinned" holds unconditionally on reef, squid and tentacle.
On main (after tentacle), standby selection is scored with host
anti-affinity (`standby_enable_host_anti_affinity`, on by default): an
unpinned standby on another host (`SCORE_PREF_VANILLA`, 5) outranks a pinned
one on the host of the addresses to avoid (`SCORE_FALLBACK_MATCH`, 3).
`find_replacement_for()` only passes addresses to avoid for a rank that is
still in `up` (a laggy active being replaced, affinity re-balancing). `fs fail`
purges every rank from `up`, so when the ranks are filled at the switch no
address is avoided and a pinned standby (`SCORE_PREF_MATCH`, 6) still beats an
unpinned one (5). **This is the one assumption the fenced switch rests on**:
the ranks must be empty when the monitors fill them, which is why the fence is
only relied on across `fs fail`.

The fence is applied with the filesystem **not joinable** (`fs set <fs> joinable
false`: the actives keep serving), and the script waits until the monitors show
every fenced daemon unpinned before failing the filesystem. On a joinable
filesystem the monitors' affinity check (`MDSMonitor::check_health`, every tick)
would drop each unpinned active in favour of a pinned standby — one unplanned
failover per tick, to the new version, while the filesystem serves. The fence is
lifted as soon as every rank is back. On an early exit *before* `fs fail`, a
trap lifts it and makes the filesystem joinable again (and removes the
`--add-standbys` extras). On an exit *after* `fs fail` and before every rank is
back, the fence is **kept** — lifting it would let the old daemons compete for
the empty ranks again — and the recovery steps are printed:

    ceph fs set <fs> joinable true         # if not done yet
    # once every rank is active, on the target version:
    for d in <fenced daemons>; do ceph config rm $d mds_join_fs; done

`ceph mds freeze <gid> true` (which makes the monitors skip a daemon) was not
used for the fence: it applies to a gid, which changes on every restart, and
has to be undone per daemon, where a config key survives restarts and is
removed with one command.

After the switch the script also re-checks every rank and, if one is still on the
old version, redeploys the offending rank holders once more to converge.

## Container image settings after the run

`orch daemon redeploy --image` leaves a per-daemon `container_image` override
(`mds.<fs>.<host>.<id>`) on every daemon it touches. Once every MDS of the
service runs the target, the script moves that setting to the service: it sets
`mds.<fs> container_image` to the repo digest the daemons actually run (or to
the image given with `-i` if they do not share one) and removes the per-daemon
overrides - otherwise they would outlive the upgrade and shadow any later
service-level change, and a new daemon of the service would be born on the old
service image. When that image already is the global `container_image`, the
`mds.<fs>` setting is removed instead. Changing these settings redeploys
nothing. A later `ceph orch upgrade` clears every `mds.*` section anyway. If a
daemon of the service does not run the target within 120 s, the overrides are
left in place and the commands to consolidate them are printed.

`--flush-journal` bounds each `flush journal` with `FLUSH_TIMEOUT` (default
60 s): `ceph tell` would otherwise wait forever for an MDS that left the map.

## Dry run

The method was exercised with a small simulator of the monitors' standby
selection (pinned standbys by gid order), of cephadm's `orch ps` cache lag
and of the reconciler (`fakeceph`, not shipped in this repository yet):

    ./fakeceph --init
    (while true; do ./fakeceph --tick; sleep 3; done) &      # cephadm serve loop
    PATH=$PWD/fakebin:$PATH POLL_INTERVAL=1 MON_POLL_INTERVAL=1 \
        ./clyso-cephfs-filesystem-upgrade -i quay.io/ceph/ceph:v18.2.8 cephfs
    grep 'mon:' /tmp/fakeceph.log     # which daemon got which rank, and why

`fakeceph` also models `orch ls --export`, `orch apply -i`, `orch daemon rm`
and a reconciler that adds/removes daemons to match managed specs, so
`--add-standbys` can be exercised too (`cephfs2` in the initial state has one
rank and no standby).

(`fakebin/ceph` is a symlink to `fakeceph`.)

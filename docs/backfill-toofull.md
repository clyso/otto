
# Upmap fix for PGs with backfill toofull warnings

```
health: HEALTH_WARN
10 nearfull osd(s)
10 backfilltoofull osd(s)
Low space hindering backfill (add storage if this doesn't resolve itself): 1 pg backfill_toofull
```

Problem:
Usually when a node goes down or when draining capacity, there are some OSDs that become nearfull and eventually can lead to PGs being backfill_toofull warning pops up.

Why does this happen? Currently the balancer doesn't do a good job of evenly spreading out data based on % utlization of an OSD and it could be the case that there is not enough capacity to backfill data.

```
$ ceph osd df tree
ID    CLASS  WEIGHT       REWEIGHT  SIZE     RAW USE  DATA     OMAP      META      AVAIL     %USE   VAR   PGS  STATUS  TYPE NAME
  -2         31073.90820         -   30 PiB   24 PiB   24 PiB   2.4 TiB    74 TiB   6.1 PiB  79.77  1.00    -          root default
 -10          4310.90576         -  4.2 PiB  3.4 PiB  3.4 PiB   435 GiB   9.7 TiB   863 TiB  79.99  1.00    -              rack rack1
 -51           176.40302         -  176 TiB  144 TiB  144 TiB    41 GiB   422 GiB    32 TiB  81.66  1.02    -                  host ceph-host1
 642    hdd      7.27736   1.00000  7.3 TiB  6.6 TiB  6.6 TiB   4.7 MiB    19 GiB   659 GiB  91.16  1.14   16      up              osd.642      <--- most full
 643    hdd      7.27736   1.00000  7.3 TiB  5.7 TiB  5.6 TiB   5.1 MiB    16 GiB   1.6 TiB  77.70  0.97   15      up              osd.643      <--- least full
 644    hdd      7.27736   1.00000  7.3 TiB  6.1 TiB  6.1 TiB   916 KiB    18 GiB   1.1 TiB  84.40  1.06   15      up              osd.644
 645    hdd      7.27736   1.00000  7.3 TiB  5.9 TiB  5.9 TiB   3.3 MiB    17 GiB   1.4 TiB  81.00  1.02   14      up              osd.645
 647    hdd      7.27736   1.00000  7.3 TiB  5.4 TiB  5.4 TiB   274 KiB    16 GiB   1.9 TiB  74.28  0.93   13      up              osd.647
 648    hdd      7.27736   1.00000  7.3 TiB  5.9 TiB  5.9 TiB   208 KiB    17 GiB   1.4 TiB  81.03  1.02   15      up              osd.648
 649    hdd      7.27736   1.00000  7.3 TiB  6.1 TiB  6.1 TiB   181 KiB    18 GiB   1.1 TiB  84.35  1.06   16      up              osd.649
 650    hdd      7.27736   1.00000  7.3 TiB  6.1 TiB  6.1 TiB   5.4 MiB    18 GiB   1.1 TiB  84.36  1.06   16      up              osd.650
 653    hdd      7.27736   1.00000  7.3 TiB  6.1 TiB  6.1 TiB   3.4 MiB    18 GiB   1.1 TiB  84.46  1.06   16      up              osd.653
....
....
```

An example of a cluster here with OSDs in this cluster that have 91% use, while some other OSD has 74%. It is also true in this cluster that there are very big PG sizes because of the small PG numbers per OSD.

In the event a host goes down, there will be degraded objects. The built-in ceph balancer does not run when there are degraded objects, so CRUSH will decide on which OSD the backfilling PGs will go into. But what if that OSD is backfilltoofull? Well it could be the case that the cluster is now 'stuck', it can't resolve the degraded objects because it can't backfill because an OSD is toofull. 

The solution to this is we can upmap this PG to another OSD. Instead of CRUSH picking a random OSD that could be already 91% full, let's tell it to use the OSD with 77%

The steps would be to
1. Find the PG that is backfill_toofull.
2. Cross reference with `ceph pg dump` to see where that PG is originally from and where it wants to go.
3. Find another OSD that we want to upmap it to, and adhears to the failure domain of the cluster.
4. Construct the upmap command

```
ceph osd pg-upmap-items 70.2e3 642 643
```

This comes very tedious very fast if we have a lot of PGs that are backfill_toofull

There is a script called clyso-upmap-toofull.py that does this for you

```
./clyso-upmap-pg-toofull
# [DRY-RUN] Generated 9 command(s) (use --write to execute or pipe to sh):
ceph osd pg-upmap-items 70.122e 2172 41 801 835 31 29
ceph osd pg-upmap-items 70.103c 452 29
ceph osd pg-upmap-items 70.fa0 1327 1249 1718 2065 454 29
ceph osd pg-upmap-items 70.eaa 307 686 2118 1327 464 29
ceph osd pg-upmap-items 70.4a3 913 1397 456 29
ceph osd pg-upmap-items 70.750 2287 2026 190 922 2026 2002
ceph osd pg-upmap-items 70.980 1637 2478 244 389 464 29
ceph osd pg-upmap-items 70.1937 2524 2175 2489 1089 454 29
```

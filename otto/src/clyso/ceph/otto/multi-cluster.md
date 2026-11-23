# Multi-Cluster Guide

Add each Ceph cluster once, then use it by name. Before a command talks to a
cluster, otto asks it for its fsid and refuses to run if that is not the fsid
saved when you added the cluster.

## Add a cluster

```bash
otto config add --conf /etc/ceph/prod.conf
```

Otto finds the keyring, connects and reads the cluster's name. Press Enter to
accept the defaults.

Options: `--keyring FILE`, `--entity client.X` (default `client.admin`),
`--use` (switch to it), `--yes` (never ask).

To add a second login (for example a read-only user), run it again with
`--keyring` and `--entity`.

## Use it

```bash
otto cluster ls                    # list clusters and logins
otto use berlin                    # switch to a cluster
otto current                       # show the current cluster
otto ceph -s                       # run ceph on the current cluster
otto -C london ceph health         # one command on another cluster
otto -C lab/viewer ceph osd tree   # use a specific login
otto -C lab exec rados lspools     # run any Ceph tool
```

```
CURRENT  NAME    ALIAS  LOGIN   TIER       VERIFIED
*        berlin  -      admin   admin      just now
         -       lab    viewer  read-only  2h ago
```

- **NAME** is stored in the cluster, so everyone sees the same name.
- **ALIAS** is an optional nickname on your machine only.
- **TIER** is what the login may do: `admin`, `read-write`, `read-only` or
  `unknown`. It comes from the last live check (**VERIFIED**), not from every
  command: run `otto config verify NAME` after a user's caps change.

Rename with `otto rename NAME`. It changes an alias here, or the cluster's own
name for everyone (it asks first).

## Safety

Before a command talks to a cluster, and before `otto use` switches, otto asks
the cluster for its fsid (live, every time). If it is not the fsid saved when
you added the cluster, otto refuses. With no cluster selected, `otto ceph` and
`otto exec` refuse too.

- Commands that only read files skip the check: `otto checkup -i report.json`,
  `otto osd perf -f dump.json`, and `otto pg distribution` with both dumps.
- `otto exec` passes the target to the program through `CEPH_ARGS`, `CEPH_CONF`
  and `CEPH_KEYRING`. A program that ignores them is not covered.
- A script printed by `otto -C NAME upmap-remapped` sets its own target and
  checks the fsid again when it runs, so `| sh -x` stays on that cluster.
  Commands printed by other tools (`otto toolkit ...`) do not: run them with
  `| otto -C NAME exec sh` instead of `| sh`.
- `--allow-fsid-mismatch` runs anyway, with a warning. Emergency use only.

```bash
otto config verify berlin    # re-check a login: fsid, name, caps, tier
```

If a cluster was rebuilt on purpose:

```bash
otto config set-cluster berlin --conf /etc/ceph/prod.conf --reset-fsid
otto config verify berlin
```

## Remove

```bash
otto config delete-connection lab/viewer   # one login
otto config delete-cluster berlin          # a cluster and all its logins (asks)
```

This only changes otto's config. The cluster and your keyrings are not touched.

## Config file

`~/.config/otto/config` (YAML, paths only, no keys). Use another file with
`OTTO_CONFIG=FILE`, or several with `OTTO_CONFIG=FILE1:FILE2`.

Tab completion in bash: `source <(otto config completion bash)`

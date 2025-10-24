# Ceph Dev Container

This repository now ships a ready-made container image that boots a tiny Ceph cluster (mon, osd, mgr, mds, rgw). It is intended for local CLI development: build the image once, run it whenever you need `ceph` / `rbd` / `cephfs` commands without touching a real cluster.

## Build the image and run otto in a container

```bash
sudo docker build -t ceph-dev containers/ceph-dev
./containers/scripts/ceph-dev-shell.sh
```

other possible commands
```bash
./containers/scripts/ceph-dev-shell.sh otto cluster checkup --ceph_report_json=tests/report.quincy.json
```

Build args:

- `CEPH_IMG` / `CEPH_TAG` – override the upstream Ceph container source (defaults to `quay.io/ceph/ceph:v19`).

## Run it

Interactive shell with a fresh cluster:

```bash
sudo docker run --rm -it --name ceph-dev ceph-dev
```

For day-to-day development use `containers/scripts/ceph-dev-shell.sh`, which always cleans the cluster (sets `CEPH_BOOTSTRAP=always`), runs `uv sync`, and opens a shell with your repo mounted at `/workspace`.

The script accepts a few env vars:

- `CEPH_DEV_IMAGE` – image name to run (default `ceph-dev`).
- `CEPH_DEV_WORKSPACE` – host path to mount at `/workspace` (default repo root).
- `DOCKER_CMD` – override the docker binary (set to `sudo docker` if you need root).

Because the container stays up while you iterate, `uv sync` only happens the first time you launch a shell; subsequent `uv run ...` commands reuse the same environment immediately. By default `/var/lib/ceph-dev` lives inside the container (ephemeral); mount your own volume at that path if you want to reuse the same cluster state.

## Useful environment switches

| Variable | Values | Effect |
| --- | --- | --- |
| `CEPH_FEATURESET` | space-separated list of `mon osd mgr mds mds2 rbd-mirror cephfs-mirror rgw rgw2 selftest` | Select which micro-services the helper script bootstraps (default: `mon osd mgr mds rgw selftest`). |
| `CEPH_BOOTSTRAP` | `auto` (default), `always`, `never` | `auto` bootstraps only when no `.ready` marker exists under `/var/lib/ceph-dev`; `always` wipes the data dir each start; `never` requires you to persist `/var/lib/ceph-dev` (via a Docker volume) so the cluster can be reused. |
| `CEPH_RESET` | `true` / `false` | Forcefully delete the data dir before bringing the cluster up (same as `CEPH_BOOTSTRAP=always`, but explicit). |
| `CEPH_DATA_DIR` | path (default `/var/lib/ceph-dev`) | Where cluster state is stored. Mount this as a named volume to reuse OSDs between runs. |


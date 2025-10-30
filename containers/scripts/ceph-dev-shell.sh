#!/usr/bin/env bash
set -euo pipefail

DOCKER_CMD=${DOCKER_CMD:-sudo docker}
IMAGE=${CEPH_DEV_IMAGE:-ceph-dev}
WORKSPACE=${CEPH_DEV_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}

${DOCKER_CMD} run --rm -it \
  -v "${WORKSPACE}:/workspace" \
  -w /workspace \
  -e CEPH_BOOTSTRAP=always \
  -e CEPH_STATUS_ON_START=true \
  "${IMAGE}" bash -lc 'set -e; uv sync --all-packages;source .venv/bin/activate; exec "$SHELL"'

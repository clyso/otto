#!/usr/bin/env bash
set -euo pipefail

MICRO_OSD_BIN=${MICRO_OSD_BIN:-/usr/local/bin/micro-osd.sh}
DATA_DIR=${CEPH_DATA_DIR:-/var/lib/ceph-dev}
READY_FILE="${DATA_DIR}/.ready"
DEFAULT_FEATURES="mon osd mgr mds rgw selftest"
CEPH_FEATURESET="${CEPH_FEATURESET:-${DEFAULT_FEATURES}}"
CEPH_RESET="${CEPH_RESET:-false}"
CEPH_BOOTSTRAP="${CEPH_BOOTSTRAP:-auto}"
CEPH_STATUS_ON_START="${CEPH_STATUS_ON_START:-true}"

mkdir -p "${DATA_DIR}"
export CEPH_CONF="${DATA_DIR}/ceph.conf"

bootstrap_cluster() {
    if [[ "${CEPH_RESET}" == "true" ]]; then
        echo "[ceph-dev] Reset requested, wiping ${DATA_DIR}"
        rm -rf "${DATA_DIR}"
        mkdir -p "${DATA_DIR}"
    elif [[ "${CEPH_BOOTSTRAP}" == "always" ]]; then
        echo "[ceph-dev] CEPH_BOOTSTRAP=always, reinitializing ${DATA_DIR}"
        rm -rf "${DATA_DIR}"
        mkdir -p "${DATA_DIR}"
    fi

    if [[ "${CEPH_BOOTSTRAP}" == "never" ]] && [[ ! -f "${READY_FILE}" ]]; then
        echo "[ceph-dev] CEPH_BOOTSTRAP=never but no existing cluster found" >&2
        exit 1
    fi

    if [[ ! -x "${MICRO_OSD_BIN}" ]]; then
        echo "[ceph-dev] micro-osd helper not found at ${MICRO_OSD_BIN}" >&2
        exit 1
    fi

    if [[ "${CEPH_BOOTSTRAP}" != "never" ]]; then
        rm -f "${READY_FILE}"
        echo "[ceph-dev] Bootstrapping micro cluster (features: ${CEPH_FEATURESET})"
        CEPH_FEATURESET="${CEPH_FEATURESET}" "${MICRO_OSD_BIN}" "${DATA_DIR}"
    else
        echo "[ceph-dev] Reusing existing cluster state at ${DATA_DIR}"
    fi

    if [[ ! -f "${READY_FILE}" ]]; then
        echo "[ceph-dev] Cluster failed to report ready flag (${READY_FILE})" >&2
        exit 1
    fi
}

show_status() {
    if [[ "${CEPH_STATUS_ON_START}" == "true" ]]; then
        echo "[ceph-dev] ceph status"
        ceph status || true
    fi
}

bootstrap_cluster
show_status

declare -a CMD=("$@")
if [[ ${#CMD[@]} -eq 0 ]]; then
    CMD=("/bin/bash")
fi

if [[ "${CMD[0]}" == "ceph-dev" ]]; then
    case "${CMD[1]:-}" in
        shell)
            exec "/bin/bash"
            ;;
        status)
            ceph status
            exit $?
            ;;
        *)
            echo "Usage: ceph-dev [shell|status]" >&2
            exit 2
            ;;
    esac
else
    echo "[ceph-dev] Executing: ${CMD[*]}"
    exec "${CMD[@]}"
fi

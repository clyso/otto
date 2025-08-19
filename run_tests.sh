#!/bin/bash -e

repo_root="$(realpath "$(dirname "$0")")"

start_copilot_backend() {
    if ! which uvicorn >/dev/null; then
        echo "uvicorn is required for COPILOT BACKEND tests" >&2
        return
    fi

    echo "Starting COPILOT BACKEND service" >&2

    pushd copilot_backend/src/ || exit 1
    COPILOT_BACKEND_REPORTS_PATH=${DATADIR}/reports \
        COPILOT_BACKEND_ACCESS_LOG_PATH=${DATADIR}/access.log \
        PYTHONPATH="${repo_root}/copilot/src/" \
        uvicorn copilot_backend:app --port 8000 --host 127.0.0.1 \
        >${DATADIR}/uvicorn.log 2>&1 &
    PIDS="${PIDS} $!"
    popd

    for i in $(seq 20); do
        COPILOT_BACKEND_ENDPOINT=$(
            sed -nEe 's/.* running on .*(htt[^ ]*:8000).*$/\1/p' ${DATADIR}/uvicorn.log
        )
        COPILOT_VERSION=$(
            sed -nEe 's/.* REST API Server version ([0-9.]+(\+g[0-9a-f]+(\.d[0-9]+)?)?).*$/\1/p' ${DATADIR}/uvicorn.log
        )
        if [ -n "${COPILOT_BACKEND_ENDPOINT}" -a -n "${COPILOT_VERSION}" ]; then
            break
        fi
        sleep 1
    done

    echo "REST API is at ${COPILOT_BACKEND_ENDPOINT}" >&2
    echo "Server version is ${COPILOT_VERSION}" >&2

    export COPILOT_BACKEND_ENDPOINT COPILOT_VERSION
}

start_copilot_rest_api() {
    if ! which uvicorn >/dev/null; then
        echo "uvicorn is required for REST API tests" >&2
        return
    fi

    echo "Starting REST API service" >&2

    pushd copilot_rest_api/src/ || exit 1
    COPILOT_REST_API_CACHE_PATH=${DATADIR}/cache \
        COPILOT_REST_API_REPORTS_PATH=${DATADIR}/reports \
        COPILOT_REST_API_ACCESS_LOG_PATH=${DATADIR}/access.log \
        PYTHONPATH="${repo_root}/copilot/src" \
        uvicorn copilot_rest_api:app --port 8000 --host 127.0.0.1 \
        >${DATADIR}/uvicorn.log 2>&1 &
    PIDS="${PIDS} $!"
    popd || exit 1

    for i in $(seq 20); do
        COPILOT_REST_API_ENDPOINT=$(
            sed -nEe 's/.* running on .*(htt[^ ]*:8000).*$/\1/p' ${DATADIR}/uvicorn.log
        )
        COPILOT_VERSION=$(
            sed -nEe 's/.* REST API Server version ([0-9.]+(\+g[0-9a-f]+(\.d[0-9]+)?)?).*$/\1/p' ${DATADIR}/uvicorn.log
        )
        if [ -n "${COPILOT_REST_API_ENDPOINT}" -a -n "${COPILOT_VERSION}" ]; then
            break
        fi
        sleep 1
    done

    echo "REST API is at ${COPILOT_REST_API_ENDPOINT}" >&2
    echo "Server version is ${COPILOT_VERSION}" >&2

    export COPILOT_REST_API_ENDPOINT COPILOT_VERSION
}

start_copilot_netcat() {
    export COPILOT_NETCAT_HOST=localhost
    export COPILOT_NETCAT_PORT=12345
    export COPILOT_NETCAT_TIMEOUT=4
    export COPILOT_NETCAT_GZIP=True
    export COPILOT_NETCAT_WEB_URL='https://analyzer.stg.clyso.cloud/#/analyzer/ceph'

    echo "Starting Netcat service" >&2

    ./copilot_netcat/src/copilot_netcat >${DATADIR}/netcat.log 2>&1 &
    PIDS="${PIDS} $!"

    for i in $(seq 10); do
        COPILOT_NETCAT_ENDPOINT=$(
            sed -nEe 's/.* Server listening on (.*:12345).*$/\1/p' ${DATADIR}/netcat.log
        )
        test -n "${COPILOT_NETCAT_ENDPOINT}" && break
        sleep 1
    done

    echo "Netcat is at ${COPILOT_NETCAT_ENDPOINT}" >&2
}

DATADIR=/tmp/copilot.test
rm -rf ${DATADIR}
mkdir ${DATADIR}
PIDS=

start_copilot_rest_api &&
    start_copilot_netcat || :

test -n "$PIDS"
trap "kill $PIDS" INT TERM EXIT

python3 -m unittest discover tests

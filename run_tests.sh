#!/bin/bash -e

repo_root="$(realpath "$(dirname "$0")")"

DATADIR=/tmp/otto.test
rm -rf ${DATADIR}
mkdir ${DATADIR}

python3 -m unittest discover tests

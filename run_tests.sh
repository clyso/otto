#!/bin/bash -e
# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later


repo_root="$(realpath "$(dirname "$0")")"

DATADIR=/tmp/otto.test
rm -rf ${DATADIR}
mkdir ${DATADIR}

python3 -m unittest discover tests

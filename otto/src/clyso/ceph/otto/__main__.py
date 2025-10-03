# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import sys

import clyso.ceph.otto

if sys.argv[0].endswith("__main__.py"):
    import os.path

    executable = os.path.basename(sys.executable)
    sys.argv[0] = executable + " -m clyso.ceph.otto"
    del os

clyso.ceph.otto.main()

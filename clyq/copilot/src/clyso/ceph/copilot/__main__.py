# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import clyso.ceph.copilot
import sys

if sys.argv[0].endswith("__main__.py"):
    import os.path
    executable = os.path.basename(sys.executable)
    sys.argv[0] = executable + " -m clyso.ceph.copilot"
    del os

clyso.ceph.copilot.main()

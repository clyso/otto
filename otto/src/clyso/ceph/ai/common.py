# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import sys
import argparse


class OttoParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super(OttoParser, self).__init__(*args, **kwargs)

    def error(self, message):
        otto_error = "{cluster, pool, toolkit}"

        if otto_error in message:
            print(f"{message}")
            self.print_help()
            sys.exit(2)

        self.print_usage()
        print(f"otto: error: {message}")
        sys.exit(2)

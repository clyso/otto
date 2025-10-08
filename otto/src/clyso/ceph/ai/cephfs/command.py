import sys
import errno
import re
from pathlib import Path
from typing import Any

from clyso.ceph.ai.cephfs.session_top import CephfsSessionTop
from clyso.ceph.api.commands import ceph_fs_status
from clyso.ceph.api.schemas import MalformedCephDataError


class CephfsSessionTopCommand:
    """Command class that orchestrates CephFS session top workflow"""

    def __init__(self, args: Any):
        self.args = args
        self.session_top = CephfsSessionTop(args)

    def execute(self) -> None:
        """Execute the complete CephFS session-top workflow"""
        try:
            self._validate_args()
            mds_list = self._get_mds_list()

            if not mds_list:
                print("no active MDS found", file=sys.stderr)
                sys.exit(errno.ENOENT)

            for mds in mds_list:
                self.session_top.run_session_analysis(mds)

        except ValueError as e:
            print(f"Argument validation error: {e}", file=sys.stderr)
            sys.exit(errno.EINVAL)
        except FileNotFoundError as e:
            print(f"File error: {e}", file=sys.stderr)
            sys.exit(errno.ENOENT)
        except MalformedCephDataError as e:
            print(f"Ceph command error: {e}", file=sys.stderr)
            sys.exit(errno.EIO)
        except Exception as e:
            print(f"Error during CephFS session analysis: {e}", file=sys.stderr)
            sys.exit(errno.EIO)

    def _validate_args(self) -> None:
        """Validate all argument combinations and regex patterns"""
        if self.args.group_by_host and self.args.group_by_root:
            raise ValueError(
                "--group-by-host and --group-by-root cannot be specified together"
            )

        if (
            self.args.sort_by.lower() == "count"
            and not self.args.group_by_host
            and not self.args.group_by_root
        ):
            raise ValueError("sort by count is only valid with --group-by options")

        if self.args.filter_by_host_regexp:
            try:
                re.compile(self.args.filter_by_host_regexp)
            except re.error as e:
                raise ValueError(f"invalid filter-by-host-regexp: {e}")

        if self.args.filter_by_root_regexp:
            try:
                re.compile(self.args.filter_by_root_regexp)
            except re.error as e:
                raise ValueError(f"invalid filter-by-root-regexp: {e}")

        if self.args.file:
            if self.args.mds or self.args.fs:
                raise ValueError("File and --mds/--fs cannot be specified together")

        elif self.args.mds and self.args.fs:
            raise ValueError("Either --mds or --fs can be specified, not both")

    def _get_mds_list(self) -> list[dict[str, Any]]:
        """Get list of MDS daemons to analyze"""
        mds_list = []

        if self.args.file:
            for f in self.args.file:
                if f != "-":
                    file_path = Path(f)
                    if not file_path.exists():
                        raise FileNotFoundError(f"file not found: {f}")
                mds_list.append({"file": f})

        else:
            fs_status = ceph_fs_status(
                fs_name=self.args.fs, skip_confirmation=getattr(self.args, "yes", True)
            )

            for mds_entry in fs_status.mdsmap:
                mds_dict = mds_entry.model_dump()

                if self.args.mds:
                    if mds_dict.get("name") == self.args.mds:
                        mds_list.append(mds_dict)
                        break
                    continue
                if mds_dict.get("state") == "active":
                    mds_list.append(mds_dict)

        return mds_list

# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import re
import sys
from typing import Any, Optional

from clyso.ceph.api.commands import ceph_mds_session_ls
from clyso.ceph.api.schemas import (
    CephfsSession,
    CephfsSessionMetricValue,
    MalformedCephDataError,
    CephfsMDSMapEntry,
)
from pydantic import BaseModel, Field
from pathlib import Path


class GroupedSession(BaseModel):
    """Schema for grouped CephFS sessions"""

    count: int = Field(default=0)
    request_load_avg: float = Field(default=0.0)
    num_caps: int = Field(default=0)
    recall_caps: CephfsSessionMetricValue = Field(
        default_factory=CephfsSessionMetricValue
    )
    release_caps: CephfsSessionMetricValue = Field(
        default_factory=CephfsSessionMetricValue
    )
    session_cache_liveness: CephfsSessionMetricValue = Field(
        default_factory=CephfsSessionMetricValue
    )
    cap_acquisition: CephfsSessionMetricValue = Field(
        default_factory=CephfsSessionMetricValue
    )

    hostname: Optional[str] = Field(default=None)
    root: Optional[str] = Field(default=None)


class CephfsSessionTop:
    """Main class for CephFS session top analysis"""

    def __init__(self, args: Any):
        self.args = args
        self.filter_by_host_regexp = self._compile_regex(args.filter_by_host_regexp)
        self.filter_by_root_regexp = self._compile_regex(args.filter_by_root_regexp)

    def _compile_regex(self, pattern: Optional[str]) -> Optional[re.Pattern]:
        """Compile regex pattern (validation already done in command layer)"""
        return re.compile(pattern) if pattern else None

    def run_session_analysis(self, mds: CephfsMDSMapEntry) -> None:
        """Run complete session analysis for a single MDS"""
        sessions = self._load_sessions(mds)
        self._print_mds_info(mds, len(sessions))
        if not sessions:
            return
        processed_sessions = self._process_sessions(sessions)
        self._display_sessions(processed_sessions)

    def _load_sessions(self, mds: CephfsMDSMapEntry) -> list[CephfsSession]:
        """Load session data from file or MDS"""
        if mds.file:
            return self._load_from_file(mds.file)
        else:
            return self._load_from_mds(mds.name)

    def _load_from_file(self, file_path: str) -> list[CephfsSession]:
        """Load sessions from a JSON file"""
        if file_path == "-":
            raw_data = json.load(sys.stdin)
        else:
            file_path = Path(file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"file not found: {file_path}")
            raw_data = json.loads(file_path.read_text())

        return [CephfsSession.model_validate(session_data) for session_data in raw_data]

    def _load_from_mds(self, mds_name: str) -> list[CephfsSession]:
        """Load sessions from MDS daemon via ceph command"""
        try:
            session_response = ceph_mds_session_ls(mds_name)
            return list(session_response)
        except MalformedCephDataError as e:
            raise RuntimeError(f"Failed to get sessions from mds.{mds_name}: {e}")

    def _print_mds_info(self, mds: CephfsMDSMapEntry, session_count: int) -> None:
        """Print MDS information header"""
        if mds.file:
            print(f"File: {Path(mds.file).name}")
        else:
            print(f"MDS: {mds.name}")
            print(f"Rank: {mds.rank}")

        print(f"Client Sessions: {session_count}")
        print()

    def _process_sessions(
        self, sessions: list[CephfsSession]
    ) -> list[CephfsSession | GroupedSession]:
        """Process sessions through filtering, grouping, sorting, and limiting"""
        filtered_sessions = self._apply_filters(sessions)
        grouped_sessions = self._apply_grouping(filtered_sessions)
        sorted_sessions = self._apply_sorting(grouped_sessions)

        if self.args.top:
            sorted_sessions = sorted_sessions[: self.args.top]

        return sorted_sessions

    def _apply_filters(self, sessions: list[CephfsSession]) -> list[CephfsSession]:
        """Apply all configured filters to the session list"""
        filtered_sessions = sessions

        if self.args.filter_by_host:
            filtered_sessions = [
                s
                for s in filtered_sessions
                if s.client_metadata.hostname == self.args.filter_by_host
            ]

        if self.filter_by_host_regexp:
            filtered_sessions = [
                s
                for s in filtered_sessions
                if self.filter_by_host_regexp.search(s.client_metadata.hostname)
            ]

        if self.args.filter_by_root:
            filtered_sessions = [
                s
                for s in filtered_sessions
                if s.client_metadata.root == self.args.filter_by_root
            ]

        if self.filter_by_root_regexp:
            filtered_sessions = [
                s
                for s in filtered_sessions
                if self.filter_by_root_regexp.search(s.client_metadata.root)
            ]

        return filtered_sessions

    def _apply_grouping(
        self, sessions: list[CephfsSession]
    ) -> list[CephfsSession | GroupedSession]:
        """Apply grouping if requested"""
        if self.args.group_by_host:
            return self._group_by_host(sessions)
        elif self.args.group_by_root:
            return self._group_by_root(sessions)
        else:
            return sessions

    def _group_by_host(self, sessions: list[CephfsSession]) -> list[GroupedSession]:
        """Group sessions by hostname"""
        groups = {}
        for session in sessions:
            host = session.client_metadata.hostname or "--"
            if host not in groups:
                groups[host] = []
            groups[host].append(session)

        return [
            self._create_grouped_session(group, hostname=host)
            for host, group in groups.items()
        ]

    def _group_by_root(self, sessions: list[CephfsSession]) -> list[GroupedSession]:
        """Group sessions by root directory"""
        groups = {}
        for session in sessions:
            root = session.client_metadata.root or "--"
            if root not in groups:
                groups[root] = []
            groups[root].append(session)

        return [
            self._create_grouped_session(group, root=root)
            for root, group in groups.items()
        ]

    def _create_grouped_session(
        self, group: list[CephfsSession], **extra_fields
    ) -> GroupedSession:
        """Create an aggregated session from a group of sessions"""
        total_request_load_avg = sum(s.request_load_avg for s in group)
        total_num_caps = sum(s.num_caps for s in group)
        total_recall_caps = sum(s.recall_caps.value for s in group)
        total_release_caps = sum(s.release_caps.value for s in group)
        total_liveness = sum(s.session_cache_liveness.value for s in group)
        total_cap_acquisition = sum(s.cap_acquisition.value for s in group)

        return GroupedSession(
            count=len(group),
            request_load_avg=total_request_load_avg,
            num_caps=total_num_caps,
            recall_caps=CephfsSessionMetricValue(value=total_recall_caps),
            release_caps=CephfsSessionMetricValue(value=total_release_caps),
            session_cache_liveness=CephfsSessionMetricValue(value=total_liveness),
            cap_acquisition=CephfsSessionMetricValue(value=total_cap_acquisition),
            **extra_fields,
        )

    def _apply_sorting(
        self, sessions: list[CephfsSession | GroupedSession]
    ) -> list[CephfsSession | GroupedSession]:
        """Sort sessions by the specified field"""
        sort_key = self.args.sort_by.lower()

        if sort_key == "loadavg":
            sessions.sort(key=lambda s: s.request_load_avg, reverse=True)
        elif sort_key == "numcaps":
            sessions.sort(key=lambda s: s.num_caps, reverse=True)
        elif sort_key == "reccaps":
            sessions.sort(key=lambda s: s.recall_caps.value, reverse=True)
        elif sort_key == "relcaps":
            sessions.sort(key=lambda s: s.release_caps.value, reverse=True)
        elif sort_key == "liveness":
            sessions.sort(key=lambda s: s.session_cache_liveness.value, reverse=True)
        elif sort_key == "capacqu":
            sessions.sort(key=lambda s: s.cap_acquisition.value, reverse=True)
        elif sort_key == "host":
            sessions.sort(key=lambda s: self._get_hostname(s))
        elif sort_key == "root":
            sessions.sort(key=lambda s: self._get_root(s))
        elif sort_key == "count":
            sessions.sort(key=lambda s: getattr(s, "count", 0), reverse=True)
        else:
            raise ValueError(f"invalid sort_by: {self.args.sort_by}")

        return sessions

    def _get_hostname(self, session: CephfsSession | GroupedSession) -> str:
        """Get hostname from session"""
        if isinstance(session, GroupedSession):
            return session.hostname or "--"
        else:
            return session.client_metadata.hostname or "--"

    def _get_root(self, session: CephfsSession | GroupedSession) -> str:
        """Get root from session"""
        if isinstance(session, GroupedSession):
            return session.root or "--"
        else:
            return session.client_metadata.root or "--"

    def _display_sessions(self, sessions: list[CephfsSession | GroupedSession]) -> None:
        """Display the processed sessions"""
        print("LOADAVG NUMCAPS RECCAPS RELCAPS LIVENESS CAPACQU", end=" ")
        if self.args.group_by_host:
            print("COUNT HOST")
        elif self.args.group_by_root:
            print("COUNT ROOT")
        else:
            print("CLIENT")

        for session in sessions:
            print(
                f"{session.request_load_avg:7} "
                f"{session.num_caps:7} "
                f"{int(session.recall_caps.value):7} "
                f"{int(session.release_caps.value):7} "
                f"{int(session.session_cache_liveness.value):8} "
                f"{int(session.cap_acquisition.value):7} ",
                end="",
            )

            if isinstance(session, GroupedSession):
                if self.args.group_by_host:
                    print(f"{session.count:5} {session.hostname}")
                elif self.args.group_by_root:
                    print(f"{session.count:5} {session.root}")
            else:
                hostname = session.client_metadata.hostname or "--"
                root = session.client_metadata.root or "--"
                print(f"{session.session_id} {hostname}:{root}")

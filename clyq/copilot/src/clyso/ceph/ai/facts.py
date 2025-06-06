# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

# Ceph Copilot - Facts extraction models
# Copyright (C) 2025 Clyso. All rights reserved.

# NOTE: basedpyright has issues with stub files in this environment
# Disable issues related to missing builtins and stubs, but keep meaningful type checking
#
# pyright: reportAny=false
# pyright: reportExplicitAny=false
# pyright: reportMissingTypeStubs=false

from __future__ import annotations

from typing import Any
import builtins

from clyso.ceph.ai.helpers import to_version, to_major, to_release


class ConfigItem:
    """Represents a single configuration item from ceph config dump"""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__()
        self.section: str = data.get("section", "")
        self.name: str = data.get("name", "")
        self.value: str = data.get("value", "")
        self.level: str = data.get("level", "")
        self.can_update_at_runtime: bool = data.get("can_update_at_runtime", False)
        self.mask: str = data.get("mask", "")
        self.location_type: str = data.get("location_type", "")
        self.location_value: str = data.get("location_value", "")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from this config item"""
        return builtins.getattr(self, key, default)


class CephFacts:
    """
    Extracts and caches commonly needed cluster information from CephData.
    """

    def __init__(self, ceph_data: Any) -> None:
        super().__init__()
        self.ceph_data: Any = ceph_data

        # Initialize all attributes with defaults
        self.version: str = "unknown"
        self.major_version: str = "unknown"
        self.release_name: str = "unknown"
        self.num_osds: int = 0
        self.num_pools: int = 0
        self.num_mons: int = 0
        self.cluster_id: str = "unknown"
        self.cluster_name: str = "ceph"
        self.deployment_type: str = "unknown"
        self.has_separate_cluster_network: bool = False

        self._extract_facts()

    def _extract_facts(self) -> None:
        """Extract all facts from the ceph data"""
        if (
            builtins.hasattr(self.ceph_data, "ceph_report")
            and self.ceph_data.ceph_report
        ):
            self._extract_from_report()
        else:
            self._set_defaults()

    def _extract_from_report(self) -> None:
        """Extract facts from ceph report"""
        report: Any = self.ceph_data.ceph_report

        self.version = to_version(report.get("version", "unknown"))
        self.major_version = to_major(self.version)
        self.release_name = to_release(self.major_version)

        osdmap: dict[str, Any] = report.get("osdmap", {})
        self.num_osds = builtins.len(osdmap.get("osds", []))
        self.num_pools = builtins.len(osdmap.get("pools", []))

        monmap: dict[str, Any] = report.get("monmap", {})
        self.num_mons = builtins.len(monmap.get("mons", []))

        self.cluster_id = monmap.get("fsid", "unknown")

        self.deployment_type = self._detect_deployment_type()

        self.has_separate_cluster_network = self._check_separate_cluster_network()

    def _set_defaults(self) -> None:
        """Set default values when report is not available"""
        self.version = "unknown"
        self.major_version = "unknown"
        self.release_name = "unknown"
        self.num_osds = 0
        self.num_pools = 0
        self.num_mons = 0
        self.cluster_id = "unknown"
        self.cluster_name = "ceph"
        self.deployment_type = "unknown"
        self.has_separate_cluster_network = False

    def _detect_deployment_type(self) -> str:
        """Detect if using cephadm (container) deployment"""
        if (
            not builtins.hasattr(self.ceph_data, "ceph_report")
            or not self.ceph_data.ceph_report
        ):
            return "unknown"

        osd_metadata: list[dict[str, Any]] = self.ceph_data.ceph_report.get(
            "osd_metadata", []
        )
        for osd in osd_metadata:
            if "container_image" in osd:
                return "cephadm"
        return "traditional"

    def _check_separate_cluster_network(self) -> bool:
        """Check if cluster has separate public and cluster networks"""
        if (
            not builtins.hasattr(self.ceph_data, "ceph_report")
            or not self.ceph_data.ceph_report
        ):
            return False

        osdmap: dict[str, Any] = self.ceph_data.ceph_report.get("osdmap", {})
        osds: list[dict[str, Any]] = osdmap.get("osds", [])
        if not osds:
            return False

        first_osd: dict[str, Any] = osds[0]
        public_ip: str = first_osd.get("public_addr", "").split(":")[0]
        cluster_ip: str = first_osd.get("cluster_addr", "").split(":")[0]
        return public_ip != cluster_ip


class ConfigLookup:
    """
    Provides easy lookup functionality for Ceph configuration values.
    """

    def __init__(self, config_dump: list[dict[str, Any]] | None) -> None:
        super().__init__()
        self.config_dump: list[dict[str, Any]] = config_dump if config_dump else []

        # Initialize lookup structures
        self.config_map: dict[tuple[str, str], dict[str, Any]] = {}
        self.by_section: dict[str, dict[str, dict[str, Any]]] = {}
        self.by_name: dict[str, list[dict[str, Any]]] = {}

        self._build_lookup_structures()

    def _build_lookup_structures(self) -> None:
        """Build efficient lookup structures from config dump"""
        # Dictionary for quick lookups: {(section, name): config_item}
        self.config_map = {}

        # Dictionary by section: {section: {name: config_item}}
        self.by_section = {}

        # Dictionary by name only: {name: [config_items]}
        self.by_name = {}

        for config_item in self.config_dump:
            section: str = builtins.str(config_item.get("section", ""))
            name: str = builtins.str(config_item.get("name", ""))

            # Full lookup
            key: tuple[str, str] = (section, name)
            self.config_map[key] = config_item

            # By section
            if section not in self.by_section:
                self.by_section[section] = {}
            self.by_section[section][name] = config_item

            # By name (may have multiple entries for different sections)
            if name not in self.by_name:
                self.by_name[name] = []
            self.by_name[name].append(config_item)

    def get_config(
        self, name: str, section: str | None = None
    ) -> dict[str, Any] | None:
        """
        Get configuration value by name and optionally section.

        Args:
            name: Configuration name
            section: Optional section (if None, searches all sections)

        Returns:
            Configuration item dict or None if not found
        """
        if section:
            return self.config_map.get((section, name))
        else:
            # Return first match if no section specified
            configs: list[dict[str, Any]] = self.by_name.get(name, [])
            return configs[0] if configs else None

    def get_config_value(
        self, name: str, section: str | None = None, default: Any = None
    ) -> Any:
        """Get just the value of a configuration setting"""
        config: dict[str, Any] | None = self.get_config(name, section)
        return config.get("value") if config else default

    def has_config(self, name: str, section: str | None = None) -> bool:
        """Check if a configuration exists"""
        return self.get_config(name, section) is not None

    def get_section_configs(self, section: str) -> dict[str, dict[str, Any]]:
        """Get all configurations for a specific section"""
        return self.by_section.get(section, {})

    def get_all_configs_by_name(self, name: str) -> list[dict[str, Any]]:
        """Get all configuration items with the given name (across all sections)"""
        return self.by_name.get(name, [])

    def is_config_set_to(
        self, name: str, expected_value: Any, section: str | None = None
    ) -> bool:
        """Check if a configuration is set to a specific value"""
        actual_value: Any = self.get_config_value(name, section)
        return actual_value == expected_value

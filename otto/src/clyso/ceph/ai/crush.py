# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

from clyso.ceph.api.schemas import CrushMap, CrushRule


class Crush(object):
    """
    Crush class to get crush settings.
    """

    def __init__(self, crushmap: CrushMap):
        self.crushmap = crushmap

    def get_rule_by_id(self, rule_id) -> CrushRule | None:
        """
        Get crush rule by rule id.
        """
        for rule in self.crushmap.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def get_rule_by_name(self, rule_name) -> CrushRule | None:
        """
        Get crush rule by rule name.
        """
        for rule in self.crushmap.rules:
            if rule.rule_name == rule_name:
                return rule
        return None

    def get_rule_failure_domain(self, rule_id):
        """
        Get crush rule failure domain by rule id.
        """
        rule = self.get_rule_by_id(rule_id)
        if not rule:
            return None

        failure_domain = None
        for step in rule.steps:
            if step.op.startswith("choose"):
                failure_domain = step.rule_type
        return failure_domain

    def get_rule_root(self, rule_name):
        """
        Get crush rule root by rule name.
        """
        rule = self.get_rule_by_name(rule_name)
        if not rule:
            return None
        for step in rule.steps:
            if step.op == "take":
                root_name = step.item_name
                for item in self.crushmap.buckets:
                    if item.name == root_name:
                        return item.bucket_id
        return None

    def get_osds_under(self, root_id):
        """
        Get osds under root.
        """
        osds = []
        for item in self.crushmap.buckets:
            if item.bucket_id != root_id:
                continue
            for sub_item in item.items:
                if sub_item.item_id < 0:
                    osds += self.get_osds_under(sub_item.item_id)
                else:
                    osds.append(sub_item.item_id)
        return osds

    def get_items_of_type_under(self, item_type, root_id):
        """
        Get items of specified type under root.
        """
        items = []
        for item in self.crushmap.buckets:
            if item.bucket_id != root_id:
                continue
            if item.type_name == item_type:
                items.append(item.bucket_id)
                break
            for sub_item in item.items:
                if sub_item.item_id >= 0:
                    if item_type == "osd":
                        items.append(sub_item.item_id)
                else:
                    items += self.get_items_of_type_under(item_type, sub_item.item_id)
            break

        return items

    def get_zero_weight_buckets_under(self, root_id):
        """
        Get zero weight buckets under root.
        """
        items = []
        for item in self.crushmap.buckets:
            if item.bucket_id != root_id:
                continue
            if item.weight == 0:
                items.append(item.bucket_id)
                break
            for sub_item in item.items:
                if sub_item.item_id < 0:
                    items += self.get_zero_weight_buckets_under(sub_item.item_id)
            break

        return items

    def get_item_weight(self, item_id):
        """
        Get bucket weight.
        """
        for item in self.crushmap.buckets:
            if item_id < 0 and item.bucket_id == item_id:
                return item.weight
            for sub_item in item.items:
                if sub_item.item_id == item_id:
                    return sub_item.weight
        return 0

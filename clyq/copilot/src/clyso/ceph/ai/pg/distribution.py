# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later


from clyso.ceph.ai.data import CephData
from clyso.ceph.ai.pg.histogram import histogram, DataPoint
from collections import defaultdict

class PGHistogram:
    def __init__(self,osd_tree: dict,pg_dump: dict, flags):
        self.data = CephData()
        self.data.add_ceph_osd_tree(osd_tree)
        self.data.add_ceph_pg_dump(pg_dump) 
        self.flags = flags
        
        
        # interface
        self.osd_weights = self.get_weights()
        self.osds = self.get_pg_stats() 
        
        
        if self.flags.normalize:
            values = [DataPoint(self.osds[osd] / self.osd_weights[osd]['crush_weight'], 1) for osd in self.osds]
        else:
            values = [DataPoint(self.osds[osd], 1) for osd in self.osds]
            
        histogram(values,self.flags)
 
    def get_weights(self):
        
        osd_weights = dict()
        # https://github.com/cernceph/ceph-scripts/blob/master/tools/ceph-pg-histogram
        for osd in self.data.ceph_osd_tree['nodes']:
            if osd['type'] == 'osd':
                osd_id = osd['id']
                reweight = float(osd['reweight'])
                crush_weight = float(osd['crush_weight'])
                osd_weights[osd_id] = dict()
                osd_weights[osd_id]['crush_weight'] = crush_weight
                osd_weights[osd_id]['reweight'] = reweight

        # print(osd_weights)
        return osd_weights
    
    def get_pg_stats(self):
        pg_data = self.data.ceph_pg_dump['pg_map'] if 'pg_map' in self.data.ceph_pg_dump else self.data.ceph_pg_dump
        ceph_pg_stats = pg_data['pg_stats']   
        osds = defaultdict(int)
        for pg in ceph_pg_stats:
            poolid = pg['pgid'].split('.')[0]
            if self.flags.pools and poolid not in self.flags.pools:
                continue
            for osd in pg['acting']:
                if osd >= 0 and osd < 1000000:
                    osds[osd] += 1
        
        return osds

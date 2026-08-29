# otto

otto is a CLI tool for analyzing and managing Ceph clusters.
You can think of Otto as your personal Dr. Octopus for Ceph.

## Installation

Download the latest binary:

```bash
curl -O  https://s3.clyso.com/otto/latest/otto
chmod +x otto
```

Binary releases are also available at https://github.com/clyso/otto/releases

Releases are also available per tag:

```bash
curl -O  https://s3.clyso.com/otto/<RELEASE_TAG>/otto
```

For more information on how this gets built see the [Development Guide - Binary Compatability](docs/dev.md#binary)

## Usage

### Analyze cluster health

```bash
ceph report > report.json
otto checkup --ceph_report_json=report.json
```

Example output:

```
Running tests: .!XX...X.!!.....X..............!X..

Overall score: 28 out of 35 (F)

- WARN in Version/Major Release: Not running the recommended major release quincy v17
- FAIL in Version/Minor Release: Not running the recommended minor bugfix release for pacific
- FAIL in Version/Check for Known Issues in Running Version: CRITICAL: Found 1 high severity bugs(s) in running version 16.2.10
- FAIL in Pools/Recommended Flags: Some pools have missing flags
- WARN in Pools/Pool Autoscale Mode: pg_autoscaler is on which may cause unexpected data movement
- WARN in Pools/RBD Pools: Too many RBD pools
- FAIL in Pools/Pool Space Amplification: Some pools have high space amplification
- WARN in OSD Health/OSD host swap: All OSD hosts have swap enabled
- FAIL in OSD Health/Check number of osdmaps stored: Cluster has too many osdmaps (185437)

Use --verbose or --summary for details and recommendations
```

### Machine-readable output

For cron, CI, or monitoring, emit the full result document as JSON:

```bash
otto cluster checkup --ceph_report_json=report.json --format json
```

`--format json` writes the complete result to stdout (warnings go to stderr, so
stdout stays valid JSON). The document has the shape
`{"summary": {...}, "sections": [...]}`.

### Monitoring integration

If you already run Prometheus + node_exporter on your Ceph hosts (the standard
monitoring stack), `--format prometheus` emits the checkup result in Prometheus
text exposition format, ready for node_exporter's
[textfile collector](https://github.com/prometheus/node_exporter#textfile-collector).
Point a cron job at the collector directory and checkup regressions show up in
your existing dashboards and alerts:

```bash
# /etc/cron.d/otto-checkup — refresh metrics every 15 minutes
*/15 * * * * root otto cluster checkup --format prometheus > /var/lib/node_exporter/otto.prom.$$ && mv /var/lib/node_exporter/otto.prom.$$ /var/lib/node_exporter/otto.prom
```

The write-then-rename keeps node_exporter from ever reading a half-written file.
Metrics exported: `otto_checkup_score`, `otto_checkup_max_score`,
`otto_checkup_section_score{section=...}`, and
`otto_checkup_check_status{section=...,check=...}` (0=PASS, 1=WARN, 2=UNKNOWN,
3=FAIL).

## Requirements

- Python 3.11+
- Access to Ceph cluster commands such as 'ceph status'

## Documentation

- [Development Guide](docs/dev.md)

## Support

[Open an issue](https://github.com/clyso/dr.otto/issues)

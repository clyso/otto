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
otto cluster checkup --ceph_report_json=report.json
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

## Requirements

- Python 3.11+
- Access to Ceph cluster commands such as 'ceph status'

## Documentation

- [Development Guide](docs/dev.md)

## Support

[Open an issue](https://github.com/clyso/dr.otto/issues)

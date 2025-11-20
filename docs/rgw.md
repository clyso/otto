# RGW Operations Guide

Otto provides several subcommands for performing RGW operations and analysis.

## Prerequisites

- Access to a Ceph cluster with RGW configured
- `radosgw-admin` command available
- Appropriate permissions to query RGW data

## Commands

### Find Missing RADOS Objects

Search for RGW objects that are missing their underlying RADOS objects in the data pool. This is useful for detecting data corruption or incomplete uploads.

```bash
otto rgw find-missing [data_pool]
```

**Options:**
- `-b, --bucket`: Specify bucket name(s) to check (default: all buckets)
- `-w, --workers N`: Number of workers (default: 64)
- `-m, --max-concurrent-ios N`: Max concurrent IOs for bucket radoslist (default: 512)
- `-s, --status-output FILE`: Status output file (default: stderr)
- `-d, --processed-buckets-db FILE`: Processed buckets database file
- `-c, --corrupted-objects NAME`: Store corrupted objects list in bucket object
- `-f, --fix`: Recreate missing RADOS objects (filled with zeros)
- `-i, --fix-bucket-index`: Fix bucket index
- `-n, --dry-run`: Show what would be done without making changes

**Example:**

```bash
otto rgw find-missing default.rgw.buckets.data
```

**Sample Output:**

```
2025-11-20 22:09:45 Processing 6 buckets on pools ['default.rgw.buckets.data'] with 64 workers
2025-11-20 22:09:45 Listing bucket test-bucket-3
2025-11-20 22:09:45 100 objects in bucket test-bucket-3
2025-11-20 22:09:45 Discovering rados objects for test-bucket-3
2025-11-20 22:09:45 Found 111 rados objects for test-bucket-3
2025-11-20 22:09:45 Processing bucket: 1/6, objects processed: 111, rate: 145.739 obj/s
2025-11-20 22:09:45 Listing bucket test-bucket-1
2025-11-20 22:09:46 100 objects in bucket test-bucket-1
2025-11-20 22:09:46 Discovering rados objects for test-bucket-1
2025-11-20 22:09:46 Found 112 rados objects for test-bucket-1
2025-11-20 22:09:46 Processing bucket: 2/6, objects processed: 223, rate: 167.784 obj/s
2025-11-20 22:09:46 Listing bucket test-bucket-4
2025-11-20 22:09:46 100 objects in bucket test-bucket-4
2025-11-20 22:09:46 Discovering rados objects for test-bucket-4
2025-11-20 22:09:47 Found 111 rados objects for test-bucket-4
2025-11-20 22:09:47 Processing bucket: 3/6, objects processed: 334, rate: 186.025 obj/s
2025-11-20 22:09:47 Listing bucket test-bucket-2
2025-11-20 22:09:47 100 objects in bucket test-bucket-2
2025-11-20 22:09:47 Discovering rados objects for test-bucket-2
2025-11-20 22:09:47 Found 107 rados objects for test-bucket-2
2025-11-20 22:09:47 Processing bucket: 4/6, objects processed: 441, rate: 172.54 obj/s
2025-11-20 22:09:47 Listing bucket test-bucket-5
2025-11-20 22:09:48 100 objects in bucket test-bucket-5
2025-11-20 22:09:48 Discovering rados objects for test-bucket-5
2025-11-20 22:09:48 Found 110 rados objects for test-bucket-5
2025-11-20 22:09:48 Processing bucket: 5/6, objects processed: 551, rate: 168.58 obj/s
2025-11-20 22:09:48 Listing bucket sam-test
2025-11-20 22:09:48 1 objects in bucket sam-test
2025-11-20 22:09:48 Discovering rados objects for sam-test
2025-11-20 22:09:49 Found 1 rados objects for sam-test
2025-11-20 22:09:49 Processing bucket: 6/6, objects processed: 552, rate: 1.57158 obj/s
```

The command reports progress for each bucket, showing:
- Number of objects in each bucket
- Number of RADOS objects discovered
- Processing rate in objects per second


### User Disk Usage (user-df)

Calculate accurate disk usage for RGW users, accounting for replication factor or erasure coding overhead. This provides a more accurate view of actual disk consumption compared to logical object sizes.

```bash
otto rgw user-df <user_id> [user_id...]
```

**Options:**
- `-v, --verbose`: Enable verbose output
- `-o, --process-objects`: Get stats from listing objects as well as bucket stats

**Example:**

```bash
otto rgw user-df samtest
```

**Sample Output:**

```
User: samtest
  Pool: default.rgw.buckets.data (hdd)
    Bytes: 663996460 (stored 1991989380)
    Num objects: 501
```

The output shows:
- **User**: RGW user ID
- **Pool**: Data pool name and device class (e.g., hdd, ssd)
- **Bytes**: Logical size (stored size accounting for replication/EC)
- **Num objects**: Total number of objects

The "stored" value reflects the actual disk space used after applying the replication factor or erasure coding overhead.


### User Quota Information

Display quota settings for all RGW users, showing both bucket-level and user-level quotas.

```bash
otto rgw user-quota
```

**Options:**
- `-v, --verbose`: Enable verbose output
- `-f, --format FORMAT`: Output format: `plain`, `json`, or `json-pretty` (default: plain)

**Example:**

```bash
otto rgw user-quota
```

**Sample Output (plain format):**

```
  User ID     Bucket [size objects]   User [size objects]
-----------------------------------------------------------
  dashboard             --                     --
  samtest               --                     --
```

The output shows:
- **--**: Quota not enabled
- **Size and object limits**: When enabled, shows maximum size (in human-readable format) and maximum number of objects
- **unlimited**: When quota is enabled but no specific limit is set


### Incomplete Multipart Uploads

List incomplete multipart uploads in RGW buckets. Multipart uploads that were started but never completed can consume storage space unnecessarily.

```bash
otto rgw incomplete-multipart-list [bucket...]
```

**Options:**
- `-v, --verbose`: Enable verbose output
- `-f, --format FORMAT`: Output format: `plain`, `json`, or `json-pretty` (default: plain)
- `-r, --rados-objects`: Include RADOS objects in the output

**Example:**

```bash
otto rgw incomplete-multipart-list sam-test
```

**Sample Output:**

When no incomplete multipart uploads are found, the command produces no output.

The command identifies:
- Incomplete multipart upload IDs
- Original object names
- Individual part names
- Underlying RADOS objects (with `-r` flag)

This information can help identify stale uploads that should be cleaned up to reclaim storage space.


## Common Use Cases

**Check user storage consumption:**
```bash
otto rgw user-df user1 user2 user3
```

**Audit all user quotas:**
```bash
otto rgw user-quota --format=json > quotas.json
```

**Find incomplete uploads across all buckets:**
```bash
otto rgw incomplete-multipart-list
```

**Verify data integrity for specific buckets:**
```bash
otto rgw find-missing -b bucket -- default.rgw.buckets.data
```

**Dry-run fix for missing objects:**
```bash
otto rgw find-missing -b my-bucket --dry-run --fix
```


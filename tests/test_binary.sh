#!/bin/bash
# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

set -e

# Colors for output
GREEN='[0;32m'
RED='[0;31m'
YELLOW='[0;33m'
NC='[0m' # No Color

echo "===== Testing otto binary ====="

run_test() {
  local cmd="$1"
  local description="$2"

  echo -e "
>>> Testing: $description"
  echo -e ">>> Command: ${YELLOW}$cmd${NC}"

  # Run the command and capture output
  OUTPUT=$(bash -c "$cmd" 2>&1)
  EXIT_CODE=$?

  if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}PASS${NC}: $description"
    return 0
  else
    echo -e "${RED}FAIL${NC}: $description (Exit code: $EXIT_CODE)"
    echo -e "${RED}Command output:${NC}"
    echo "$OUTPUT"
    return 1
  fi
}

if [ ! -f "dist/otto" ]; then
  echo -e "${RED}ERROR${NC}: otto binary not found in dist/ directory"
  exit 1
fi

FAILURES=0

run_test "./dist/otto --version" "Version command" || ((FAILURES++))
run_test "./dist/otto --help" "Help command" || ((FAILURES++))

run_test "./dist/otto pools -h" "Pools help command" || ((FAILURES++))
run_test "./dist/otto pools pg -h" "Pools pg help command" || ((FAILURES++))

run_test "./dist/otto toolkit -h" "Toolkit help command" || ((FAILURES++))
run_test "./dist/otto toolkit list" "Toolkit list command" || ((FAILURES++))

run_test "./dist/otto cluster -h" "Cluster help command" || ((FAILURES++))
run_test "./dist/otto cluster upmap -h" "Cluster upmap help command" || ((FAILURES++))
run_test "./dist/otto cluster checkup -h" "Cluster checkup help command" || ((FAILURES++))

if [ -d "tests/reports" ]; then
  echo -e "
>>> Testing with report files from tests/reports/"

  REPORT_COUNT=$(find tests/reports -type f -name "*.json" | wc -l)

  if [ "$REPORT_COUNT" -gt 0 ]; then
    echo -e "Found ${GREEN}$REPORT_COUNT${NC} report files to test"

    for report_file in tests/reports/*.json; do
      if [ -f "$report_file" ]; then
        file_name=$(basename "$report_file")
        run_test "./dist/otto cluster checkup --ceph_report_json $report_file" "Cluster checkup with report $file_name" || ((FAILURES++))
      fi
    done
  else
    echo -e "${YELLOW}Warning${NC}: No .json report files found in tests/reports/"
  fi
else
  echo -e "${YELLOW}Warning${NC}: tests/reports directory not found"
fi

run_test "./dist/otto cluster checkup --ceph_report_json tests/reports/01.json --ceph-config-dump tests/configs/ceph_cluster_info-config_dump.json" "Cluster checkup with report and config dump" || ((FAILURES++))
run_test "./dist/otto cluster osd-perf -f tests/osd-perf-dump.json" "OSD perf analysis command" || ((FAILURES++))

# Summary
echo -e "
===== Test Summary ====="
if [ "$FAILURES" -eq 0 ]; then
  echo -e "${GREEN}All tests passed!${NC}"
  exit 0
else
  echo -e "${RED}$FAILURES test(s) failed!${NC}"
  exit 1
fi

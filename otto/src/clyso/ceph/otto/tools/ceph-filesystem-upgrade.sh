#!/usr/bin/env bash
#
# ceph-filesystem-upgrade.sh
#
# Upgrade the MDS daemons of a single CephFS filesystem without disturbing the
# others, working around the cephadm limitation where
#   ceph orch upgrade ... --services mds.<fs>
# prepares (fails / scales down) ALL filesystems instead of only the targeted one.
#
# Argument-driven by default; pass --interactive for a guided prompt flow.
#
# Requires: ceph, jq. Run from a host with an admin keyring.

set -euo pipefail

CEPH="${CEPH:-ceph}"
REDEPLOY_TIMEOUT="${REDEPLOY_TIMEOUT:-600}"   # seconds to wait for an MDS to come back
POLL_INTERVAL="${POLL_INTERVAL:-5}"           # seconds between status polls

PROG="$(basename "$0")"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo ">>> $*"; }
warn() { echo "WARNING: $*" >&2; }

require() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not found in PATH"; }

# returns 0 if $1 is a strictly older version than $2 (numeric, sort -V)
ver_lt() {
    [[ "$1" != "$2" ]] && \
    [[ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" == "$1" ]]
}

# cached `orch ps` snapshot of all MDS daemons
MDS_PS_JSON=""
refresh_mds_ps() { MDS_PS_JSON="$($CEPH orch ps --daemon_type mds --format json 2>/dev/null)"; }

# Bulk snapshots to avoid one ceph call per daemon / per filesystem.
CONFIG_DUMP_JSON=""
FS_DUMP_JSON=""
refresh_config_dump() { CONFIG_DUMP_JSON="$($CEPH config dump --format json 2>/dev/null)"; }
refresh_fs_dump()     { FS_DUMP_JSON="$($CEPH fs dump --format json 2>/dev/null)"; }

# Cluster version (X.Y.Z) as reported by the mons (fallback mgr, then overall).
# Parses 'ceph versions' which maps full version strings to counts per component.
cluster_version() {
    $CEPH versions --format json 2>/dev/null | jq -r '
        ([.mon // {}, .mgr // {}, .overall // {}][]
         | keys[]?
         | capture("ceph version (?<v>[0-9]+\\.[0-9]+\\.[0-9]+)").v) // empty
    ' | head -1
}

daemon_version() {
    jq -r --arg n "$1" '.[] | select(.daemon_name==$n) | .version // ""' <<<"$MDS_PS_JSON"
}
daemon_status() {
    jq -r --arg n "$1" '.[] | select(.daemon_name==$n) | .status_desc // ""' <<<"$MDS_PS_JSON"
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
$PROG - per-filesystem CephFS MDS upgrade helper
Author: Frédéric Nass (Clyso)

USAGE:
  $PROG [-i IMAGE | -t TARGET_VERSION] [options]

DESCRIPTION:
  Upgrades the MDS daemons of a single CephFS filesystem without disturbing the
  other filesystems. By default the script is argument-driven and performs no
  prompting. Run with --interactive for a guided flow.

OPTIONS:
  -i, --image IMAGE         Container image to deploy, e.g.
                            quay.io/ceph/ceph:v18.2.8 or a private-registry path.
                            The target version is derived from its :vX.Y.Z tag
                            unless overridden with -t. If the image has no
                            parseable version tag, -t is required.
  -t, --target-version VER  Target Ceph version, e.g. 18.2.8. Optional when -i is
                            given (derived from the image tag); overrides the tag
                            if both are given. With neither -i nor -t, the default
                            image quay.io/ceph/ceph:v<VER> and the cluster's
                            current version are used.
  -f, --filesystem NAME     Filesystem(s) to act on. May be a comma-separated
                            list (-f a,b,c) and/or repeated (-f a -f b). With
                            more than one, they are upgraded one after the other.
  -a, --all                 Upgrade every filesystem that needs it, one after
                            the other. Mutually exclusive with --filesystem.
                            Requires --method.
  -m, --method METHOD       Upgrade method: 'fail_fs' or 'max_mds'.
                            Required (together with --filesystem/--all) to
                            perform an upgrade.
  --interactive             Guided interactive mode (lists, prompts for the
                            filesystem and method, then upgrades).
  --force-downgrade         Allow moving MDS to an OLDER version than they
                            currently run (and disregard the cluster version).
                            Works in both normal and interactive mode.
                            DANGEROUS: MDS downgrades are not generally supported
                            and can leave a filesystem unable to start. Requires
                            an explicit typed confirmation of the filesystem name.

  --set-mds-join-fs         Set mds_join_fs affinity for every filesystem that
                            lacks it (or only for --filesystem if given), then
                            exit.
  --set-refuse-standby-for-another-fs
                            Set refuse_standby_for_another_fs on every filesystem
                            that lacks it (or only --filesystem if given), then
                            exit.

  -h, --help                Show this help and exit.

BEHAVIOR:
  $PROG
        List all filesystems with their current MDS version(s).
  $PROG -i quay.io/ceph/ceph:v18.2.8
        List all filesystems, marking each as 'needs upgrade' or 'up to date'.
  $PROG -i quay.io/ceph/ceph:v18.2.8 --filesystem cephfs2
        Error: an upgrade method (--method) is required.
  $PROG -i quay.io/ceph/ceph:v18.2.8 -f cephfs2 -m fail_fs
        Upgrade cephfs2's MDS to 18.2.8 using 'ceph fs fail'.
  $PROG -i quay.io/ceph/ceph:v18.2.8 -f cephfs2 -m max_mds
        Upgrade cephfs2's MDS to 18.2.8 by scaling to max_mds 1.
  $PROG -i quay.io/ceph/ceph:v18.2.8 --all -m fail_fs
        Upgrade every filesystem that needs it, one after the other.
  $PROG --interactive
        Guided mode.

METHODS:
  fail_fs   Fail the filesystem (offline) for the duration of the upgrade.
            Fastest and simplest; the fs is briefly unavailable.
  max_mds   Scale the filesystem to a single rank, upgrade standbys first then
            the active MDS last (single failover), then restore max_mds. The fs
            stays online but degraded; slower.

EXAMPLES:
  $PROG -i quay.io/ceph/ceph:v18.2.8
  $PROG -i quay.io/ceph/ceph:v18.2.8 -f cephfs2 -m fail_fs
  $PROG -i my.registry.local/ceph/ceph:v18.2.8 -f cephfs,cephfs2 -m max_mds
  $PROG -i my.registry.local/ceph/ceph:custom -t 18.2.8 -f cephfs2 -m fail_fs
  $PROG --set-refuse-standby-for-another-fs
  $PROG --set-mds-join-fs --filesystem cephfs2
EOF
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
TARGET_VERSION=""
FS=""
declare -a FS_LIST_ARG=()
METHOD=""
INTERACTIVE=false
IMAGE=""
ACTION_SET_JOIN_FS=false
ACTION_SET_REFUSE=false
ALL=false
FORCE_DOWNGRADE=false

# append comma-separated and/or repeated -f values
add_filesystems() {
    local IFS=','
    local item
    for item in $1; do
        [[ -n "$item" ]] && FS_LIST_ARG+=("$item")
    done
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --interactive) INTERACTIVE=true; shift ;;
        -i|--image) IMAGE="${2:-}"; shift 2 ;;
        -f|--filesystem) add_filesystems "${2:-}"; shift 2 ;;
        -m|--method) METHOD="${2:-}"; shift 2 ;;
        -a|--all) ALL=true; shift ;;
        -t|--target-version) TARGET_VERSION="${2:-}"; shift 2 ;;
        --set-mds-join-fs) ACTION_SET_JOIN_FS=true; shift ;;
        --set-refuse-standby-for-another-fs) ACTION_SET_REFUSE=true; shift ;;
        --force-downgrade) FORCE_DOWNGRADE=true; shift ;;
        --) shift; break ;;
        -*) die "unknown option: $1 (see --help)" ;;
        *) die "unexpected argument: '$1'. Use -i/--image for the image and -t/--target-version for the version (see --help)." ;;
    esac
done

# For backward compatibility, FS holds the single selected filesystem when
# exactly one is given (used by the apply_* / single-upgrade paths).
if [[ ${#FS_LIST_ARG[@]} -eq 1 ]]; then
    FS="${FS_LIST_ARG[0]}"
fi

require ceph
require jq

# Resolve IMAGE and TARGET_VERSION, image-first:
#   - if -i/--image is given, derive the version from its :vX.Y.Z tag unless
#     -t/--target-version overrides it; if neither yields a version, error.
#   - if no image is given, build the default image from the version (used by
#     the listing paths and as a convenience when only -t is supplied).
resolve_image_and_version() {
    if [[ -n "$IMAGE" ]]; then
        if [[ -z "$TARGET_VERSION" ]]; then
            if [[ "$IMAGE" =~ :v?([0-9]+\.[0-9]+\.[0-9]+) ]]; then
                TARGET_VERSION="${BASH_REMATCH[1]}"
            else
                die "could not derive a version from image '$IMAGE'; specify it with -t/--target-version."
            fi
        fi
    else
        if [[ -n "$TARGET_VERSION" ]]; then
            IMAGE="quay.io/ceph/ceph:v${TARGET_VERSION}"
        fi
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------
get_fs_list() { $CEPH fs ls --format json | jq -r '.[].name' | sort; }

# distinct MDS versions of a filesystem's service
fs_versions() {
    jq -r --arg s "mds.$1" \
        '[.[] | select(.service_name==$s) | .version] | unique | .[]' <<<"$MDS_PS_JSON"
}

# daemons of a filesystem's service
fs_daemons() {
    jq -r --arg s "mds.$1" '.[] | select(.service_name==$s) | .daemon_name' <<<"$MDS_PS_JSON" | sort
}

fs_get() { $CEPH fs get "$1" --format json; }

# refuse_standby_for_another_fs state of a filesystem from the cached fs dump.
# Prints "true"/"false". Requires refresh_fs_dump to have run.
fs_refuse_standby_cached() {
    jq -r --arg f "$1" '
        (.filesystems[] | select(.mdsmap.fs_name==$f) | .mdsmap.flags_state.refuse_standby_for_another_fs) // false
        | if . then "true" else "false" end' <<<"$FS_DUMP_JSON"
}

# mds_join_fs value for a filesystem's service section (mds.<fs>) from the
# cached config dump (empty if unset). Requires refresh_config_dump to have run.
fs_join_fs_cached() {
    # $1 = filesystem name; config section is mds.<fs>
    jq -r --arg s "mds.$1" '
        [.[] | select(.section==$s and .name=="mds_join_fs") | .value] | (.[0] // "")' \
        <<<"$CONFIG_DUMP_JSON"
}

# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------
list_filesystems() {
    # $1 = target_version (optional). With it, annotate up-to-date vs needs upgrade.
    local tv="${1:-}"
    refresh_mds_ps
    local fs vers nver note state
    if [[ -n "$tv" ]]; then
        echo "Filesystems (target version $tv):"
    else
        echo "Filesystems:"
    fi
    while IFS= read -r fs; do
        [[ -z "$fs" ]] && continue
        mapfile -t vlist < <(fs_versions "$fs")
        if [[ ${#vlist[@]} -eq 0 ]]; then
            printf "  %-28s %s\n" "$fs" "(no MDS daemons)"
            continue
        fi
        vers="$(printf '%s,' "${vlist[@]}")"; vers="${vers%,}"
        if [[ -z "$tv" ]]; then
            if [[ ${#vlist[@]} -gt 1 ]]; then
                printf "  %-28s versions: %s\n" "$fs" "$vers"
            else
                printf "  %-28s version: %s\n" "$fs" "$vers"
            fi
        else
            local has_stale=false all_target=true v
            for v in "${vlist[@]}"; do
                ver_lt "$v" "$tv" && has_stale=true
                [[ "$v" == "$tv" ]] || all_target=false
            done
            if $has_stale; then
                if [[ ${#vlist[@]} -gt 1 ]]; then
                    note="NEEDS UPGRADE (mixed: $vers)"
                else
                    note="NEEDS UPGRADE ($vers)"
                fi
            elif $all_target; then
                note="up to date ($tv)"
            else
                note="newer than target ($vers)"
            fi
            printf "  %-28s %s\n" "$fs" "$note"
        fi
    done < <(get_fs_list)
}

# ---------------------------------------------------------------------------
# Recommendations: mds_join_fs affinity + refuse_standby_for_another_fs
# ---------------------------------------------------------------------------
recommend_settings() {
    refresh_config_dump
    refresh_fs_dump
    local fs join refuse
    local -a join_missing=()
    local -a refuse_missing=()

    while IFS= read -r fs; do
        [[ -z "$fs" ]] && continue
        # mds_join_fs affinity per filesystem (section mds.<fs>)
        join="$(fs_join_fs_cached "$fs")"
        [[ -n "$join" ]] || join_missing+=("$fs")
        # refuse_standby_for_another_fs per fs
        refuse="$(fs_refuse_standby_cached "$fs")"
        [[ "$refuse" == "true" ]] || refuse_missing+=("$fs")
    done < <(get_fs_list)

    if [[ ${#join_missing[@]} -eq 0 && ${#refuse_missing[@]} -eq 0 ]]; then
        echo "   All filesystems have mds_join_fs affinity set and refuse standby for another fs."
        echo "   Nothing to recommend."
        return 0
    fi

    local step=1

    if [[ ${#join_missing[@]} -gt 0 ]]; then
        echo "  ${step}. Set mds_join_fs affinity on the following filesystem(s)"
        echo "     (pins each filesystem's MDS so standbys join the intended fs):"
        for fs in "${join_missing[@]}"; do
            echo "       $CEPH config set mds.${fs} mds_join_fs ${fs}"
        done
        echo "     Or re-run to set them all at once:"
        echo "       $PROG --set-mds-join-fs"
        echo "     Or for a single filesystem:"
        echo "       $PROG --set-mds-join-fs --filesystem <fs_name>"
        ((step++))
    fi

    if [[ ${#refuse_missing[@]} -gt 0 ]]; then
        # separate from the previous block only if one was printed
        [[ ${#join_missing[@]} -gt 0 ]] && echo
        echo "  ${step}. Set refuse_standby_for_another_fs on the following filesystem(s)"
        echo "     (prevents a non-upgraded MDS from stepping in for an upgraded one):"
        for fs in "${refuse_missing[@]}"; do
            echo "       $CEPH fs set ${fs} refuse_standby_for_another_fs true"
        done
        echo "     Or re-run to set them all at once:"
        echo "       $PROG --set-refuse-standby-for-another-fs"
        echo "     Or for a single filesystem:"
        echo "       $PROG --set-refuse-standby-for-another-fs --filesystem <fs_name>"
        ((step++))
    fi
}

# Apply mds_join_fs affinity to filesystems lacking it (all, or only --filesystem)
apply_set_join_fs() {
    refresh_config_dump
    local target_fs="${1:-}" fs join applied=0
    while IFS= read -r fs; do
        [[ -z "$fs" ]] && continue
        if [[ -n "$target_fs" && "$fs" != "$target_fs" ]]; then
            continue
        fi
        join="$(fs_join_fs_cached "$fs")"
        if [[ -z "$join" ]]; then
            info "Setting mds_join_fs=$fs on mds.$fs"
            $CEPH config set "mds.$fs" mds_join_fs "$fs"
            applied=$((applied + 1))
        fi
    done < <(get_fs_list)
    info "mds_join_fs applied to $applied filesystem(s)."
    return 0
}

# Apply refuse_standby_for_another_fs to filesystems lacking it (all, or only --filesystem)
apply_set_refuse() {
    refresh_fs_dump
    local target_fs="${1:-}" fs refuse applied=0
    while IFS= read -r fs; do
        [[ -z "$fs" ]] && continue
        if [[ -n "$target_fs" && "$fs" != "$target_fs" ]]; then
            continue
        fi
        refuse="$(fs_refuse_standby_cached "$fs")"
        if [[ "$refuse" != "true" ]]; then
            info "Setting refuse_standby_for_another_fs=true on $fs"
            $CEPH fs set "$fs" refuse_standby_for_another_fs true
            applied=$((applied + 1))
        fi
    done < <(get_fs_list)
    info "refuse_standby_for_another_fs applied to $applied filesystem(s)."
    return 0
}

# ---------------------------------------------------------------------------
# Upgrade core (shared by argument and interactive modes)
# ---------------------------------------------------------------------------
confirm() { local r; read -r -p "$1 [y/N] " r; [[ "$r" =~ ^[Yy]$ ]]; }

# redeploy a list of daemons onto IMAGE and wait until all report TARGET_VERSION
redeploy_and_wait() {
    local batch=("$@") d
    [[ ${#batch[@]} -gt 0 ]] || return 0
    for d in "${batch[@]}"; do
        info "Redeploying $d -> $IMAGE"
        $CEPH orch daemon redeploy "$d" --image "$IMAGE"
    done
    info "Waiting for ${#batch[@]} MDS daemon(s) to reach version $TARGET_VERSION (timeout ${REDEPLOY_TIMEOUT}s)"
    local deadline; deadline=$(( $(date +%s) + REDEPLOY_TIMEOUT ))
    while :; do
        refresh_mds_ps
        local ok=true
        for d in "${batch[@]}"; do
            if [[ "$(daemon_status "$d")" != "running" || "$(daemon_version "$d")" != "$TARGET_VERSION" ]]; then
                ok=false; break
            fi
        done
        $ok && { info "Batch up to date on $TARGET_VERSION"; return 0; }
        if (( $(date +%s) >= deadline )); then
            warn "Timed out waiting for MDS redeploy. Current state:"
            for d in "${batch[@]}"; do
                echo "    $d : status=$(daemon_status "$d") version=$(daemon_version "$d")" >&2
            done
            return 1
        fi
        sleep "$POLL_INTERVAL"
    done
}

do_upgrade() {
    # uses globals: FS, METHOD, TARGET_VERSION, IMAGE
    [[ -n "$FS" ]] || die "no filesystem specified"
    [[ -n "$TARGET_VERSION" ]] || die "no target version specified"
    [[ -n "$IMAGE" ]] || die "no image resolved"
    case "$METHOD" in
        fail_fs|max_mds) ;;
        *) die "invalid or missing --method (expected 'fail_fs' or 'max_mds')" ;;
    esac

    refresh_mds_ps
    mapfile -t ALL_DAEMONS < <(fs_daemons "$FS")
    [[ ${#ALL_DAEMONS[@]} -gt 0 ]] || die "no MDS daemons found for filesystem '$FS' (service mds.$FS)"

    local -a STALE=() SKIP=()
    local d dv
    local is_downgrade=false
    for d in "${ALL_DAEMONS[@]}"; do
        dv="$(daemon_version "$d")"
        if [[ "$dv" == "$TARGET_VERSION" ]]; then
            SKIP+=("$d")
        else
            STALE+=("$d")
            # a daemon currently NEWER than target means this is a downgrade
            ver_lt "$TARGET_VERSION" "$dv" && is_downgrade=true
        fi
    done
    [[ ${#STALE[@]} -gt 0 ]] || die "all MDS of '$FS' already on $TARGET_VERSION (nothing to do)"

    # A downgrade (moving any MDS to an OLDER version) is dangerous and is only
    # allowed with --force-downgrade.
    if $is_downgrade && ! $FORCE_DOWNGRADE; then
        die "'$FS' has MDS newer than $TARGET_VERSION; this would be a DOWNGRADE. Re-run with --force-downgrade to allow it."
    fi

    local ASR ORIG_MAX_MDS
    ASR="$(fs_get "$FS" | jq -r 'if (.mdsmap.flags_state.allow_standby_replay // false) then "true" else "false" end')"
    [[ "$ASR" == "true" || "$ASR" == "false" ]] || ASR="false"
    ORIG_MAX_MDS="$(fs_get "$FS" | jq -r '.mdsmap.max_mds')"

    local plan_title="UPGRADE PLAN"
    $is_downgrade && plan_title="*** DOWNGRADE PLAN ***"

    echo
    echo "==================== $plan_title ===================="
    echo "Filesystem      : $FS"
    echo "Method          : $METHOD"
    echo "Target image    : $IMAGE"
    echo "Target version  : $TARGET_VERSION"
    echo "max_mds (orig)  : $ORIG_MAX_MDS"
    echo "standby_replay  : $ASR"
    echo "Will redeploy (${#STALE[@]}):"
    for d in "${STALE[@]}"; do echo "    + $d ($(daemon_version "$d") -> $TARGET_VERSION)"; done
    if [[ ${#SKIP[@]} -gt 0 ]]; then
        echo "Will skip (already on target) (${#SKIP[@]}):"
        for d in "${SKIP[@]}"; do echo "    - $d (skipped)"; done
    fi
    echo "Other filesystems are NOT touched."
    echo "======================================================"

    if $is_downgrade; then
        echo
        warn "DOWNGRADE REQUESTED for '$FS': MDS will be moved to an OLDER version ($TARGET_VERSION)."
        warn "MDS downgrades across versions are NOT generally supported by Ceph."
        warn "An older MDS may refuse to join if the filesystem's compat/incompat"
        warn "feature set was advanced by the newer version, potentially leaving"
        warn "'$FS' unable to start. Ensure you have verified this path is safe"
        warn "(e.g. with Ceph support) and have backups/snapshots as appropriate."
        # Mandatory typed confirmation, even in non-interactive mode.
        local reply
        read -r -p "Type the filesystem name '$FS' to confirm the downgrade: " reply
        [[ "$reply" == "$FS" ]] || die "downgrade not confirmed; aborting (no changes made to '$FS')."
    elif $INTERACTIVE; then
        confirm "Proceed?" || die "aborted by user"
    fi

    # Prepare
    if [[ "$ASR" == "true" ]]; then
        info "Disabling allow_standby_replay on $FS"
        $CEPH fs set "$FS" allow_standby_replay false
    fi

    if [[ "$METHOD" == "fail_fs" ]]; then
        info "Failing filesystem $FS (offline until restore)"
        $CEPH fs fail "$FS"
    else
        if [[ "$ORIG_MAX_MDS" -gt 1 ]]; then
            info "Scaling $FS down to max_mds 1 (will restore to $ORIG_MAX_MDS)"
            $CEPH fs set "$FS" max_mds 1
            info "Waiting for $FS to reach a single active rank..."
            local sd; sd=$(( $(date +%s) + REDEPLOY_TIMEOUT ))
            while :; do
                local ranks
                ranks="$(fs_get "$FS" | jq -r '[.mdsmap.info[] | select(.state|startswith("up:active"))] | length')"
                [[ "$ranks" == "1" ]] && break
                (( $(date +%s) >= sd )) && die "timed out waiting for $FS to scale down to 1 rank"
                sleep "$POLL_INTERVAL"
            done
        fi
    fi

    # Redeploy
    if [[ "$METHOD" == "max_mds" ]]; then
        refresh_mds_ps
        local ACTIVE_DAEMON
        ACTIVE_DAEMON="$(fs_get "$FS" | jq -r '.mdsmap.info[] | select(.state|startswith("up:active")) | "mds."+.name' | head -1)"
        local -a STALE_STANDBY=() STALE_ACTIVE=()
        for d in "${STALE[@]}"; do
            if [[ -n "$ACTIVE_DAEMON" && "$d" == "$ACTIVE_DAEMON" ]]; then
                STALE_ACTIVE+=("$d")
            else
                STALE_STANDBY+=("$d")
            fi
        done
        if [[ ${#STALE_STANDBY[@]} -gt 0 ]]; then
            info "Phase 1/2: upgrading ${#STALE_STANDBY[@]} standby MDS (no failover)"
            redeploy_and_wait "${STALE_STANDBY[@]}" || die "standby upgrade failed; '$FS' left at max_mds 1. Restore with: $CEPH fs set $FS max_mds $ORIG_MAX_MDS"
        fi
        if [[ ${#STALE_ACTIVE[@]} -gt 0 ]]; then
            info "Phase 2/2: upgrading the active MDS ${STALE_ACTIVE[0]} last (single failover)"
            redeploy_and_wait "${STALE_ACTIVE[@]}" || die "active upgrade failed; '$FS' left at max_mds 1. Restore with: $CEPH fs set $FS max_mds $ORIG_MAX_MDS"
        else
            info "Active MDS already on target; no failover needed"
        fi
    else
        redeploy_and_wait "${STALE[@]}" || die "redeploy failed; '$FS' left FAILED. Restore with: $CEPH fs set $FS joinable true"
    fi

    # Restore
    if [[ "$METHOD" == "fail_fs" ]]; then
        info "Setting $FS joinable"
        $CEPH fs set "$FS" joinable true
    else
        if [[ "$ORIG_MAX_MDS" -gt 1 ]]; then
            info "Restoring max_mds to $ORIG_MAX_MDS on $FS"
            $CEPH fs set "$FS" max_mds "$ORIG_MAX_MDS"
        fi
    fi
    if [[ "$ASR" == "true" ]]; then
        info "Restoring allow_standby_replay on $FS"
        $CEPH fs set "$FS" allow_standby_replay true
    fi

    info "Waiting for an active MDS on $FS"
    local i
    for i in $(seq 1 30); do
        local active
        active="$(fs_get "$FS" | jq -r '[.mdsmap.info[] | select(.state=="up:active")] | length')"
        [[ "$active" -ge 1 ]] && break
        sleep "$POLL_INTERVAL"
    done

    echo
    info "Done. Final state of $FS:"
    sleep 3
    $CEPH fs status "$FS" 2>/dev/null || fs_get "$FS" | jq '.mdsmap | {max_mds, in, up, flags}'
}

# Upgrade every filesystem that has at least one MDS older than TARGET_VERSION,
# one after the other. Uses METHOD, TARGET_VERSION, IMAGE.
# do_upgrade_list [fs...] : upgrade the given filesystems (one after the other),
# skipping any that are already on TARGET_VERSION. With no arguments, considers
# all filesystems on the cluster.
do_upgrade_list() {
    [[ -n "$TARGET_VERSION" ]] || die "no target version specified"
    case "$METHOD" in
        fail_fs|max_mds) ;;
        *) die "invalid or missing --method (expected 'fail_fs' or 'max_mds')" ;;
    esac

    refresh_mds_ps

    # candidate list: explicit args, or all filesystems
    local -a CANDIDATES=()
    if [[ $# -gt 0 ]]; then
        CANDIDATES=("$@")
    else
        local f
        while IFS= read -r f; do [[ -n "$f" ]] && CANDIDATES+=("$f"); done < <(get_fs_list)
    fi

    # validate names and gather existing filesystems
    local -a EXISTING=()
    while IFS= read -r f; do [[ -n "$f" ]] && EXISTING+=("$f"); done < <(get_fs_list)
    local fs found
    for fs in "${CANDIDATES[@]}"; do
        found=false
        local e
        for e in "${EXISTING[@]}"; do [[ "$e" == "$fs" ]] && found=true; done
        $found || die "filesystem '$fs' not found on this cluster"
    done

    # keep only those needing work
    #   normal:          at least one MDS OLDER than target (needs upgrade)
    #   force-downgrade: at least one MDS not EQUAL to target (any direction)
    local -a TODO=()
    local v needs
    for fs in "${CANDIDATES[@]}"; do
        needs=false
        while IFS= read -r v; do
            [[ -z "$v" ]] && continue
            if $FORCE_DOWNGRADE; then
                [[ "$v" != "$TARGET_VERSION" ]] && needs=true
            else
                ver_lt "$v" "$TARGET_VERSION" && needs=true
            fi
        done < <(fs_versions "$fs")
        if $needs; then
            TODO+=("$fs")
        elif $FORCE_DOWNGRADE; then
            info "Skipping '$fs' (already on $TARGET_VERSION)."
        else
            info "Skipping '$fs' (already on $TARGET_VERSION or newer)."
        fi
    done

    if [[ ${#TODO[@]} -eq 0 ]]; then
        info "No filesystem needs changing to $TARGET_VERSION. Nothing to do."
        return 0
    fi

    info "Filesystems to upgrade to $TARGET_VERSION (method=$METHOD): ${TODO[*]}"
    local idx=0 total=${#TODO[@]}
    for fs in "${TODO[@]}"; do
        idx=$((idx + 1))
        echo
        echo "----------------------------------------------------------"
        echo " [$idx/$total] Upgrading filesystem: $fs"
        echo "----------------------------------------------------------"
        FS="$fs"
        do_upgrade
    done
    echo
    info "All ${total} filesystem(s) processed."
    return 0
}

# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------
interactive_mode() {
    refresh_mds_ps
    # ask target version if not given
    if [[ -z "$TARGET_VERSION" ]]; then
        read -r -p "Target version (e.g. 18.2.8): " TARGET_VERSION
        [[ -n "$TARGET_VERSION" ]] || die "no target version given"
    fi
    resolve_image_and_version

    # build selectable list
    mapfile -t FS_LIST < <(get_fs_list)
    local -a SELECTABLE=(); local idx=1 fs
    echo
    echo "Upgradable filesystems (MDS older than $TARGET_VERSION):"
    local any=false
    for fs in "${FS_LIST[@]}"; do
        mapfile -t vlist < <(fs_versions "$fs")
        [[ ${#vlist[@]} -eq 0 ]] && continue
        local has_stale=false v
        for v in "${vlist[@]}"; do ver_lt "$v" "$TARGET_VERSION" && has_stale=true; done
        $has_stale || continue
        any=true
        local vers; vers="$(printf '%s,' "${vlist[@]}")"; vers="${vers%,}"
        printf "  %2d) %-28s (%s)\n" "$idx" "$fs" "$vers"
        SELECTABLE[$idx]="$fs"; ((idx++))
    done
    $any || die "No filesystem needs upgrading to $TARGET_VERSION."

    local count=$((idx-1)) choice
    echo
    if [[ "$count" -eq 1 ]]; then
        read -r -p "Select a filesystem to upgrade [1] (Enter to confirm): " choice
        choice="${choice:-1}"
    else
        read -r -p "Select a filesystem to upgrade [1-$count]: " choice
    fi
    [[ "$choice" =~ ^[0-9]+$ && -n "${SELECTABLE[$choice]:-}" ]] || die "invalid selection"
    FS="${SELECTABLE[$choice]}"

    echo
    echo "Upgrade method for '$FS':"
    echo "  1) fail_fs  (default) - fs offline briefly; fastest"
    echo "  2) max_mds            - fs online but degraded; slower"
    local m
    read -r -p "Choose [1/2, default 1]: " m
    case "${m:-1}" in
        1|"") METHOD="fail_fs" ;;
        2)    METHOD="max_mds" ;;
        *)    die "invalid method" ;;
    esac

    do_upgrade
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

# Standalone fix actions: run any that are requested (both may be given), then exit.
# Honor multiple -f filesystems; with none given, apply to all.
if $ACTION_SET_JOIN_FS || $ACTION_SET_REFUSE; then
    if [[ ${#FS_LIST_ARG[@]} -gt 0 ]]; then
        for _fs in "${FS_LIST_ARG[@]}"; do
            if $ACTION_SET_JOIN_FS; then apply_set_join_fs "$_fs"; fi
            if $ACTION_SET_REFUSE; then apply_set_refuse "$_fs"; fi
        done
    else
        if $ACTION_SET_JOIN_FS; then apply_set_join_fs ""; fi
        if $ACTION_SET_REFUSE; then apply_set_refuse ""; fi
    fi
    exit 0
fi

if $INTERACTIVE; then
    interactive_mode
    exit 0
fi

# Non-interactive, argument-driven dispatch.

# Determine the cluster's current version (mons/mgrs) once.
CLUSTER_VERSION="$(cluster_version)"

# Resolve image and version first: if -i/--image was given, the version is
# derived from its tag (unless -t overrides). This must happen before the
# cluster-version fallback so an explicit image wins.
resolve_image_and_version

# When still no target version is given, default it to the cluster's version.
DEFAULTED_VERSION=false
if [[ -z "$TARGET_VERSION" ]]; then
    if [[ -n "$CLUSTER_VERSION" ]]; then
        TARGET_VERSION="$CLUSTER_VERSION"
        DEFAULTED_VERSION=true
        # build the default image now that we have a version
        resolve_image_and_version
    fi
fi

# Header: explain what the script is doing.
echo "=========================================================="
echo " CephFS per-filesystem MDS upgrade helper"
echo "=========================================================="
echo
echo "Step 1. Cluster version"
echo
if [[ -n "$CLUSTER_VERSION" ]]; then
    echo "   Current version of the cluster (mons/mgrs): $CLUSTER_VERSION"
else
    echo "   Current version of the cluster (mons/mgrs): unknown"
fi
if $DEFAULTED_VERSION; then
    echo "   No target version given; using the cluster version ($TARGET_VERSION) as target."
fi

if [[ ${#FS_LIST_ARG[@]} -eq 0 ]] && ! $ALL; then
    echo
    echo "Step 2. Filesystems and their MDS versions"
    echo
    # version (explicit or defaulted) -> list with up-to-date / needs upgrade annotations
    if [[ -n "$TARGET_VERSION" ]]; then
        list_filesystems "$TARGET_VERSION"
    else
        list_filesystems
    fi
    echo
    echo "Step 3. Pre-upgrade recommendations"
    echo
    recommend_settings
    echo
    echo "----------------------------------------------------------"
    echo "To upgrade one filesystem, re-run with:"
    echo "    ./$PROG -t $TARGET_VERSION -f <fs_name> -m fail_fs|max_mds"
    echo "To upgrade all filesystems one after the other, re-run with:"
    echo "    ./$PROG -t $TARGET_VERSION --all -m fail_fs|max_mds"
    echo "----------------------------------------------------------"
    echo
    echo "For a full description of all arguments, re-run with -h / --help."
    exit 0
fi

# An upgrade is intended (either --all or a specific --filesystem).
echo
echo "Step 2. Upgrade"
echo

# version + target but no method -> error asking for method
if [[ -z "$METHOD" ]]; then
    die "an upgrade method is required: specify --method fail_fs|max_mds (or use --interactive)"
fi

if $ALL; then
    [[ ${#FS_LIST_ARG[@]} -eq 0 ]] || die "--all and --filesystem are mutually exclusive"
    do_upgrade_list           # all filesystems
elif [[ ${#FS_LIST_ARG[@]} -gt 1 ]]; then
    do_upgrade_list "${FS_LIST_ARG[@]}"   # the specified list
else
    # exactly one filesystem (FS already set from FS_LIST_ARG[0])
    do_upgrade
fi

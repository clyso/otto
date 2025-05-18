#!/bin/sh

#
# Collect Ceph cluster info
#

CENSORED="${CENSORED:-<CENSORED>}"
CEPH="${CEPH:-ceph}"
CEPH_CONFIG_FILE="${CEPH_CONFIG_FILE:-/etc/ceph/ceph.conf}"
CEPH_TIMEOUT="${CEPH_TIMEOUT:-10}"
QUERY_INACTIVE_PG="${QUERY_INACTIVE_PG:-N}"
RADOSGW_ADMIN="${RADOSGW_ADMIN:-radosgw-admin}"
VERBOSE="${VERBOSE:-N}"
COLLECT_ALL_OSD_ASOK_STATS="${COLLECT_ALL_OSD_ASOK_STATS:-N}"
RESET_MDS_PERF_AND_SLEEP="${RESET_MDS_PERF_AND_SLEEP:-0}"
RESET_MGR_PERF_AND_SLEEP="${RESET_MGR_PERF_AND_SLEEP:-0}"
RESET_MON_PERF_AND_SLEEP="${RESET_MON_PERF_AND_SLEEP:-0}"
RESET_OSD_PERF_AND_SLEEP="${RESET_OSD_PERF_AND_SLEEP:-0}"

#
# Functions
#

usage()
{
    echo
    echo "usage: $0 [options]"
    echo
    echo "Options:"
    echo
    echo "  -h | --help                            print this help and exit"
    echo "  -c | --ceph-config-file <file>         ceph configuration file"
    echo "  -q | --query-inactive-pg               query inactive pg"
    echo "  -r | --results-dir <dir>               directory to store result"
    echo "  -t | --timeout <seconds>               timeout for ceph operations"
    echo "  -u | --uncensored                      don't hide sensitive data"
    echo "  -v | --verbose                         be verbose"
    echo "  -a | --all-osd-asok-stats              get data via admin socket (tell)"
    echo "                                         for all osds"
    echo "  -D | --mds-perf-reset-and-sleep <sec>  reset mds perf counters and sleep"
    echo "  -G | --mgr-perf-reset-and-sleep <sec>  reset mgr perf counters and sleep"
    echo "  -M | --mon-perf-reset-and-sleep <sec>  reset mon perf counters and sleep"
    echo "  -O | --osd-perf-reset-and-sleep <sec>  reset osd perf counters and sleep"
    echo
}

cleanup() {
    test -n "${RESULTS_DIR}" && rm -Rf "${RESULTS_DIR}"
}

info() {
    echo "$*" >&2
}

version() {
    md5sum "$(command -v $0)" | cut -d' ' -f1
}

censor_config() {
    if [ -z "${CENSORED}" ]; then
        "$@"
        return
    fi

    "$@" | sed "s/\(ACCESS_KEY\|SECRET_KEY\|PASSWORD\)\(\s*\).*/\1\2${CENSORED}/gi"
}

censor_config_json() {
    if [ -z "${CENSORED}" ]; then
        "$@"
        return
    fi

    "$@" | jq 'map(if (.name | test("ACCESS_KEY|SECRET_KEY|PASSWORD"))
                   then .value = "'"${CENSORED}"'"
                   else . end)'
}

censor_config_log_json() {
    if [ -z "${CENSORED}" ]; then
        "$@"
        return
    fi

    "$@" | jq 'map(
                .changes |= map(
                  if (.name | test("ACCESS_KEY|SECRET_KEY|PASSWORD"))
                  then
                    .previous_value = "'"${CENSORED}"'"
                   |.new_value = "'"${CENSORED}"'"
                  else .
                  end
                 )
               )'
}

censor_auth() {
    if [ -z "${CENSORED}" ]; then
        "$@"
        return
    fi

    "$@" | sed "s/\(key:\)\(\s*\).*/\1\2${CENSORED}/g"
}

censor_auth_json() {
    if [ -z "${CENSORED}" ]; then
        "$@"
        return
    fi

    "$@" | jq '.auth_dump |= map(.key = "'"${CENSORED}"'")'
}

store() {
    local skip_json=0
    local json_file_compat=0

    while true; do
        case "$1" in
            -s)
                skip_json=1
                shift
                ;;
            -S)
                skip_json=2
                shift
                ;;
            -c)
                json_file_compat=1
                shift
                ;;
            *)
                break
                ;;
        esac
    done

    local name=$1; shift;
    local log_name="${name}.log"

    "$@" > "${RESULTS_DIR}/${name}" 2> "${RESULTS_DIR}/${log_name}"

    if [ ${skip_json} -eq 0 ]; then
	"$@" -f json > "${RESULTS_DIR}/${name}.json" 2>> \
	     "${RESULTS_DIR}/${log_name}"
    elif [ ${skip_json} -eq 1 ]; then
	ln -sr "${RESULTS_DIR}/${name}" "${RESULTS_DIR}/${name}.json"
    fi

    # TODO: remove this when all tools are updated to use *.json files only.
    if [ $json_file_compat -eq 1 ]; then
        ln -sr "${RESULTS_DIR}/${name}.json" "${RESULTS_DIR}/${name}_json"
    fi
}

show_stored() {
    local name="$1"

    cat "${RESULTS_DIR}/${name}"
}

get_script_info() {
    local t=script_info

    info "collecting script info ..."

    store -S ${t}-version version
}

get_system_info() {
    local t=system_info

    info "collecting system info ..."

    store -S ${t}-uname       uname -a
    store -S ${t}-lsb_release lsb_release -a
}

get_ceph_info() {
    local t=ceph_cluster_info

    info "collecting ceph cluster info ..."

    store    ${t}-status           ${CEPH} status
    store    ${t}-version          ${CEPH} version
    store    ${t}-versions         ${CEPH} versions
    store    ${t}-fsid             ${CEPH} fsid
    store -S ${t}-ceph_conf        censor_config          cat ${CEPH_CONFIG_FILE}
    store -S ${t}-config_dump      censor_config          ${CEPH} config dump
    store -S ${t}-config_dump.json censor_config_json     ${CEPH} config dump -f json
    store -S ${t}-config_log       censor_config          ${CEPH} config log
    store -S ${t}-config_log.json  censor_config_log_json ${CEPH} config log -f json
    store -S ${t}-auth_list        censor_auth            ${CEPH} auth list
    store -S ${t}-auth_list.json   censor_auth_json       ${CEPH} auth list -f json
}

get_health_info() {
    local t=cluster_health
    local id

    info "collecting cluster health info ..."

    store    ${t}-stat            ${CEPH} health
    store    ${t}-detail          ${CEPH} health detail
    store    ${t}-df              ${CEPH} df
    store    ${t}-df-detail       ${CEPH} df detail
    store -s ${t}-report          ${CEPH} report
    store    ${t}-crash_ls        ${CEPH} crash ls
    store    ${t}-balancer-status ${CEPH} balancer status

    show_stored ${t}-crash_ls | grep -o '^[0-9][^ ]*' |
    while read id; do
        store -s ${t}-crash_info_${id} ${CEPH} crash info ${id}
    done
}

get_monitor_info() {
    local t=monitor_info

    info "collecting monitor info ..."

    store    ${t}-stat     ${CEPH} mon stat
    store    ${t}-dump     ${CEPH} mon dump
    store -s ${t}-map      ${CEPH} mon getmap
    store -s ${t}-metadata ${CEPH} mon metadata

    if [ "${RESET_MON_PERF_AND_SLEEP}" -gt 0 ]; then
        store -S ${t}-perf_reset ${CEPH} tell mon.\* perf reset all
        info "sleeping for ${RESET_MON_PERF_AND_SLEEP} sec after reseting mon perf counters ..."
        sleep ${RESET_MON_PERF_AND_SLEEP}
    fi

    show_stored ${t}-dump |
    sed -nEe 's/^.* (mon\..*)$/\1/p' |
    while read mon; do
        store -s ${t}-${mon}-config_diff            ${CEPH} tell ${mon} config diff
        store -s ${t}-${mon}-config_show            ${CEPH} tell ${mon} config show
        store -s ${t}-${mon}-dump_historic_ops      ${CEPH} tell ${mon} dump_historic_ops
        store -s ${t}-${mon}-dump_historic_slow_ops ${CEPH} tell ${mon} dump_historic_slow_ops
        store -s ${t}-${mon}-dump_mempools          ${CEPH} tell ${mon} dump_mempools
        store -s ${t}-${mon}-mon_status             ${CEPH} tell ${mon} mon_status
        store -s ${t}-${mon}-ops                    ${CEPH} tell ${mon} ops
        store -s ${t}-${mon}-perf_dump              ${CEPH} tell ${mon} perf dump
        store -s ${t}-${mon}-sessions               ${CEPH} tell ${mon} sessions
    done
}

get_device_info() {
    local t=device_info

    info "collecting device info ..."

    store -c ${t}-ls ${CEPH} device ls
}

get_manager_info() {
    local t=manager_info

    info "collecting manager info ..."

    store    ${t}-ls-modules ${CEPH} mgr module ls
    store -s ${t}-dump    ${CEPH} mgr dump
    store -s ${t}-metadata   ${CEPH} mgr metadata

    if [ "${RESET_MGR_PERF_AND_SLEEP}" -gt 0 ]; then
        store -S ${t}-perf_reset ${CEPH} tell mgr.\* perf reset all
        info "sleeping for ${RESET_MGR_PERF_AND_SLEEP} sec after reseting mgr perf counters ..."
        sleep ${RESET_MGR_PERF_AND_SLEEP}
    fi

    show_stored ${t}-dump |
    sed -nEe 's/^.*"active_name": "([^"]*)".*$/mgr.\1/p' |
    while read mgr; do
        store -s ${t}-${mgr}-mds_requests  ${CEPH} tell ${mgr} mds_requests
        store -s ${t}-${mgr}-config_diff   ${CEPH} tell ${mgr} config diff
        store -s ${t}-${mgr}-config_show   ${CEPH} tell ${mgr} config show
        store -s ${t}-${mgr}-dump_cache    ${CEPH} tell ${mgr} dump_cache
        store -s ${t}-${mgr}-dump_mempools ${CEPH} tell ${mgr} dump_mempools
        store -s ${t}-${mgr}-mgr_status    ${CEPH} tell ${mgr} mgr_status
        store -s ${t}-${mgr}-perf_dump     ${CEPH} tell ${mgr} perf dump
        store -s ${t}-${mgr}-status        ${CEPH} tell ${mgr} status
    done
}

get_osd_info() {
    local t=osd_info

    info "collecting osd info ..."

    store -c ${t}-tree      ${CEPH} osd tree
    store    ${t}-df        ${CEPH} osd df
    store    ${t}-df-tree   ${CEPH} osd df tree
    store    ${t}-dump      ${CEPH} osd dump
    store    ${t}-stat      ${CEPH} osd stat
    store -s ${t}-crushmap  ${CEPH} osd getcrushmap
    store -s ${t}-map       ${CEPH} osd getmap
    store -s ${t}-metadata  ${CEPH} osd metadata
    store    ${t}-perf      ${CEPH} osd perf

    show_stored ${t}-crushmap | store ${t}-crushmap.txt crushtool -d -

    if [ "${RESET_OSD_PERF_AND_SLEEP}" -gt 0 ]; then
        store -S ${t}-perf_reset ${CEPH} tell osd.\* perf reset all
        info "sleeping for ${RESET_OSD_PERF_AND_SLEEP} sec after reseting osd perf counters ..."
        sleep ${RESET_OSD_PERF_AND_SLEEP}
    fi

    # Sort osds by weight and collect stats for one of every class
    # with highest weight, unless COLLECT_ALL_OSD_ASOK_STATS is set,
    # in which case stats for all osds are collected.
    # The sort and awk commands below parse lines like this:
    #
    #   99    ssd     0.21799          osd.99               up   1.00000  1.00000
    #
    show_stored ${t}-tree | sort -n -k 3 |
    awk -v a=$(test "${COLLECT_ALL_OSD_ASOK_STATS}" = Y && echo 1) '
        $5 == "up" && $6 > 0.8 {
            if (a) {print $4} else {o[$2] = $4}
        }
        END {
            if (!a) {
                for (c in o) print o[c]
             }
        }' |
    while read osd; do
        store -s ${t}-${osd}-cache_status            ${CEPH} tell ${osd} cache status
        store -s ${t}-${osd}-config_diff             ${CEPH} tell ${osd} config diff
        store -s ${t}-${osd}-config_show             ${CEPH} tell ${osd} config show
        store -s ${t}-${osd}-dump_historic_ops       ${CEPH} tell ${osd} dump_historic_ops
        store -s ${t}-${osd}-dump_historic_slow_ops  ${CEPH} tell ${osd} dump_historic_slow_ops
        store -s ${t}-${osd}-dump_mempools           ${CEPH} tell ${osd} dump_mempools
        store -s ${t}-${osd}-dump_ops_in_flight      ${CEPH} tell ${osd} dump_ops_in_flight
        store -s ${t}-${osd}-dump_osd_network        ${CEPH} tell ${osd} dump_osd_network
        store -s ${t}-${osd}-dump_scrub_reservations ${CEPH} tell ${osd} dump_scrub_reservations
        store -s ${t}-${osd}-dump_scrubs             ${CEPH} tell ${osd} dump_scrubs
        store -s ${t}-${osd}-perf_dump               ${CEPH} tell ${osd} perf dump
        store -s ${t}-${osd}-status                  ${CEPH} tell ${osd} status
    done
}

get_pg_info() {
    local t=pg_info
    local pgid

    info "collecting pg info ..."

    store    ${t}-stat       ${CEPH} pg stat
    store -c ${t}-dump       ${CEPH} pg dump
    store    ${t}-dump_stuck ${CEPH} pg dump_stuck

    if [ "$QUERY_INACTIVE_PG" = Y ]; then
        store -S ${t}-dump_stuck_inactive ${CEPH} pg dump_stuck inactive
        show_stored ${t}-dump_stuck_inactive | grep -o '^[0-9][^ ]*' |
        while read pgid; do
            store -s ${t}-query-${pgid} ${CEPH} pg ${pgid} query
        done
    fi
}

get_mds_info() {
    local t=mds_info

    info "collecting mds info ..."

    store    ${t}-stat ${CEPH} mds stat
    store -s ${t}-metadata ${CEPH} mds metadata
}

get_fs_info() {
    local t=fs_info
    local mds

    info "collecting fs info ..."

    store ${t}-ls     ${CEPH} fs ls
    store ${t}-status ${CEPH} fs status
    store ${t}-dump   ${CEPH} fs dump

    if [ "${RESET_MDS_PERF_AND_SLEEP}" -gt 0 ]; then
        store -S ${t}-perf_reset ${CEPH} tell mds.\* perf reset all
        info "sleeping for ${RESET_MDS_PERF_AND_SLEEP} sec after reseting mds perf counters ..."
        sleep ${RESET_MDS_PERF_AND_SLEEP}
    fi

    show_stored ${t}-dump |
    sed -nEe 's/^\[(mds\.[^{]*).*state up:active.*/\1/p' |
    while read mds; do
        store -s ${t}-${mds}-cache_status       ${CEPH} tell ${mds} cache status
        store -s ${t}-${mds}-dump_historic_ops  ${CEPH} tell ${mds} dump_historic_ops
        store -s ${t}-${mds}-dump_loads         ${CEPH} tell ${mds} dump loads
        store -s ${t}-${mds}-dump_mempools      ${CEPH} tell ${mds} dump_mempools
        store -s ${t}-${mds}-dump_ops_in_flight ${CEPH} tell ${mds} dump_ops_in_flight
        store -s ${t}-${mds}-perf_dump          ${CEPH} tell ${mds} perf dump
        store -s ${t}-${mds}-scrub_status       ${CEPH} tell ${mds} scrub status
        store -s ${t}-${mds}-session_ls         ${CEPH} tell ${mds} session ls
        store -s ${t}-${mds}-status             ${CEPH} tell ${mds} status
        store -s ${t}-${mds}-config_diff        ${CEPH} tell ${mds} config diff
        store -s ${t}-${mds}-config_show        ${CEPH} tell ${mds} config show
        store -s ${t}-${mds}-damage_ls          ${CEPH} tell ${mds} damage ls
        store -s ${t}-${mds}-dump_blocked_ops   ${CEPH} tell ${mds} dump_blocked_ops
    done
}

get_radosgw_admin_info() {
    local t=radosgw_admin_info

    if ! ${CEPH} osd dump | grep -q '^pool .* application rgw'; then
        return
    fi

    root_pool=$(${CEPH} config get client.admin rgw_realm_root_pool)
    if [ -z "${root_pool}" ]; then
        return
    fi
    if ! ${CEPH} osd pool ls | fgrep -q "${root_pool}"; then
        return
    fi

    info "collecting radosgw info ..."

    store -s ${t}-bucket_stats                  ${RADOSGW_ADMIN} bucket stats
    store -s ${t}-bucket_limit_check            ${RADOSGW_ADMIN} bucket limit check
    store -s ${t}-metadata_list_bucket.instance ${RADOSGW_ADMIN} metadata list bucket.instance
    store -s ${t}-period_get                    ${RADOSGW_ADMIN} period get
    store -S ${t}-sync_status                   ${RADOSGW_ADMIN} sync status
}

get_orch_info() {
    local t=orch_info

    info "collecting orchestrator info ..."

    store    ${t}-status  ${CEPH} orch status
    store    ${t}-ls      ${CEPH} orch ls
    store -S ${t}-ls_yaml ${CEPH} orch ls --format yaml
    store    ${t}-ps      ${CEPH} orch ps
}

archive_result() {
    local result_archive compress

    info "archiving ${RESULTS_DIR} ..."

    if which tar > /dev/null 2>&1; then
        result_archive=${RESULTS_DIR}.tar.gz

        tar -czf ${result_archive} -C $(dirname ${RESULTS_DIR}) $(basename ${RESULTS_DIR})

    elif which cpio > /dev/null 2>&1; then
        result_archive=${RESULTS_DIR}.cpio

        if which gzip > /dev/null 2>&1; then
            compress="gzip -c"
            result_archive=${result_archive}.gz
        elif which bzip2 > /dev/null 2>&1; then
            compress="bzip2 -c"
            result_archive=${result_archive}.bz2
        else
            compress="cat"
        fi

        (
           cd $(dirname ${RESULTS_DIR}) &&
           find $(basename ${RESULTS_DIR}) -print | cpio -o -H newc
        ) | ${compress} > ${result_archive}
    else
        info "no archiving tool found, keeping results in directory"
        result_archive=${RESULTS_DIR}

        # Reset RESULTS_DIR to prevent removal on cleanup
        RESULTS_DIR=
    fi

    info "done"
    info "result: ${result_archive}"
}

#
# Main
#

OPTIONS=$(getopt -o ac:hqr:t:uvD:G:M:O:V --long all-osd-asok-stats,ceph-config-file:,help,query-inactive-pg,results-dir:,timeout:,uncensored,verbose,mds-perf-reset-and-sleep:,mgr-perf-reset-and-sleep:,mon-perf-reset-and-sleep:,osd-perf-reset-and-sleep:,version -- "$@")
if [ $? -ne 0 ]; then
    usage >&2
    exit 1
fi

eval set -- "$OPTIONS"
while true; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        -c|--ceph-config-file)
            CEPH_CONFIG_FILE="$2"
            shift 2
            ;;
        -a|--all-osd-asok-stats)
            COLLECT_ALL_OSD_ASOK_STATS=Y
            shift
            ;;
        -q|--query-inactive-pg)
            QUERY_INACTIVE_PG=Y
            shift
            ;;
        -r|--results-dir)
            RESULTS_DIR="$2"
            shift 2
            ;;
        -t|--timeout)
            CEPH_TIMEOUT="$2"
            shift 2
            ;;
        -u|--uncensored)
            CENSORED=
            shift
            ;;
        -v|--verbose)
            VERBOSE=Y
            shift
            ;;
        -D|--mds-perf-reset-and-sleep)
            RESET_MDS_PERF_AND_SLEEP="$2"
            shift 2
            ;;
        -G|--mgr-perf-reset-and-sleep)
            RESET_MGR_PERF_AND_SLEEP="$2"
            shift 2
            ;;
        -M|--mon-perf-reset-and-sleep)
            RESET_MON_PERF_AND_SLEEP="$2"
            shift 2
            ;;
        -O|--osd-perf-reset-and-sleep)
            RESET_OSD_PERF_AND_SLEEP="$2"
            shift 2
            ;;
	-V|--version)
	    version
	    exit 0
	    ;;
        --)
            shift
            break
            ;;
        *)
            echo "Invalid option: $1" >&1
            usage >&2
            exit 1
            ;;
    esac
done

if ! [ "${CEPH_TIMEOUT}" -gt 0 ]; then
    echo "Invalid ceph timeout: ${CEPH_TIMEOUT}" >&1
    usage >&2
    exit 1
fi

if [ "${VERBOSE}" = Y ]; then
    set -x
fi

CEPH="${CEPH} --conf=${CEPH_CONFIG_FILE} --connect-timeout=${CEPH_TIMEOUT}"
RADOSGW_ADMIN="${RADOSGW_ADMIN} --conf=${CEPH_CONFIG_FILE}"

# use timeout(1) when running cli commands if it is available
if `which timeout > /dev/null 2>&1`; then
    # use verbose option if it is available
    verbose_opt=
    if `timeout -v 10 true /dev/null 2>&1`; then
        verbose_opt=-v
    fi
    CEPH="timeout ${verbose_opt} $((CEPH_TIMEOUT * 2)) ${CEPH}"
    RADOSGW_ADMIN="timeout ${verbose_opt} $((CEPH_TIMEOUT * 2)) ${RADOSGW_ADMIN}"
fi

if [ -n "${RESULTS_DIR}" ]; then
    mkdir -p "${RESULTS_DIR}"
else
    RESULTS_DIR=$(mktemp -d /tmp/ceph-collect_$(date +%Y%m%d_%H%I%S)-XXX)
fi

trap cleanup INT TERM EXIT

get_script_info
get_system_info
get_ceph_info
get_health_info
get_monitor_info
get_device_info
get_manager_info
get_osd_info
get_pg_info
get_mds_info
get_fs_info
get_radosgw_admin_info
get_orch_info

archive_result

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
RADOSGW_ADMIN_TIMEOUT="${RADOSGW_ADMIN_TIMEOUT:-60}"
VERBOSE="${VERBOSE:-N}"
ASOK_STATS_MAX_OSDS="${ASOK_STATS_MAX_OSDS:-100}"
CRASH_LAST_DAYS="${CRASH_LAST_DAYS:-10}"
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
    echo "  -a | --archive-name <name>             name of the result archive"
    echo "  -c | --ceph-config-file <file>         ceph configuration file"
    echo "  -d | --archive-dir <dir>               directory to store result archive"
    echo "  -h | --help                            print this help and exit"
    echo "  -m | --asok-stats-max-osds <N>         get data via admin socket (tell) for"
    echo "                                         not more than N osds (default ${ASOK_STATS_MAX_OSDS})"
    echo "  -q | --query-inactive-pg               query inactive pg"
    echo "  -r | --results-dir <dir>               directory to store result"
    echo "                                         (deprecated, use -d and -a instead)"
    echo "  -t | --timeout <sec>                   timeout for ceph operations"
    echo "  -u | --uncensored                      don't hide sensitive data"
    echo "  -v | --verbose                         be verbose"
    echo "  -C | --crash-last-days <days>          number of days to look for crash logs"
    echo "  -D | --mds-perf-reset-and-sleep <sec>  reset mds perf counters and sleep"
    echo "  -G | --mgr-perf-reset-and-sleep <sec>  reset mgr perf counters and sleep"
    echo "  -M | --mon-perf-reset-and-sleep <sec>  reset mon perf counters and sleep"
    echo "  -O | --osd-perf-reset-and-sleep <sec>  reset osd perf counters and sleep"
    echo "  -T | --radosgw-admin-timeout <sec>     timeout radosgw-admin operations"
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

    "$@" | jq 'map(if (.name | test("ACCESS_KEY|SECRET_KEY|PASSWORD"; "i"))
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
                  if (.name | test("ACCESS_KEY|SECRET_KEY|PASSWORD"; "i"))
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

prettyfy_command() {
    echo "$*" | sed -Ee 's/  +/ /g' \
                    -Ee 's/--conf[= ][^ ]+ //g' \
                    -Ee 's/--cluster[= ][^ ]+ //g' \
                    -Ee 's/--connect-timeout[= ][^ ]+ //g' \
                    -Ee 's/--timeout[= ][^ ]+ //g' \
                    -Ee 's/timeout (-v:?)* *[0-9]+ //g' \
		    -Ee 's/censor_[^ ]+ //g' \
                    -Ee 's|/|_|g'
}

store() {
    local skip_json=0
    local json_file_compat=0
    local cmd

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

    cmd=$(prettyfy_command "$@")
    ln -sr "${RESULTS_DIR}/${name}" "${RESULTS_DIR}/COMMANDS/${cmd}"
}

store_tell() {
    local opt="$1"; shift
    local daemons="$1"; shift
    local t="$1"; shift
    local name="$1"; shift
    local d

    for d in ${daemons}; do
	store ${opt} ${t}-${d}-${name} ${CEPH} tell ${d} "$@" &
    done
    wait
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
    local id oldest

    info "collecting cluster health info ..."

    store    ${t}-stat            ${CEPH} health
    store    ${t}-detail          ${CEPH} health detail
    store    ${t}-df              ${CEPH} df
    store    ${t}-df-detail       ${CEPH} df detail
    store -s ${t}-report          ${CEPH} report
    store    ${t}-crash_ls        ${CEPH} crash ls
    store    ${t}-balancer-status ${CEPH} balancer status
    store -s ${t}-service-status  ${CEPH} service status

    if [ "${CRASH_LAST_DAYS}" -gt 0 ]; then
        oldest=$(date -d "-${CRASH_LAST_DAYS} days" +%F)
    else
        oldest=''
    fi
    show_stored ${t}-crash_ls | grep -o '^[0-9][^ ]*' |
    while read id; do
        test "${id}" '<' "${oldest}" && continue
        store -s ${t}-crash_info_${id} ${CEPH} crash info ${id}
    done
}

get_monitor_info() {
    local t=monitor_info
    local mons

    info "collecting monitor info ..."

    store    ${t}-stat     ${CEPH} mon stat
    store    ${t}-dump     ${CEPH} mon dump
    store -s ${t}-map      ${CEPH} mon getmap
    store -s ${t}-metadata ${CEPH} mon metadata

    mons=$(show_stored ${t}-dump | sed -nEe 's/^.* (mon\..*)$/\1/p')

    if [ "${RESET_MON_PERF_AND_SLEEP}" -gt 0 ]; then
        store_tell -S "${mons}" ${t} perf_reset perf reset all
        info "sleeping for ${RESET_MON_PERF_AND_SLEEP} sec after reseting mon perf counters ..."
        sleep ${RESET_MON_PERF_AND_SLEEP}
    fi

    store_tell -s "${mons}" ${t} config_diff            config diff
    store_tell -s "${mons}" ${t} config_show            config show
    store_tell -s "${mons}" ${t} dump_historic_ops      dump_historic_ops
    store_tell -s "${mons}" ${t} dump_historic_slow_ops dump_historic_slow_ops
    store_tell -s "${mons}" ${t} dump_mempools          dump_mempools
    store_tell -s "${mons}" ${t} mon_status             mon_status
    store_tell -s "${mons}" ${t} ops                    ops
    store_tell -s "${mons}" ${t} perf_dump              perf dump
    store_tell -s "${mons}" ${t} sessions               sessions
}

get_device_info() {
    local t=device_info

    info "collecting device info ..."

    store -c ${t}-ls ${CEPH} device ls
}

get_manager_info() {
    local t=manager_info
    local mgrs

    info "collecting manager info ..."

    store    ${t}-ls-modules ${CEPH} mgr module ls
    store -s ${t}-dump    ${CEPH} mgr dump
    store -s ${t}-metadata   ${CEPH} mgr metadata

    mgrs=$(show_stored ${t}-dump |
           sed -nEe 's/^.*"active_name": "([^"]*)".*$/mgr.\1/p')

    if [ "${RESET_MGR_PERF_AND_SLEEP}" -gt 0 ]; then
        store_tell -S "${mgrs}" ${t} perf_reset perf reset all
        info "sleeping for ${RESET_MGR_PERF_AND_SLEEP} sec after reseting mgr perf counters ..."
        sleep ${RESET_MGR_PERF_AND_SLEEP}
    fi

    store_tell -s "${mgrs}" ${t} mds_requests  mds_requests
    store_tell -s "${mgrs}" ${t} config_diff   config diff
    store_tell -s "${mgrs}" ${t} config_show   config show
    store_tell -s "${mgrs}" ${t} dump_cache    dump_cache
    store_tell -s "${mgrs}" ${t} dump_mempools dump_mempools
    store_tell -s "${mgrs}" ${t} mgr_status    mgr_status
    store_tell -s "${mgrs}" ${t} perf_dump     perf dump
    store_tell -s "${mgrs}" ${t} status        status
}

get_osd_info() {
    local t=osd_info
    local osds

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

    # Sort osds by weight and collect stats for up to ASOK_STATS_MAX_OSDS
    # of every class with highest weight.
    # The sort and awk commands below parse lines like this:
    #
    #   99    ssd     0.21799          osd.99               up   1.00000  1.00000
    #
    osds=$(show_stored ${t}-tree | sort -nrk 3 |
           awk -v max_osds=${ASOK_STATS_MAX_OSDS} '
               n[$2] < max_osds && $5 == "up" && $6 > 0.1 {
                   print $4;
                   n[$2]++;
               }'
         )

    if [ "${RESET_OSD_PERF_AND_SLEEP}" -gt 0 ]; then
        store_tell -S "${osds}" ${t} perf_reset perf reset all
        info "sleeping for ${RESET_OSD_PERF_AND_SLEEP} sec after reseting osd perf counters ..."
        sleep ${RESET_OSD_PERF_AND_SLEEP}
    fi

    store_tell -s "${osds}" ${t} cache_status                      cache status
    store_tell -s "${osds}" ${t} config_diff                       config diff
    store_tell -s "${osds}" ${t} config_show                       config show
    store_tell -s "${osds}" ${t} dump_historic_ops                 dump_historic_ops
    store_tell -s "${osds}" ${t} dump_historic_slow_ops            dump_historic_slow_ops
    store_tell -s "${osds}" ${t} dump_mempools                     dump_mempools
    store_tell -s "${osds}" ${t} dump_ops_in_flight                dump_ops_in_flight
    store_tell -s "${osds}" ${t} dump_osd_network                  dump_osd_network
    store_tell -s "${osds}" ${t} dump_scrub_reservations           dump_scrub_reservations
    store_tell -s "${osds}" ${t} dump_scrubs                       dump_scrubs
    store_tell -s "${osds}" ${t} perf_dump                         perf dump
    store_tell -s "${osds}" ${t} status                            status
    store_tell -s "${osds}" ${t} bluestore_allocator_fragmentation bluestore allocator fragmentation block
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
    local mdss

    info "collecting fs info ..."

    store ${t}-ls     ${CEPH} fs ls
    store ${t}-status ${CEPH} fs status
    store ${t}-dump   ${CEPH} fs dump

    mdss=$(show_stored ${t}-dump |
           sed -nEe 's/^\[(mds\.[^{]*).*state up:active.*/\1/p')

    if [ "${RESET_MDS_PERF_AND_SLEEP}" -gt 0 ]; then
        store_tell -S "${mdss}" ${t} perf_reset perf reset all
        info "sleeping for ${RESET_MDS_PERF_AND_SLEEP} sec after reseting mds perf counters ..."
        sleep ${RESET_MDS_PERF_AND_SLEEP}
    fi

    store_tell -s "${mdss}" ${t} cache_status       cache status
    store_tell -s "${mdss}" ${t} dump_historic_ops  dump_historic_ops
    store_tell -s "${mdss}" ${t} dump_loads         dump loads
    store_tell -s "${mdss}" ${t} dump_mempools      dump_mempools
    store_tell -s "${mdss}" ${t} dump_ops_in_flight dump_ops_in_flight
    store_tell -s "${mdss}" ${t} perf_dump          perf dump
    store_tell -s "${mdss}" ${t} scrub_status       scrub status
    store_tell -s "${mdss}" ${t} session_ls         session ls
    store_tell -s "${mdss}" ${t} status             status
    store_tell -s "${mdss}" ${t} config_diff        config diff
    store_tell -s "${mdss}" ${t} config_show        config show
    store_tell -s "${mdss}" ${t} damage_ls          damage ls
    store_tell -s "${mdss}" ${t} dump_blocked_ops   dump_blocked_ops
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

    store    ${t}-status ${CEPH} orch status
    store    ${t}-ls ${CEPH} orch ls
    store -s ${t}-ls-export ${CEPH} orch ls --export
    store -S ${t}-ls_yaml ${CEPH} orch ls --format yaml
    store    ${t}-ps ${CEPH} orch ps
    store    ${t}-host ${CEPH} orch host ls
}

get_prometheus_info() {
    local t=prometheus_info
    local target

    info "collecting prometheus info ..."

    store    ${t}-healthcheck_history_ls ${CEPH} healthcheck history ls
    store -s ${t}-file_sd_config         ${CEPH} prometheus file_sd_config

    show_stored ${t}-file_sd_config | jq -r '.[].targets[]' | sort -u |
    while read target; do
        store -S ${t}-${target}-metrics curl http://${target}/metrics
    done
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

OPTIONS=$(getopt -o a:c:d:hm:qr:t:uvC:D:G:M:O:T:V --long archive-name:,archive-dir:,asok-stats-max-osds:,ceph-config-file:,crash-last-days:,help,query-inactive-pg,results-dir:,timeout:,uncensored,verbose,mds-perf-reset-and-sleep:,mgr-perf-reset-and-sleep:,mon-perf-reset-and-sleep:,osd-perf-reset-and-sleep:,radosgw-admin-timeout:,version -- "$@")
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
	-a|--archive-name)
	    ARCHIVE_NAME="$2"
	    shift 2
	    ;;
        -c|--ceph-config-file)
            CEPH_CONFIG_FILE="$2"
            shift 2
            ;;
	-d|--archive-dir)
	    ARCHIVE_DIR="$2"
	    shift 2
	    ;;
        -m|--asok-stats-max-osds)
            ASOK_STATS_MAX_OSDS="$2"
            shift 2
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
        -C|--crash-last-days)
            CRASH_LAST_DAYS="$2"
            shift 2
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
        -T|--radosgw-admin-timeout)
            RADOSGW_ADMIN_TIMEOUT="$2"
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

# check `jq` is available
if ! which jq > /dev/null 2>&1; then
    echo "jq command not found, please install jq package" >&2
    exit 1
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
    RADOSGW_ADMIN="timeout ${verbose_opt} ${RADOSGW_ADMIN_TIMEOUT} ${RADOSGW_ADMIN}"
fi

if [ -n "${ARCHIVE_NAME}" -o -n "${ARCHIVE_DIR}" ]; then
    if [ -n "${RESULTS_DIR}" ]; then
        echo "Cannot use both --results-dir and --archive-name|dir" \
             "options simultaneously" >&2
        exit 1
    fi
    if [ -z "${ARCHIVE_DIR}" ]; then
        ARCHIVE_DIR="/tmp"
    fi
    if [ -n "${ARCHIVE_NAME}" ]; then
        RESULTS_DIR="${ARCHIVE_DIR}/${ARCHIVE_NAME}"
        if [ -e "${RESULTS_DIR}" ]; then
            echo "Cannot use ${RESULTS_DIR} as directory for storing results:" \
                 "already exists" >&2
            exit 1
        fi
        mkdir "${RESULTS_DIR}"
    else
        RESULTS_DIR=$(mktemp -d "${ARCHIVE_DIR}/ceph-collect_$(date +%Y%m%d_%H%I%S)-XXX")
    fi
elif [ -n "${RESULTS_DIR}" ]; then
    echo "WARNING: --results-dir option is deprecated, please use" \
         "--archive-name and --archive-dir options instead" >&2
    if [ -e "${RESULTS_DIR}" ]; then
        echo "Cannot use ${RESULTS_DIR} as directory for storing results:" \
             "already exists" >&2
        exit 1
    fi
    mkdir "${RESULTS_DIR}"
else
    RESULTS_DIR=$(mktemp -d /tmp/ceph-collect_$(date +%Y%m%d_%H%I%S)-XXX)
fi
mkdir  "${RESULTS_DIR}"/COMMANDS

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
get_prometheus_info

archive_result

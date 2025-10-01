#!/bin/bash -ex

NAME=otto
RELEASE=${RELEASE:-0}
EL_VERSION="${EL_VERSION:-9}"
DEST="${DEST:-${PWD}}"

if [ -n "$1" ]; then
    VERSION=$1
else
    tag="$(git describe --long 2>/dev/null)"
    [[ -z "${tag}" ]] &&
        echo "error: unable to obtain tag from git" && exit 1

    ver="${tag%%-*}"
    VERSION="${ver#v}"
    RELEASE="$(echo "${tag#*-}" | tr '-' '_')"
fi

if [ -z "$VERSION" ]; then
    echo "version not found" >&2
    echo "usage: $0 <version> [<release>]" >&2
    echo "or run from a git checkout (release tag)" >&2
    exit 1
fi

if [ -n "$2" ]; then
    RELEASE=$2
fi

[[ -z "${DEST}" ]] &&
    echo "error: missing rpm DEST directory" && exit 1

[[ ! -e "${DEST}" ]] && (mkdir "${DEST}" || exit 1)

[[ -z "${EL_VERSION}" ]] &&
    echo "error: missing EL_VERSION" && exit 1

dist_version=".el${EL_VERSION}."

# build copilot python binary
./build.sh || exit 1

pkg_name="${NAME}-${VERSION}"
basedir="$(mktemp --suffix=-copilot-rpm -d)"
rpmdir="${basedir}/rpms"
srcdir="${basedir}/${pkg_name}"

mkdir "${rpmdir}" || exit 1
HOME="${rpmdir}" rpmdev-setuptree

specfile="${rpmdir}/rpmbuild/SPECS/${NAME}.spec"
sed "s/@VERSION@/$VERSION/g; s/@RELEASE@/$RELEASE/g" ${NAME}.spec.in >"${specfile}"

mkdir "${srcdir}" || exit 1
install -m 755 dist/otto "${srcdir}"/ || exit 1
install -m 644 LICENSE "${srcdir}"/ || exit 1
install -m 644 README.md "${srcdir}"/ || exit 1

tar -C "${basedir}" \
    --bzip2 -cvf "${rpmdir}"/rpmbuild/SOURCES/"${pkg_name}".tar.bz2 \
    "${pkg_name}" || exit 1

rm -fr "${srcdir}" || exit 1

rpmbuild \
    --define "_topdir ${rpmdir}/rpmbuild" \
    --define "dist ${dist_version}" \
    -bb "${specfile}" || exit 1

cp "${rpmdir}"/rpmbuild/RPMS/x86_64/otto-*.rpm "${DEST}"/
rm -fr "${basedir}"

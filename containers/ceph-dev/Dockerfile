
# Adapted from https://github.com/ceph/go-ceph 
ARG CEPH_IMG=quay.io/ceph/ceph
ARG CEPH_TAG=v19
FROM ${CEPH_IMG}:${CEPH_TAG}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Provide a few quality-of-life tools plus dependencies that the micro-ceph
# bootstrap script relies on (uuidgen, getent, jq, etc.).
RUN set -euxo pipefail \
    && pkg_mgr="dnf" \
    && if command -v microdnf >/dev/null 2>&1; then pkg_mgr="microdnf"; fi \
    && if [[ "${pkg_mgr}" == "microdnf" ]]; then \
        microdnf install -y --setopt=install_weak_deps=0 --setopt=tsflags=nodocs \
            bash-completion \
            findutils \
            hostname \
            iproute \
            jq \
            less \
            procps-ng \
            python3.11 \
            python3.11-devel \
            python3.11-pip \
            util-linux \
            vim-minimal \
        && microdnf clean all; \
    else \
        dnf install -y --setopt=install_weak_deps=0 --setopt=tsflags=nodocs \
            bash-completion \
            findutils \
            hostname \
            iproute \
            jq \
            less \
            procps-ng \
            python3.11 \
            python3.11-devel \
            python3.11-pip \
            util-linux \
            vim-minimal \
        && dnf clean all; \
    fi

ARG UV_VERSION=v0.4.23
RUN curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh \
    && chmod +x /tmp/uv-install.sh \
    && UV_INSTALL_DIR=/usr/local/bin /tmp/uv-install.sh \
    && rm -f /tmp/uv-install.sh

COPY micro-osd.sh /usr/local/bin/micro-osd.sh
COPY entrypoint.sh /usr/local/bin/ceph-dev-entrypoint.sh
RUN chmod +x /usr/local/bin/micro-osd.sh /usr/local/bin/ceph-dev-entrypoint.sh

ENV CEPH_DATA_DIR=/var/lib/ceph-dev \
    CEPH_BOOTSTRAP=auto \
    CEPH_STATUS_ON_START=true
ENTRYPOINT ["/usr/local/bin/ceph-dev-entrypoint.sh"]
CMD ["/bin/bash"]
